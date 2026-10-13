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

From the repo root, with the venv active (`pip install -c constraints.txt -e ./backend pyinstaller`):

```powershell
cd frontend; npm ci; npm run build; cd ..
python -m PyInstaller packaging/osu-coach.spec --noconfirm
New-Item -ItemType Directory desktop\src-tauri\resources -Force
Remove-Item desktop\src-tauri\resources\osu-coach -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item dist\osu-coach desktop\src-tauri\resources\osu-coach -Recurse
cd desktop
npx tauri build --config src-tauri/tauri.release.conf.json
```

The installer is `src-tauri\target\release\bundle\nsis\osu! coach_<version>_x64-setup.exe` and bundles the frozen server.

## Other

```powershell
npm run icon           # regenerate icons from frontend/public/pwa-512.png
cd src-tauri; cargo check
```
