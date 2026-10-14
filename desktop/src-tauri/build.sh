#!/usr/bin/env bash
# Builds the desktop app for release (.deb) with the server embedded; output in desktop/src-tauri/target/release.
# Needs .venv (./run.sh once), Node.js 22.12+, Rust and the Tauri system packages (see desktop/README.md).
set -euo pipefail
cd "$(dirname "$0")/../.."

PY=${PY:-.venv/bin/python}
$PY -c 'import osu_coach' 2>/dev/null || { echo "No Python with osu-coach installed: run ./run.sh once to set up .venv, or set PY." >&2; exit 1; }

$PY -m pip install --quiet -c constraints.txt pyinstaller
(cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent)
$PY -m PyInstaller packaging/osu-coach.spec --noconfirm
$PY packaging/make_server_zip.py

cd desktop
npm ci --no-audit --no-fund --loglevel=error
npx tauri build --bundles deb --features embedded-server "$@"

echo
echo "Package: desktop/src-tauri/target/release/bundle/deb"
