; 漫剧助手X-2 用户版 Inno Setup 脚本
; 输出: 漫剧助手X-2_v{APP_VERSION}_Setup.exe
;
; 安装目录结构:
;   <install_root>\
;   ├── 漫剧助手X-2.exe
;   ├── _internal\              ← PyInstaller onedir (manju 主体)
;   │   ├── resources\hermes\profiles\storyboard\
;   │   │                       assets/ seedance-prompt/ (各 100+ skills)
;   │   └── ...
;   ├── hermes\                 ← 独立 hermes.exe (Phase 2 产物)
;   │   ├── hermes.exe
;   │   └── _internal\
;   ├── config\hermes_api.json  ← 用户首次启动 wizard 填
;   ├── data\                   ← manju db
;   ├── outputs\                ← 项目数据
;   └── logs\

#define MyAppName "漫剧助手X-2"
#define MyAppVersion "1.1.1"
#define MyAppPublisher "ManjuTools"
#define MyAppURL "https://github.com/xyq900319xyq/manju-x2"
#define MyAppExeName "漫剧助手X-2.exe"

[Setup]
AppId={{B5E6A3F0-1234-4567-8901-ABCDEF123456}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
; 安装到 C:\Program Files\ 需 UAC 提权,改默认到 C:\漫剧助手X-2 (无需管理员)
DefaultDirName=C:\漫剧助手X-2
DisableProgramGroupPage=yes
DisableDirPage=no
LicenseFile=D:\漫剧助手\manju-x2\docs\LICENSE.txt
OutputDir=D:\漫剧助手\manju-x2\release
OutputBaseFilename=漫剧助手X-2_v{#MyAppVersion}_Setup
; v1.0.0 修:icon.ico 缺文件,默认用 Windows 默认图标(不引 SetupIconFile)
; 如需自定义图标,准备 installer\icon.ico 后再加: SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
VersionInfoVersion={#MyAppVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} 安装包
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
MinVersion=10.0
; v1.1.0 一键更新:让 Inno Setup 自动识别并关闭运行中的漫剧助手X-2.exe
; 然后装完后自动重启新版本(配合 main_window._launch_setup_silent 的 /CLOSEAPPLICATIONS)
CloseApplicationsFilter=漫剧助手X-2.exe;manju-x2.exe
CloseApplications=yes
RestartApplications=yes
SetupMutex=漫剧助手X-2_InstanceMutex

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel2=欢迎使用 [name/ver]。本安装包会把漫剧助手X-2 安装到您指定的目录。%n%n首次启动时会引导您填写 API key。

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; PyInstaller onedir 产物 (dist\漫剧助手X-2\*,已包含 hermes\ 子目录)
Source: "D:\漫剧助手\manju-x2\source\dist\漫剧助手X-2\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; 用户版 hermes_api.json 模板(若 dist 里没带,装一份)
Source: "D:\漫剧助手\manju-x2\source\config\hermes_api.json"; DestDir: "{app}\config"; Flags: onlyifdoesntexist
; 文档
Source: "D:\漫剧助手\manju-x2\docs\README.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "D:\漫剧助手\manju-x2\docs\API配置说明.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "D:\漫剧助手\manju-x2\docs\更新日志.md"; DestDir: "{app}\docs"; Flags: ignoreversion
; 卸载前确认
Source: "D:\漫剧助手\manju-x2\docs\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\漫剧助手X-2"; Filename: "{app}\{#MyAppExeName}"
Name: "{commondesktop}\漫剧助手X-2"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{group}\卸载漫剧助手X-2"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,漫剧助手X-2}"; Flags: nowait postinstall skipifsilent

; v1.0.0 修:删除原 [UninstallRun] 的 cmd echo(那行没用),
; 改为 [UninstallDelete] 清理缓存目录(用户数据 config/data/outputs/logs 保留)
[UninstallDelete]
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\cache"

[Code]
// v1.0.0 修:NeedRestart() 默认返回 False(无需重启 Inno),
// 只在旧 EXE 还在跑且用户同意 kill 时才返回 True
function NeedRestart(): Boolean;
var
  ResultCode: Integer;
begin
  Result := False;  // 默认不需要重启 Inno
  if CheckForMutexes('{#MyAppName}_InstanceMutex') then
  begin
    if MsgBox('漫剧助手X-2 正在运行。安装程序将关闭它后继续。是否继续？',
              mbConfirmation, MB_YESNO) = IDYES then
    begin
      // 杀掉旧 EXE
      Exec('taskkill', '/F /IM {#MyAppExeName}', '', SW_HIDE, ewNoWait, ResultCode);
      Sleep(2000);
      // 杀完不需要重启 Inno,只要继续装就行
    end;
  end;
end;
