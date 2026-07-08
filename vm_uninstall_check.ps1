<#
.SYNOPSIS
  漫剧助手X-2 VM 卸载验证脚本

.DESCRIPTION
  控制面板卸载后跑这个脚本,验证:
  1. 安装目录已删除
  2. 桌面快捷方式已删除
  3. 开始菜单快捷方式已删除
  4. 应用列表中无残留
  5. config/data/outputs 是否保留(预期保留)

.EXAMPLE
  PS> .\vm_uninstall_check.ps1
#>

$ErrorActionPreference = "Continue"

if (-not $env:VM_TEST_RESULTS_DIR) { $env:VM_TEST_RESULTS_DIR = "_vm_test_results" }
$ReportDir = ".\$env:VM_TEST_RESULTS_DIR"
if (-not (Test-Path $ReportDir)) { New-Item -ItemType Directory -Path $ReportDir | Out-Null }

$Report = Join-Path $ReportDir "03_uninstall_report.txt"

function Write-Banner($msg) {
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host " $msg" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
}

$Content = @()
$Content += "漫剧助手X-2 VM 卸载验证报告"
$Content += "生成时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$Content += "================================================"
$Content += ""

$InstallDir = "C:\漫剧助手X-2"

# 1. 安装目录
Write-Banner "1. 安装目录删除检查"
$Content += "## 1. 安装目录"
$Content += "检查: $InstallDir"
if (Test-Path $InstallDir) {
    $Content += "结果: 存在 ❌(预期被卸载器删)"
    $Remaining = Get-ChildItem $InstallDir -Recurse -ErrorAction SilentlyContinue | Measure-Object
    $Content += "残留文件: $($Remaining.Count)"
} else {
    $Content += "结果: 不存在 ✅(卸载器正确清理)"
}
$Content += ""

# 2. 桌面快捷
Write-Banner "2. 桌面快捷方式"
$Desktop = [Environment]::GetFolderPath("Desktop")
$Shortcut = "$Desktop\漫剧助手X-2.lnk"
$Content += "检查: $Shortcut"
$Content += "结果: $(if (Test-Path $Shortcut) { '存在 ❌' } else { '不存在 ✅' })"
$Content += ""

# 3. 开始菜单
Write-Banner "3. 开始菜单快捷方式"
$StartMenu = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$StartShortcut = Get-ChildItem $StartMenu -Recurse -Filter "漫剧助手X-2*.lnk" -ErrorAction SilentlyContinue
$Content += "开始菜单快捷方式残留: $(if ($StartShortcut) { "❌ $($StartShortcut.Count) 个" } else { '0 个 ✅' })"
$Content += ""

# 4. 应用列表
Write-Banner "4. 控制面板 / 设置 应用列表"
$Content += "## 4. 应用列表残留"
$UninstallKeys = @(
    "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*",
    "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\*"
)
$Found = $false
foreach ($key in $UninstallKeys) {
    $items = Get-ItemProperty $key -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "*漫剧助手X-2*" }
    foreach ($i in $items) {
        $Content += "残留注册表项: $($i.DisplayName) ($($i.UninstallString))"
        $Found = $true
    }
}
if (-not $Found) {
    $Content += "应用列表中无残留 ✅"
}
$Content += ""

# 5. 残留文件(预期保留项)
Write-Banner "5. 预期保留的数据(应保留)"
$Content += "## 5. 预期保留(如果用户在 APPDATA 有数据)"
$DataDirs = @(
    "$env:LOCALAPPDATA\manju-x2",
    "$env:APPDATA\manju-x2"
)
foreach ($d in $DataDirs) {
    $exists = Test-Path $d
    $Content += "  $d : $(if ($exists) { '存在(用户数据)' } else { '不存在' })"
}
$Content += ""

# 6. 安装日志(找 Inno Setup 卸载日志)
Write-Banner "6. Inno Setup 卸载日志"
$TmpLogs = Get-ChildItem "$env:TEMP" -Filter "Setup Log*.txt" -ErrorAction SilentlyContinue
$Content += "卸载日志(在 $env:TEMP):"
foreach ($log in $TmpLogs) {
    $Content += "  - $($log.Name) ($($log.Length) bytes)"
    Copy-Item $log.FullName -Destination $ReportDir -Force -ErrorAction SilentlyContinue
}
$Content += ""

# 写报告
$Content | Out-File -FilePath $Report -Encoding UTF8

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  报告已保存: $Report" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "总览:"
if (Test-Path $InstallDir) {
    Write-Host "  ❌ 安装目录未删除" -ForegroundColor Red
} else {
    Write-Host "  ✅ 安装目录已删除" -ForegroundColor Green
}
if (Test-Path $Shortcut) {
    Write-Host "  ❌ 桌面快捷残留" -ForegroundColor Red
} else {
    Write-Host "  ✅ 桌面快捷删除" -ForegroundColor Green
}
if ($StartShortcut) {
    Write-Host "  ❌ 开始菜单残留" -ForegroundColor Red
} else {
    Write-Host "  ✅ 开始菜单清理" -ForegroundColor Green
}
Write-Host ""
Write-Host "下一步:"
Write-Host "  1. 看报告(任何 ❌ 看 Inno Setup 卸载日志)"
Write-Host "  2. 重新装 + 测 C13 覆盖升级"
Write-Host "  3. 把 _vm_test_results 整个目录发给 dev"
