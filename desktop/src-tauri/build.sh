#!/usr/bin/env bash
# Builds the desktop app for release (.deb) with the server embedded; output in desktop/src-tauri/target/release.
# Needs Node.js 22.12+, Rust and the Tauri system packages (see desktop/README.md); sets up .venv itself if missing.
set -euo pipefail
cd "$(dirname "$0")/../.."

if [ -z "${PY:-}" ]; then
  PY=.venv/bin/python
  [ -x "$PY" ] || ./run.sh --setup
fi
$PY -c 'import osu_coach' 2>/dev/null || { echo "No Python with osu-coach installed: set PY to one, or delete .venv and run this again." >&2; exit 1; }

$PY -m pip install --quiet -c constraints.txt pyinstaller
# Always a clean build: drop every previous build output and cache first.
rm -rf build dist frontend/dist desktop/src-tauri/target desktop/src-tauri/server.zip

(cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent)
$PY -m PyInstaller packaging/osu-coach.spec --noconfirm --clean
$PY packaging/make_server_zip.py

cd desktop
npm ci --no-audit --no-fund --loglevel=error
npx tauri build --bundles deb --features embedded-server "$@"

echo
echo "Package: desktop/src-tauri/target/release/bundle/deb"
