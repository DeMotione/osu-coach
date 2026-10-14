@echo off
rem osu! coach launcher (Windows): sets up the Python packages and builds the web app on the first run, then opens
rem the app. Needs Python 3.11+ and, for the first build of the web app, Node.js 22.12+.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" ".venv\Scripts\python.exe" -c "import osu_coach.main" 2>nul && goto web

echo First run: setting up ^(this takes a minute^)...
if exist ".venv" rmdir /s /q ".venv"
rem Prefer a real python.exe: the "py"/"python" app aliases can stop to ask first-run questions.
set "PY="
if exist "%LOCALAPPDATA%\Python\bin\python.exe" set "PY=%LOCALAPPDATA%\Python\bin\python.exe"
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  "%%D\python.exe" -c "import sys; sys.exit(sys.version_info < (3, 11))" 2>nul && set "PY=%%D\python.exe"
)
if defined PY (
  "%PY%" -m venv .venv
) else (
  py -3 -m venv .venv 2>nul || python -m venv .venv
)
if not exist ".venv\Scripts\python.exe" goto nopython
".venv\Scripts\python.exe" -c "import sys; sys.exit(sys.version_info < (3, 11))" || goto oldpython
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -c constraints.txt -e backend || goto pipfail

:web
if exist "frontend\dist\index.html" goto run
where npm >nul 2>nul || goto nonode
echo Building the web app ^(first run only^)...
pushd frontend
call npm ci --no-audit --no-fund --loglevel=error || goto npmfail
call npm run build --silent || goto npmfail
popd

:run
if /i "%~1"=="--setup" exit /b 0
".venv\Scripts\osu-coach.exe" ui %*
exit /b

:oldpython
rmdir /s /q ".venv"
:nopython
echo Python 3.11 or newer is required: https://www.python.org/downloads/  ^(tick "Add python.exe to PATH"^)
pause
exit /b 1

:pipfail
rmdir /s /q ".venv"
echo Installing the parts osu! coach needs failed. Check the internet connection and run this again.
pause
exit /b 1

:nonode
echo The web app has to be built once with Node.js 22.12 or newer: https://nodejs.org/
echo ^(Or install osu! coach with the setup .exe from the Releases page: it needs neither Python nor Node.js.^)
pause
exit /b 1

:npmfail
popd
echo Building the web app failed. Check the internet connection and run this again.
pause
exit /b 1
