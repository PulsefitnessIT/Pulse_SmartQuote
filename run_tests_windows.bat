@echo off
cd /d "%~dp0"
set SMARTQUOTE_AUTH=off
where py >nul 2>nul
if %errorlevel%==0 (set PY=py) else (set PY=python)
%PY% -m unittest discover -s tests -v
pause
