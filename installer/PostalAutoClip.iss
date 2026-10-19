#ifndef AppVersion
  #define AppVersion "0.9.0-beta"
#endif

[Setup]
AppId={{8F6A7371-9A13-48E4-9AF3-5C85C2EEED89}
AppName=Postal AutoClip Beta
AppVersion={#AppVersion}
AppPublisher=Postal AutoClip
DefaultDirName={localappdata}\Programs\Postal AutoClip
DefaultGroupName=Postal AutoClip
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=output
OutputBaseFilename=PostalAutoClip-Beta-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\PostalAutoClip.exe
CloseApplications=yes
RestartApplications=no
DisableProgramGroupPage=yes

[Files]
Source: "..\dist\PostalAutoClip\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Postal AutoClip"; Filename: "{app}\PostalAutoClip.exe"
Name: "{autodesktop}\Postal AutoClip"; Filename: "{app}\PostalAutoClip.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Run]
Filename: "{app}\PostalAutoClip.exe"; Description: "Launch Postal AutoClip"; Flags: nowait postinstall skipifsilent

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    MsgBox('Postal AutoClip was removed. Your creator data was intentionally kept in %LOCALAPPDATA%\PostalAutoClip so clips, learning history, settings, and account tokens are not destroyed by uninstalling or updating the app.', mbInformation, MB_OK);
end;
