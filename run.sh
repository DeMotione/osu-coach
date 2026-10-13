#!/usr/bin/env sh
# osu! coach launcher (Linux / macOS): sets up the Python packages and builds the web app on the first run,
# then opens the app. Needs Python 3.11+ and, for the first build of the web app, Node.js 22.12+.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/osu-coach-api ]; then
  echo "First run: setting up (this takes a minute)..."
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -c constraints.txt -e ./core -e ./api
fi
# (re)build the web app when it is missing or older than its sources (e.g. after a git pull)
if [ ! -f frontend/dist/index.html ] || \
   [ -n "$(find frontend/src frontend/index.html frontend/package.json -newer frontend/dist/index.html 2>/dev/null | head -n 1)" ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "The web app has to be built once with Node.js 22.12 or newer: https://nodejs.org/" >&2
    exit 1
  fi
  echo "Building the web app..."
  (cd frontend && npm ci --no-audit --no-fund --loglevel=error && npm run build --silent)
fi
exec .venv/bin/osu-coach ui "$@"
