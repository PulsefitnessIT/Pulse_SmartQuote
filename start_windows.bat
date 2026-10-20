@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if errorlevel 1 (
  echo ERROR: Cannot access the extracted SmartQuote folder.
  echo Move the extracted folder to Documents and try again.
  pause
  exit /b 1
)

if not exist "startup_manager.py" (
  echo ERROR: The SmartQuote launcher is missing startup_manager.py.
  echo Download the complete ZIP from GitHub, right-click it and select Extract All.
  echo Do not run this file directly from inside a ZIP preview.
  pause
  exit /b 1
)

set "PYBOOT="
py -3.11 -c "import sys" >nul 2>nul
if not errorlevel 1 set "PYBOOT=py -3.11"
if not defined PYBOOT (
  py -3 -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
  if not errorlevel 1 set "PYBOOT=py -3"
)
if not defined PYBOOT (
  python -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
  if not errorlevel 1 set "PYBOOT=python"
)
if not defined PYBOOT (
  echo ERROR: Python 3.11 or newer was not found.
  echo Download Python from https://www.python.org/downloads/windows/
  echo Select Add Python to PATH during installation, then try again.
  echo.
  echo For staff, use the no-Python Windows application from GitHub Actions:
  echo https://github.com/PulsefitnessIT/Pulse_SmartQuote/actions
  echo Open the latest successful V10 run and download SmartQuote-V10-Windows-No-Python.
  pause
  exit /b 1
)

%PYBOOT% "startup_manager.py" %*
set "RESULT=%errorlevel%"
if not "%RESULT%"=="0" (
  echo.
  echo SmartQuote did not start. See the message above for a suggested fix.
  pause
)
exit /b %RESULT%
