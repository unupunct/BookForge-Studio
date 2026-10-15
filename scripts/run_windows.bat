@echo off
rem Starts BookForge Studio from source (creates the virtual environment on first run).
setlocal
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
    echo Creating virtual environment...
    python -m venv .venv || goto :error
    .venv\Scripts\python -m pip install --upgrade pip || goto :error
    .venv\Scripts\python -m pip install -r requirements.txt || goto :error
)
.venv\Scripts\python main.py %*
exit /b %errorlevel%
:error
echo Setup failed. Install Python 3.11+ and try again.
exit /b 1
