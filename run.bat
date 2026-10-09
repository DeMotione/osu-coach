@echo off
rem osu! coach launcher (Windows): creates a virtual environment on first run, then opens the app.
cd /d "%~dp0"
if exist ".venv\Scripts\osu-coach.exe" goto run

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
".venv\Scripts\python.exe" -m pip install --quiet -e . || goto pipfail

:run
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
