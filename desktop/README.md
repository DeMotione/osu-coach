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

The installers bundle the frozen server (`packaging/osu-coach.spec`) as a resource, so they need no Python.
From the repo root, with the venv active (`pip install -c constraints.txt -e ./backend pyinstaller`):

### Windows (.exe setup, .msi)

```powershell
cd frontend; npm ci; npm run build; cd ..
python -m PyInstaller packaging/osu-coach.spec --noconfirm
New-Item -ItemType Directory desktop\src-tauri\resources -Force
Remove-Item desktop\src-tauri\resources\osu-coach -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item dist\osu-coach desktop\src-tauri\resources\osu-coach -Recurse
cd desktop
npx tauri build --config src-tauri/tauri.release.conf.json
```

The installers are `src-tauri\target\release\bundle\nsis\osu! coach_<version>_x64-setup.exe` and
`src-tauri\target\release\bundle\msi\osu! coach_<version>_x64_en-US.msi`.

### Linux (.deb)

Needs the [Tauri Linux packages](https://tauri.app/start/prerequisites/#linux); on Debian / Ubuntu:

```sh
sudo apt install libwebkit2gtk-4.1-dev libxdo-dev libssl-dev libayatana-appindicator3-dev librsvg2-dev build-essential
```

Then, from the repo root:

```sh
(cd frontend && npm ci && npm run build)
python -m PyInstaller packaging/osu-coach.spec --noconfirm
rm -rf desktop/src-tauri/resources/osu-coach && mkdir -p desktop/src-tauri/resources
cp -a dist/osu-coach desktop/src-tauri/resources/osu-coach
cd desktop && npm ci
npx tauri build --bundles deb --config src-tauri/tauri.release.conf.json
```

The package is `src-tauri/target/release/bundle/deb/osu! coach_<version>_amd64.deb`; install it with
`sudo apt install "./src-tauri/target/release/bundle/deb/osu! coach_<version>_amd64.deb"`. It puts the app in
`/usr/bin/osu-coach-desktop` (menu entry *osu! coach*) and the server in `/usr/lib/osu! coach/`. A package built on
an older distribution also runs on newer ones (the release builds it on Ubuntu 22.04).

### Releases

`.github/workflows/release.yml` builds all of this (plus the Inno Setup installer and the portable exe) when a tag
`v<version>` is pushed, and publishes the files as a GitHub release.

## Other

```powershell
npm run icon           # regenerate icons from frontend/public/pwa-512.png
cd src-tauri; cargo check
```
