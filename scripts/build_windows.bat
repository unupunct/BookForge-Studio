@echo off
rem Builds dist\BookForgeStudio\BookForgeStudio.exe with PyInstaller and verifies it.
setlocal
cd /d "%~dp0.."
if not exist .venv\Scripts\python.exe (
    python -m venv .venv || exit /b 1
    .venv\Scripts\python -m pip install -r requirements.txt || exit /b 1
)
.venv\Scripts\python -m pip install pyinstaller || exit /b 1
.venv\Scripts\python scripts\generate_templates.py || exit /b 1
.venv\Scripts\python -m PyInstaller --noconfirm --clean bookforge.spec || exit /b 1
echo Verifying the packaged build...
dist\BookForgeStudio\BookForgeStudio.exe --selftest build\selftest || (echo Self-test FAILED & exit /b 1)
echo Build OK: dist\BookForgeStudio\BookForgeStudio.exe
exit /b 0
