; installer.iss — Inno Setup script for the Zara AI Assistant
;
; Compile with:
;     ISCC.exe packaging\installer.iss
; or run the whole pipeline with:
;     python packaging\build.py
;
; Produces dist\ZaraSetup.exe. It packages the PyInstaller output at
; dist\ZaraAI\ (built from packaging\zara.spec), installs it under
; {autopf}\Zara AI, and creates Start Menu + desktop shortcuts and an
; uninstaller.
;
; Requires Inno Setup 6.3 or newer (for the "x64compatible" architecture
; identifiers). Download: https://jrsoftware.org/isdl.php
;
; Two details are specific to Zara and easy to get wrong:
;
;   * The app stores its config, memory and logs inside its own folder
;     (config\api_keys.json, memory\, uploads\). {autopf} is Program Files,
;     which a standard user cannot write to, so the installer grants write
;     permission on those three data folders — and only those. The app's
;     program files (the .exe, the DLLs, the Qt plugins) stay read-only, which
;     is what stops an unprivileged user from tampering with them.
;
;   * It is a PyInstaller onedir build with a flat layout, so the folder holds
;     the .exe plus a lot of DLLs, Qt plugins and the bundled browser. The whole
;     tree is installed as-is.

#define MyAppName        "Zara AI"
#define MyAppVersion     "1.0.0"
#define MyAppPublisher   "Zara AI"
#define MyAppURL         "https://github.com/rustamaliabro131/Zara-Version-1.0"
#define MyAppExeName     "ZaraAI.exe"
#define MyAppId          "{{2AB8B906-1DB4-4134-A530-FA5085AA367D}"
; One level up from packaging\ is the repo root, which holds dist\.
#define SourceRoot       ".."
#define DistDir          SourceRoot + "\dist\ZaraAI"

[Setup]
; AppId identifies the app for upgrades and uninstall. It must never change, or
; a new version would install alongside the old one instead of replacing it.
AppId={#MyAppId}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; {autopf} resolves to Program Files on a 64-bit install, or Program Files (x86)
; otherwise, and honours a portable/redirected Program Files location.
DefaultDirName={autopf}\Zara AI
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
AllowNoIcons=yes
LicenseFile={#SourceRoot}\LICENSE
InfoBeforeFile={#SourceRoot}\packaging\BEFORE_INSTALL.txt

; 64-bit only: the bundle carries 64-bit Qt and Playwright binaries.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Single file, compressed.
OutputDir={#SourceRoot}\dist
OutputBaseFilename=ZaraSetup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile={#SourceRoot}\config\zara.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}

; The payload is large; give the wizard a sane minimum and no splash flicker.
MinVersion=10.0
PrivilegesRequired=admin
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
      GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The entire PyInstaller onedir tree: the EXE, all DLLs, Qt plugins, assets,
; the actions\ and plugins\ source folders, and the bundled browser.
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
; The three folders the app writes to at run time. Permissions: users-modify
; grants BUILTIN\Users modify rights that inherit to subdirectories, so a
; standard user can save the API key, memory and uploads without elevation.
; Program files elsewhere under {app} stay read-only on purpose.
Name: "{app}\config";  Permissions: users-modify
Name: "{app}\memory";  Permissions: users-modify
Name: "{app}\uploads"; Permissions: users-modify

[Icons]
Name: "{group}\{#MyAppName}";           Filename: "{app}\{#MyAppExeName}"; \
      IconFilename: "{app}\config\zara.ico"; Comment: "{#MyAppName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}";     Filename: "{app}\{#MyAppExeName}"; \
      IconFilename: "{app}\config\zara.ico"; Tasks: desktopicon

[Run]
; Offer to launch Zara when the wizard finishes.
Filename: "{app}\{#MyAppExeName}"; \
    Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Runtime data the app created inside its own folder. The uninstaller removes
; files it installed by itself; these are generated at run time, so they are
; named explicitly. Removing them keeps the app folder clean.
Type: filesandordirs; Name: "{app}\config\api_keys.json"
Type: filesandordirs; Name: "{app}\config\errors.log"
Type: filesandordirs; Name: "{app}\config\certs"
Type: filesandordirs; Name: "{app}\memory\long_term.json"
Type: filesandordirs; Name: "{app}\memory\*.db"
Type: filesandordirs; Name: "{app}\uploads"
Type: filesandordirs; Name: "{app}\startup_error.log"
Type: filesandordirs; Name: "{app}\skills\AI-Research-SKILLs\.zara_index.json"
Type: dirifempty;     Name: "{app}\memory"
Type: dirifempty;     Name: "{app}\uploads"
Type: dirifempty;     Name: "{app}"

[Code]
// Zara writes a startup-crash report to startup_error.log in the app folder
// root. That folder is read-only by design, so the file is created here and
// given modify rights on that single file — no recursive grant on {app}.
procedure EnsureCrashLogWritable();
var
  LogPath: String;
  ResultCode: Integer;
begin
  LogPath := ExpandConstant('{app}\startup_error.log');
  if not FileExists(LogPath) then
  begin
    if not SaveStringToFile(LogPath, '', False) then
      Exit;
  end;
  // Grant the installing user modify on just this file. No /T: nothing else
  // under {app} is touched.
  Exec('icacls.exe',
       '"' + LogPath + '" /grant *S-1-5-32-545:M',
       '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    EnsureCrashLogWritable();
end;
