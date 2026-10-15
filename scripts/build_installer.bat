@echo off
rem Builds the app (PyInstaller) and then the Windows installer with Inno Setup 6.
setlocal
cd /d "%~dp0.."
set ISCC=
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do if exist %%P set ISCC=%%~P
if "%ISCC%"=="" (
    echo Inno Setup 6 not found. Install it: winget install JRSoftware.InnoSetup
    exit /b 1
)
call scripts\build_windows.bat || exit /b 1
"%ISCC%" installer\bookforge.iss || exit /b 1
echo Installer: dist-installer\BookForgeStudio-Setup-0.2.3.exe
exit /b 0
