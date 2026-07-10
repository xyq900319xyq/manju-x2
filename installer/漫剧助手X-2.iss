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
#define MyAppVersion "1.1.5.12"
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
OutputBaseFilename=X-2_v{#MyAppVersion}_Setup
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
; v1.1.5.3【用户数据保护】:Excludes 排除 hermes_api.json,防止 ignoreversion
; 覆盖用户填的 API key。line 75 单独用 onlyifdoesntexist 装模板(首次安装时)。
; 之前没 Excludes → 升级后用户 API 配置被模板覆盖,API key 全部丢失。
Source: "D:\漫剧助手\manju-x2\source\dist\漫剧助手X-2\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "hermes_api.json"
; v1.1.5.5【自带 Git Bash 装 hermes 依赖】:PortableGit 64-bit (~50MB) 从
; build_x2.py step 0.5 下的 installer/PortableGit/ 拷到 <install_root>\PortableGit\。
; 装后 hermes 端能调 `bash -c 'cat <file>'`,跟老 software D:\剧本分镜助手\
; 装 hermes 时行为一致(hermes install 脚本自带 PortableGit + 设 HERMES_GIT_BASH_PATH)。
; bash.exe 在 <PortableGit>\bin\bash.exe(PortableGit 实际解压结构:cmd\git.exe + bin\bash.exe + usr\bin\perl\ssh\curl)。
; v1.1.5.5 build 第一版错误地用 MinGit(没 bash),改用 PortableGit(hermes 官方用)。
Source: "D:\漫剧助手\manju-x2\installer\PortableGit\*"; DestDir: "{app}\PortableGit"; Flags: ignoreversion recursesubdirs createallsubdirs
; 用户版 hermes_api.json 模板(只装一次,保留用户填的 API key)
Source: "D:\漫剧助手\manju-x2\source\config\hermes_api.json"; DestDir: "{app}\config"; Flags: onlyifdoesntexist
; 文档
Source: "D:\漫剧助手\manju-x2\docs\README.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "D:\漫剧助手\manju-x2\docs\API配置说明.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "D:\漫剧助手\manju-x2\docs\更新日志.md"; DestDir: "{app}\docs"; Flags: ignoreversion
; 卸载前确认
Source: "D:\漫剧助手\manju-x2\docs\LICENSE.txt"; DestDir: "{app}"; Flags: ignoreversion

[Registry]
; v1.1.5.5【设 HERMES_GIT_BASH_PATH env var】:HKCU\Environment 注册表项,hermes 端
; (tools/environments/local.py:358) 读 `os.environ.get("HERMES_GIT_BASH_PATH")` 找 bash。
; 不设 → hermes 走默认 bash 查找逻辑,Windows 找不到 → 报 "无法读取文件:Git Bash 未安装"。
; PortableGit 实际解压结构是 <PortableGit>\bin\bash.exe (cmd\ 是 git.exe,usr\bin\ 是 perl\ssh\curl)。
; Flags: uninsdeletevalue 卸载时自动清。errorignore flag 在 [Registry] 段不支持
; (v1.1.5.5 build 测试发现),所以不写失败就编译失败 → 写 HKCU 通常 OK,无需 errorignore。
Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "HERMES_GIT_BASH_PATH"; ValueData: "{app}\PortableGit\bin\bash.exe"; Flags: uninsdeletevalue

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
// 只在旧 EXE 还在跑时直接 taskkill 杀掉再装,不弹确认框
function NeedRestart(): Boolean;
var
  ResultCode: Integer;
begin
  Result := False;  // 默认不需要重启 Inno
  if CheckForMutexes('{#MyAppName}_InstanceMutex') then
  begin
    // v1.1.5.10【静默更新修复】:去掉 MsgBox(),直接 taskkill 杀旧 EXE。
    // Inno Setup 6 [Code] 段 MsgBox() 不受 /VERYSILENT /SUPPRESSMSGBOXES 影响,
    // 会强制弹"是否继续"确认框,经常藏在所有窗口后面被 user 忽略,
    // 导致 installer 卡住等 user 点确认 → 装失败,EXE 没换。
    // 改成静默 taskkill + sleep,配合 main_window.py 的 /FORCECLOSEAPPLICATIONS
    // 双保险,确保 Setup.exe 干净替换。
    Exec('taskkill', '/F /IM {#MyAppExeName}', '', SW_HIDE, ewNoWait, ResultCode);
    Sleep(2000);
  end;
end;

// v1.1.5.6【WM_SETTINGCHANGE 广播 - 不实现】:**manju 端核心 fix 是在 spawn hermes 前
// 主动探测 bash 路径**(generators.py `_ensure_hermes_bash_env`,不依赖系统 env var 加载),
// 所以这里**不**调 WM_SETTINGCHANGE 广播。Inno Setup 写 HKCU\Environment 是辅助
// (让用户能在 System Properties 看到 env var + 下次新登录后生效)。
//
// 早期 v1.1.5.6 build 试过 [Code] 段直接 SendMessageTimeoutA,**踩坑**:
//   - PChar('Environment') 报 "Unknown identifier 'PChar'"
//   - Pointer(env_name) 报 "Unknown identifier 'Pointer'"
//   - PAnsiChar(env_name) 报 "Unknown identifier 'PAnsiChar'"
// Inno Setup 6 [Code] 段 Pascal 不支持 WM API 的字符串指针 cast。强行调需要
// LoadDLL + GetProcAddress + 手动 GetMem + StrPCopy,代码量 30+ 行,容易引入其他 BUG。
// 备选方案:不写 [Registry] 段,改用 [Code] 段 Exec('reg.exe', 'add ...') - reg.exe 自己会广播。
// 当前的 [Registry] 段保留是因为它直接、明确、可读(用户能在 regedit 看到)。