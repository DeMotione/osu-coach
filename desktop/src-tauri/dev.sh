#!/usr/bin/env bash
# Runs the desktop app in dev mode: the .venv's API server and the built web app (built here if missing).
set -euo pipefail
cd "$(dirname "$0")/../.."

[ -x .venv/bin/osu-coach-api ] || { echo "Run ./run.sh once first to set up .venv." >&2; exit 1; }
[ -f frontend/dist/index.html ] || (cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent)

export OSU_COACH_API_BIN="$PWD/.venv/bin/osu-coach-api"
export OSU_COACH_WEB_DIR="$PWD/frontend/dist"
cd desktop
[ -d node_modules ] || npm ci --no-audit --no-fund --loglevel=error
exec npm run dev -- "$@"
