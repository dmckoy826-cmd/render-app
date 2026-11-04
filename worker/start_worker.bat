@echo off
REM FinishFlow Rhino worker — edit the two values below, then double-click.
REM Requires: Python 3.10+ (with `requests`) and Rhino 8 with V-Ray installed.

REM Base URL of the FinishFlow server (LAN IP, or the hosted sandbox URL).
set FF_API=http://YOUR-SERVER-LAN-IP:8000

REM Full path to Rhino.exe
set FF_RHINO=C:\Program Files\Rhino 8\System\Rhino.exe

where python >nul 2>nul
if errorlevel 1 (
  echo Python not found on PATH — install Python 3.10+ from python.org and re-run.
  pause
  exit /b 1
)
python -c "import requests" >nul 2>nul
if errorlevel 1 (
  echo Installing missing dependency: requests
  python -m pip install requests
)
echo Starting FinishFlow worker against %FF_API% ...
python "%~dp0agent.py"
pause
