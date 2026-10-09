@echo off
rem osu! coach launcher (Windows): creates a virtual environment on first run, then opens the app.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo First run: setting up ^(this takes a minute^)...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo Python 3.11+ is required: https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^)
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
  ".venv\Scripts\python.exe" -m pip install --quiet -e .
)
".venv\Scripts\osu-coach.exe" ui %*
