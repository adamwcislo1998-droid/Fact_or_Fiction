@echo off
REM Start the backend with the project virtual environment, not global Python.
setlocal
cd /d "%~dp0..\backend"

REM Detect an incomplete setup and provide the correct recovery command.
if not exist .venv\Scripts\python.exe (
  echo Backend environment not found. Run scripts\setup_windows.bat first.
  exit /b 1
)

REM app.py starts Flask on the configured localhost address and port.
.venv\Scripts\python.exe app.py
endlocal
