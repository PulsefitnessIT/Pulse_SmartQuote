@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
 echo Failed to install Python dependencies. Please contact IT.
 pause
 exit /b 1
)
%PY% manage_users.py bootstrap
if errorlevel 1 (
 echo SmartQuote account setup failed. Application not started.
 pause
 exit /b 1
)
start "" /B cmd /C "timeout /t 3 /nobreak >nul & start http://127.0.0.1:8765"
%PY% -m uvicorn main:app --host 127.0.0.1 --port 8765
pause
