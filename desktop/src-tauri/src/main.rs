#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{Read, Write};
use std::net::{Ipv4Addr, SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, RunEvent};

const HOST: Ipv4Addr = Ipv4Addr::LOCALHOST;

struct Server(Mutex<Option<Child>>);

/// `OSU_COACH_API_BIN` (osu-coach-api), else the bundled `osu-coach` app, else `osu-coach-api` on PATH.
fn server_command(resources: Option<PathBuf>, port: u16) -> Command {
    let port = port.to_string();
    if let Some(p) = std::env::var_os("OSU_COACH_API_BIN") {
        let mut cmd = Command::new(p);
        cmd.args(["--port", &port]);
        return cmd;
    }
    let name = if cfg!(windows) { "osu-coach.exe" } else { "osu-coach" };
    if let Some(bundled) = resources.map(|r| r.join("osu-coach").join(name)).filter(|p| p.exists()) {
        let mut cmd = Command::new(bundled);
        cmd.args(["ui", "--port", &port, "--no-browser"]);
        return cmd;
    }
    let mut cmd = Command::new("osu-coach-api");
    cmd.args(["--port", &port]);
    cmd
}

fn free_port() -> std::io::Result<u16> {
    Ok(TcpListener::bind((HOST, 0))?.local_addr()?.port())
}

fn spawn_api(resources: Option<PathBuf>, port: u16) -> std::io::Result<Child> {
    let mut cmd = server_command(resources, port);
    cmd.stdin(Stdio::null());
    if !cfg!(debug_assertions) {
        cmd.env("OSU_COACH_API_DOCS", "false");
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    cmd.spawn()
}

fn is_healthy(port: u16) -> bool {
    let addr = SocketAddr::from((HOST, port));
    let Ok(mut s) = TcpStream::connect_timeout(&addr, Duration::from_millis(500)) else {
        return false;
    };
    let _ = s.set_read_timeout(Some(Duration::from_secs(2)));
    let req = format!("GET /api/health HTTP/1.0\r\nHost: 127.0.0.1:{port}\r\n\r\n");
    let mut body = String::new();
    s.write_all(req.as_bytes()).is_ok() && s.read_to_string(&mut body).is_ok() && body.contains("\"ok\"")
}

fn main() {
    let app = tauri::Builder::default()
        .manage(Server(Mutex::new(None)))
        .setup(|app| {
            let port = free_port()?;
            let child = spawn_api(app.path().resource_dir().ok(), port).map_err(|e| format!("cannot start osu-coach-api ({e}); set OSU_COACH_API_BIN"))?;
            *app.state::<Server>().0.lock().unwrap() = Some(child);

            let window = app.get_webview_window("main").expect("main window");
            std::thread::spawn(move || {
                for _ in 0..300 {
                    if is_healthy(port) {
                        let _ = window.navigate(format!("http://127.0.0.1:{port}").parse().unwrap());
                        return;
                    }
                    std::thread::sleep(Duration::from_millis(100));
                }
                let _ = window.eval("document.body.textContent = 'osu! coach could not start its local server.'");
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the app");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(mut child) = handle.state::<Server>().0.lock().unwrap().take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    });
}
