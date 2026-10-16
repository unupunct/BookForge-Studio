; Inno Setup script for BookForge Studio. Build with scripts\build_installer.bat
#define AppName "BookForge Studio"
#define AppVersion "0.3.1"
#define AppExe "BookForgeStudio.exe"

[Setup]
AppId={{6F1D2B7A-3C54-4E0B-9A41-BF0A5D7C2E11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=BookForge Studio
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
; Installs into Program Files for all users, so administrator rights are required.
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist-installer
OutputBaseFilename=BookForgeStudio-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes
ChangesAssociations=yes

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\BookForgeStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.bookforge"; ValueType: string; ValueData: "BookForgeStudio.Project"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\BookForgeStudio.Project"; ValueType: string; ValueData: "BookForge project"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\BookForgeStudio.Project\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExe},0"
Root: HKA; Subkey: "Software\Classes\BookForgeStudio.Project\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent

; User data (%APPDATA%\BookForgeStudio) and projects are intentionally left on uninstall.
