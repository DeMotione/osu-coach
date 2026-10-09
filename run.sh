#!/usr/bin/env sh
# osu! coach launcher (Linux / macOS): creates a virtual environment on first run, then opens the app.
set -e
cd "$(dirname "$0")"
if [ ! -x .venv/bin/python ]; then
  echo "First run: setting up (this takes a minute)..."
  python3 -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  .venv/bin/python -m pip install --quiet -e .
fi
exec .venv/bin/osu-coach ui "$@"
