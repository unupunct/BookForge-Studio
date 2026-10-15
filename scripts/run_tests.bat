@echo off
rem Runs the complete automated test suite (headless Qt, no window appears).
setlocal
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
    python -m venv .venv || exit /b 1
    .venv\Scripts\python -m pip install -r requirements.txt || exit /b 1
)
set QT_QPA_PLATFORM=offscreen
.venv\Scripts\python -m pytest tests %*
exit /b %errorlevel%
