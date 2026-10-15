# osu! coach desktop (Tauri)

A native window around the local web app. On start it launches `osu-coach-api` on a free port, waits for `/api/health`, then loads the app from it. On exit it stops the server.

## Prerequisites

- Rust (stable) and the [Tauri prerequisites](https://tauri.app/start/prerequisites/) (WebView2 on Windows)
- Node >= 22.12
- Python venv with the backend installed, so `osu-coach-api` exists

## Setup

From the repo root:

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e backend[dev]

cd frontend
npm install
npm run build          # build the web app
cd ..
# copy frontend\dist into backend\src\osu_coach\web (the API serves the app from there)
Copy-Item frontend\dist backend\src\osu_coach\web -Recurse -Force

cd desktop
npm install
```

## Run (dev)

With the venv active, so `osu-coach-api` is on `PATH`:

```powershell
cd desktop
npm run dev
```

To use a specific server binary: `$env:OSU_COACH_API_BIN = "C:\path\to\osu-coach-api.exe"`.

## Build

The installers embed the frozen server (`packaging/osu-coach.spec`) in the app's executable, so they need no Python
and the executable alone is the whole app: on first start it unpacks the server to its local data folder.
From the repo root, with the venv active (`pip install -c constraints.txt -e ./backend pyinstaller`):

### Windows (.exe setup, .msi, portable .exe)

```powershell
cd frontend; npm ci; npm run build; cd ..
python -m PyInstaller packaging/osu-coach.spec --noconfirm
python packaging/make_server_zip.py
cd desktop
npx tauri build --bundles nsis,msi --features embedded-server
```

The installers are `src-tauri\target\release\bundle\nsis\osu! coach_<version>_x64-setup.exe` and
`src-tauri\target\release\bundle\msi\osu! coach_<version>_x64_en-US.msi`.

Portable (what the release ships): `src-tauri\target\release\osu-coach-desktop.exe` runs on its own from any folder.
It needs Microsoft's WebView2 runtime, which Windows 11 has and Windows 10 gets with Edge.

### Linux (.deb)

On Debian / Ubuntu / Mint, one script does all of the following: it installs what the build needs (the system
packages below, Rust, a Python venv), builds the `.deb` and installs it with apt. It needs Python 3.11+ and
Node.js 22.12+. Run it as your normal user from anywhere in the repo:

```sh
bash packaging/build-deb.sh               # build + install
bash packaging/build-deb.sh --no-install  # only build: dist/osu-coach_<version>_amd64.deb
```

By hand: it needs the [Tauri Linux packages](https://tauri.app/start/prerequisites/#linux) and Rust
(`curl https://sh.rustup.rs -sSf | sh`, not the distribution's `cargo`, which is usually too old). On Debian / Ubuntu:

```sh
sudo apt install libwebkit2gtk-4.1-dev libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev build-essential
```

Then, from the repo root:

```sh
(cd frontend && npm ci && npm run build)
python -m PyInstaller packaging/osu-coach.spec --noconfirm
python packaging/make_server_zip.py
cd desktop && npm ci
npx tauri build --bundles deb --features embedded-server
```

The package is `src-tauri/target/release/bundle/deb/osu! coach_<version>_amd64.deb`; install it with
`sudo apt install "./src-tauri/target/release/bundle/deb/osu! coach_<version>_amd64.deb"`. It puts the app in
`/usr/bin/osu-coach-desktop` (menu entry *osu! coach*); the server is inside that binary. A package built on
an older distribution also runs on newer ones (the release builds it on Ubuntu 22.04).

### Releases

`.github/workflows/release.yml` builds all of this when a tag
`v<version>` is pushed, and publishes the files as a GitHub release.

## Other

```powershell
npm run icon           # regenerate icons from frontend/public/pwa-512.png
cd src-tauri; cargo check
```
