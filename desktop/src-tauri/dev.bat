@echo off
rem Runs the desktop app in dev mode: the .venv's API server and the built web app (both set up here if missing).
cd /d "%~dp0..\.."
if not exist ".venv\Scripts\osu-coach-api.exe" (
  echo Setting up .venv and the web app ^(first run only^)...
  call run.bat --setup || exit /b 1
)
if not exist "frontend\node_modules" (
  pushd frontend
  call npm ci --no-audit --no-fund --loglevel=error || (popd & exit /b 1)
  popd
)
pushd frontend
call npm run build --silent || (popd & exit /b 1)
popd
set "OSU_COACH_API_BIN=%CD%\.venv\Scripts\osu-coach-api.exe"
set "OSU_COACH_WEB_DIR=%CD%\frontend\dist"
cd desktop
if not exist node_modules call npm ci --no-audit --no-fund --loglevel=error || exit /b 1
call npm run dev -- %*
