; Inno Setup script: packs dist/osu-coach into one installer .exe (per-user install, no admin rights needed).
;   ISCC.exe /DAppVersion=2.0.0 packaging\installer.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F3C1E2A-8B4D-4C7E-9A51-0C2D7E5B9F14}
AppName=osu! coach
AppVersion={#AppVersion}
AppVerName=osu! coach {#AppVersion}
AppPublisher=DeMotione
DefaultDirName={localappdata}\Programs\osu-coach
DefaultGroupName=osu! coach
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=osu-coach-{#AppVersion}-setup
SetupIconFile=osu-coach.ico
UninstallDisplayIcon={app}\osu-coach.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "..\dist\osu-coach\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; an update replaces the program files completely (your replays, settings and progress live elsewhere)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\osu! coach"; Filename: "{app}\osu-coach.exe"; IconFilename: "{app}\osu-coach.exe"
Name: "{group}\Uninstall osu! coach"; Filename: "{uninstallexe}"
Name: "{userdesktop}\osu! coach"; Filename: "{app}\osu-coach.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\osu-coach.exe"; Description: "Start osu! coach"; Flags: nowait postinstall skipifsilent
