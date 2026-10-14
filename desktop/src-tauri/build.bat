@echo off
rem Builds the desktop app for release (setup .exe, .msi, portable .exe) with the server embedded; output in
rem desktop\src-tauri\target\release. Needs .venv (run.bat once), Node.js 22.12+ and Rust.
cd /d "%~dp0..\.."
if not defined PY set "PY=.venv\Scripts\python.exe"
%PY% -c "import osu_coach" 2>nul || (
  echo No Python with osu-coach installed: run run.bat once to set up .venv, or set PY.
  exit /b 1
)

%PY% -m pip install --quiet -c constraints.txt pyinstaller pillow || exit /b 1

pushd frontend
call npm ci --no-audit --no-fund --loglevel=error || (popd & exit /b 1)
call npm run build --silent || (popd & exit /b 1)
popd

%PY% packaging\make_icon.py || exit /b 1
%PY% -m PyInstaller packaging\osu-coach.spec --noconfirm || exit /b 1
%PY% packaging\make_server_zip.py || exit /b 1

cd desktop
call npm ci --no-audit --no-fund --loglevel=error || exit /b 1
call npx tauri build --bundles nsis,msi --features embedded-server %* || exit /b 1

echo.
echo Setup: src-tauri\target\release\bundle\nsis
echo MSI:   src-tauri\target\release\bundle\msi
echo Portable: src-tauri\target\release\osu-coach-desktop.exe
