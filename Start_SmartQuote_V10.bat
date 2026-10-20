@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
if not exist "Pulse_SmartQuote_V10.exe" (
  echo ERROR: The SmartQuote Windows program is missing.
  echo Download the Windows Portable ZIP from GitHub Actions. Extract ALL files.
  echo Do not use the developer source-code ZIP for this installer-free edition.
  pause
  exit /b 1
)
"%~dp0Pulse_SmartQuote_V10.exe" %*
if errorlevel 1 (
  echo.
  echo SmartQuote could not start. Send the error above to IT or the development team.
  pause
  exit /b 1
)
exit /b 0
