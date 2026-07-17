; ============================================================================
;  Inno Setup script - YT -> MP3 Converter
;
;  Bouwt een professionele Windows-installer (Setup.exe) die:
;   - de PyInstaller-output (dist\YT-MP3-Converter\*) installeert
;   - Start Menu- en optioneel Bureaublad-snelkoppelingen aanmaakt
;   - een nette uninstaller registreert (verschijnt in "Programma's en onderdelen")
;   - de gebruiker vraagt of de app na installatie meteen gestart mag worden
;
;  Vereist: Inno Setup 6 (https://jrsoftware.org/isinfo.php) - gratis
;  Bouwen: open dit bestand in Inno Setup en klik "Compile", of via CLI:
;          ISCC.exe installer.iss
; ============================================================================

#define MyAppName "YT -> MP3 Converter"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "Jouw Naam"
#define MyAppExeName "YT-MP3-Converter.exe"
; Vaste GUID zodat updates dezelfde installatie herkennen i.p.v. dubbel te installeren
#define MyAppId "{{B7B2B7A0-6E2B-4B4C-9C2E-YTMP3CONVERTER}"

[Setup]
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Installeert per-user (geen admin-rechten nodig) - prettiger voor eindgebruikers
PrivilegesRequired=lowest
OutputDir=installer_output
OutputBaseFilename=YT-MP3-Converter-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Zet hier je eigen icoon neer als je die hebt (zelfde als in de .spec)
; SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Pakt de volledige PyInstaller-output map (inclusief ffmpeg.exe/ffprobe.exe) in
Source: "dist\YT-MP3-Converter\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Ruimt door de app aangemaakte instellingen/logs mee op bij de-installatie
Type: filesandordirs; Name: "{userappdata}\YT-MP3"
