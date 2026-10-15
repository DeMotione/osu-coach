#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{Read, Write};
use std::net::{Ipv4Addr, SocketAddr, TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::{Manager, RunEvent};

const HOST: Ipv4Addr = Ipv4Addr::LOCALHOST;
const SERVER_NAME: &str = if cfg!(windows) { "osu-coach.exe" } else { "osu-coach" };

struct Server(Mutex<Option<Child>>);

#[tauri::command]
fn windows_supports_mica() -> bool {
    #[cfg(windows)]
    {
        #[repr(C)]
        struct OsVersionInfoW {
            size: u32,
            major: u32,
            minor: u32,
            build: u32,
            platform_id: u32,
            service_pack: [u16; 128],
        }

        #[link(name = "ntdll")]
        extern "system" {
            fn RtlGetVersion(info: *mut OsVersionInfoW) -> i32;
        }

        let mut version = OsVersionInfoW {
            size: std::mem::size_of::<OsVersionInfoW>() as u32,
            major: 0,
            minor: 0,
            build: 0,
            platform_id: 0,
            service_pack: [0; 128],
        };
        // Mica is supported starting with Windows 11 (build 22000).
        unsafe { RtlGetVersion(&mut version) == 0 && version.major == 10 && version.build >= 22000 }
    }
    #[cfg(not(windows))]
    {
        false
    }
}

#[cfg(feature = "embedded-server")]
static SERVER_ZIP: &[u8] = include_bytes!("../server.zip");

/// Unpacks the server baked into this executable (once per build) and returns its path.
#[cfg(feature = "embedded-server")]
fn embedded_server(data_dir: &std::path::Path) -> Result<PathBuf, String> {
    use std::hash::{Hash, Hasher};
    // keyed on the zip contents too, so a rebuild with an unchanged version never reuses an older unpacked server
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    SERVER_ZIP.hash(&mut hasher);
    let version = format!("{}-{:016x}", env!("CARGO_PKG_VERSION"), hasher.finish());
    let version = version.as_str();
    let runtime = data_dir.join("runtime");
    let dir = runtime.join(version);
    let exe = dir.join(SERVER_NAME);
    if dir.join(".complete").exists() && exe.exists() {
        return Ok(exe);
    }
    // other versions' folders (a running older instance may keep its own; that removal just fails)
    if let Ok(entries) = std::fs::read_dir(&runtime) {
        for e in entries.flatten().filter(|e| e.file_name() != version) {
            let _ = std::fs::remove_dir_all(e.path());
        }
    }
    let tmp = runtime.join(format!("{version}.tmp"));
    let _ = std::fs::remove_dir_all(&tmp);
    let err = |e: &dyn std::fmt::Display| format!("cannot unpack the server to {}: {e}", dir.display());
    std::fs::create_dir_all(&tmp).map_err(|e| err(&e))?;
    zip::ZipArchive::new(std::io::Cursor::new(SERVER_ZIP))
        .and_then(|mut z| z.extract(&tmp))
        .map_err(|e| err(&e))?;
    std::fs::write(tmp.join(".complete"), version).map_err(|e| err(&e))?;
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::rename(&tmp, &dir).map_err(|e| err(&e))?;
    Ok(exe)
}

/// `OSU_COACH_API_BIN` (osu-coach-api), else the server baked into this executable, else a bundled `osu-coach`
/// folder in the resources, else `osu-coach-api` on PATH.
fn server_command(data_dir: Option<PathBuf>, resources: Option<PathBuf>, port: u16) -> Result<Command, String> {
    let port = port.to_string();
    if let Some(p) = std::env::var_os("OSU_COACH_API_BIN") {
        let mut cmd = Command::new(p);
        cmd.args(["--port", &port]);
        return Ok(cmd);
    }
    #[cfg(feature = "embedded-server")]
    {
        let data_dir = data_dir.ok_or("no local data folder")?;
        let _ = resources;
        let mut cmd = Command::new(embedded_server(&data_dir)?);
        cmd.args(["ui", "--port", &port, "--no-browser"]);
        return Ok(cmd);
    }
    #[cfg(not(feature = "embedded-server"))]
    {
        let _ = data_dir;
        Ok(resource_or_path_command(resources, &port))
    }
}

#[cfg(not(feature = "embedded-server"))]
fn resource_or_path_command(resources: Option<PathBuf>, port: &str) -> Command {
    let name = SERVER_NAME;
    if let Some(bundled) = resources.map(|r| r.join("osu-coach").join(name)).filter(|p| p.exists()) {
        let mut cmd = Command::new(bundled);
        cmd.args(["ui", "--port", port, "--no-browser"]);
        return cmd;
    }
    let mut cmd = Command::new("osu-coach-api");
    cmd.args(["--port", port]);
    cmd
}

/// Stable port keeps the web origin (and its localStorage/PWA data) the same across launches; falls back to any free port if taken.
const PREFERRED_PORT: u16 = 8511;

fn free_port() -> std::io::Result<u16> {
    let listener = TcpListener::bind((HOST, PREFERRED_PORT)).or_else(|_| TcpListener::bind((HOST, 0)))?;
    Ok(listener.local_addr()?.port())
}

fn spawn_api(data_dir: Option<PathBuf>, resources: Option<PathBuf>, port: u16) -> Result<Child, String> {
    let mut cmd = server_command(data_dir, resources, port)?;
    cmd.stdin(Stdio::null());
    if !cfg!(debug_assertions) {
        cmd.env("OSU_COACH_API_DOCS", "false");
    }
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    }
    cmd.spawn().map_err(|e| format!("cannot start the osu! coach server ({e}); set OSU_COACH_API_BIN"))
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
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![windows_supports_mica])
        .manage(Server(Mutex::new(None)))
        .setup(|app| {
            let port = free_port()?;
            let window = app.get_webview_window("main").expect("main window");
            let handle = app.handle().clone();
            let data_dir = app.path().app_local_data_dir().ok();
            let resources = app.path().resource_dir().ok();
            // off the main thread: the first launch unpacks the server, which takes a few seconds
            std::thread::spawn(move || {
                match spawn_api(data_dir, resources, port) {
                    Ok(child) => *handle.state::<Server>().0.lock().unwrap() = Some(child),
                    Err(e) => {
                        let _ = window.eval(&format!("document.body.textContent = {e:?}"));
                        return;
                    }
                }
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
