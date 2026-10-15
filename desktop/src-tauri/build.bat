@echo off
rem Builds the desktop app for release (setup .exe, .msi, portable .exe) with the server embedded; output in
rem desktop\src-tauri\target\release. Needs Node.js 22.12+ and Rust; sets up .venv itself if it is missing.
cd /d "%~dp0..\.."
if not defined PY (
  set "PY=.venv\Scripts\python.exe"
  if not exist ".venv\Scripts\python.exe" call run.bat --setup || exit /b 1
)
%PY% -c "import osu_coach" 2>nul || (
  echo No Python with osu-coach installed: set PY to one, or delete .venv and run this again.
  exit /b 1
)

%PY% -m pip install --quiet -c constraints.txt pyinstaller pillow || exit /b 1

rem Always a clean build: drop every previous build output and cache first.
for %%D in (build dist frontend\dist desktop\src-tauri\target) do if exist "%%D" rmdir /s /q "%%D"
if exist desktop\src-tauri\server.zip del /q desktop\src-tauri\server.zip

pushd frontend
call npm ci --no-audit --no-fund --loglevel=error || (popd & exit /b 1)
call npm run build --silent || (popd & exit /b 1)
popd

%PY% packaging\make_icon.py || exit /b 1
%PY% -m PyInstaller packaging\osu-coach.spec --noconfirm --clean || exit /b 1
%PY% packaging\make_server_zip.py || exit /b 1

cd desktop
call npm ci --no-audit --no-fund --loglevel=error || exit /b 1
call npx tauri build --bundles nsis,msi --features embedded-server %* || exit /b 1

echo.
echo Setup: src-tauri\target\release\bundle\nsis
echo MSI:   src-tauri\target\release\bundle\msi
echo Portable: src-tauri\target\release\osu-coach-desktop.exe
