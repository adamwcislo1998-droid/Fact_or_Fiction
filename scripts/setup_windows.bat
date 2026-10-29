@echo off
REM Keep command output tidy and isolate environment-variable changes.
setlocal

REM %~dp0 is this batch file's directory. /d also permits changing drive.
cd /d "%~dp0..\backend"

REM Prefer the Windows Python launcher (py), then fall back to python on PATH.
where py >nul 2>nul
if not errorlevel 1 (
  set "PYTHON_COMMAND=py"
) else (
  where python >nul 2>nul
  if errorlevel 1 (
    echo Python was not found. Install Python 3.10 or later and try again.
    exit /b 1
  )
  set "PYTHON_COMMAND=python"
)

REM Create an isolated backend virtual environment on first setup only.
if not exist .venv (
  %PYTHON_COMMAND% -m venv .venv
  if errorlevel 1 exit /b 1
)

REM Activate that environment and install the portable default dependencies.
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 1

REM Give the user the next command after successful setup.
echo.
echo Setup complete. Start the backend with:
echo scripts\run_backend_windows.bat
endlocal
