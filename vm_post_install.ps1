<#
.SYNOPSIS
  漫剧助手X-2 VM 装后验证脚本

.DESCRIPTION
  装好 Setup.exe 后跑这个脚本,自动验证:
  1. 安装目录结构
  2. EXE 文件存在
  3. hermes 子目录
  4. config 模板
  5. secrets.bin 状态(应不存在,装好没启动)
  6. 启动 EXE,检查 wizard 是否弹
  7. 收集 logs

.EXAMPLE
  PS> .\vm_post_install.ps1
#>

$ErrorActionPreference = "Continue"
$InstallDir = "C:\漫剧助手X-2"

if (-not $env:VM_TEST_RESULTS_DIR) { $env:VM_TEST_RESULTS_DIR = "_vm_test_results" }
$ReportDir = ".\$env:VM_TEST_RESULTS_DIR"
if (-not (Test-Path $ReportDir)) { New-Item -ItemType Directory -Path $ReportDir | Out-Null }

$Report = Join-Path $ReportDir "02_post_install_report.txt"

function Write-Banner($msg) {
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host " $msg" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
}

$Content = @()
$Content += "漫剧助手X-2 VM 装后验证报告"
$Content += "生成时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$Content += "================================================"
$Content += ""

# 1. 安装目录结构
Write-Banner "1. 安装目录结构"
$Content += "## 1. 安装目录检查"
if (-not (Test-Path $InstallDir)) {
    $Content += "ERROR: $InstallDir 不存在 - 可能装失败了"
    $Content | Out-File -FilePath $Report -Encoding UTF8
    Write-Host "ERROR: $InstallDir 不存在" -ForegroundColor Red
    exit 1
}
$Content += "安装目录: $InstallDir (存在 ✅)"

# 关键文件检查
$Files = @(
    "$InstallDir\漫剧助手X-2.exe",
    "$InstallDir\_internal\漫剧助手X-2.exe",
    "$InstallDir\hermes\hermes.exe",
    "$InstallDir\hermes\_internal\hermes.exe",
    "$InstallDir\config\hermes_api.json",
    "$InstallDir\docs\README.md",
    "$InstallDir\unins000.exe"
)
foreach ($f in $Files) {
    $exists = Test-Path $f
    $size = if ($exists) { (Get-Item $f).Length } else { 0 }
    $sizeStr = if ($size -gt 1MB) { "{0:N1} MB" -f ($size / 1MB) } elseif ($size -gt 1KB) { "{0:N1} KB" -f ($size / 1KB) } else { "$size bytes" }
    $Content += "  $(if ($exists) { '✅' } else { '❌' }) $f ($sizeStr)"
}
$Content += ""

# 2. 目录大小
Write-Banner "2. 目录大小"
$DirSize = (Get-ChildItem $InstallDir -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
$Content += "总大小: $([math]::Round($DirSize / 1MB, 2)) MB"

# hermes 目录大小
if (Test-Path "$InstallDir\hermes") {
    $HermesSize = (Get-ChildItem "$InstallDir\hermes" -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
    $Content += "hermes 目录: $([math]::Round($HermesSize / 1MB, 2)) MB"
}
$Content += ""

# 3. secrets.bin 状态
Write-Banner "3. secrets.bin 状态(首次装好应不存在)"
$SecretsBin = "$InstallDir\config\secrets.bin"
if (Test-Path $SecretsBin) {
    $Size = (Get-Item $SecretsBin).Length
    $Content += "存在($Size bytes) - 装之前启动过?正常应该不存在"
} else {
    $Content += "不存在 ✅ - 装好没启动过(预期)"
}
$Content += ""

# 4. 桌面快捷方式
Write-Banner "4. 桌面快捷方式"
$Desktop = [Environment]::GetFolderPath("Desktop")
$Shortcut = "$Desktop\漫剧助手X-2.lnk"
$Content += "桌面快捷方式: $(if (Test-Path $Shortcut) { '存在 ✅' } else { '不存在(可能装时没勾)' })"
$Content += ""

# 5. 开始菜单
Write-Banner "5. 开始菜单"
$StartMenu = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$StartShortcut = Get-ChildItem $StartMenu -Recurse -Filter "漫剧助手X-2*.lnk" -ErrorAction SilentlyContinue
$Content += "开始菜单快捷方式: $(if ($StartShortcut) { "存在 ✅ ($($StartShortcut.Count) 个)" } else { '不存在' })"
foreach ($s in $StartShortcut) {
    $Content += "  - $($s.FullName)"
}
$Content += ""

# 6. 启动 EXE(后台启动,看 wizard 窗口)
Write-Banner "6. 启动 EXE 测 wizard"
$Content += "## 6. EXE 启动测试"

$ExePath = "$InstallDir\漫剧助手X-2.exe"
if (Test-Path $ExePath) {
    $Content += "启动: $ExePath"
    try {
        # 启动并捕获 PID
        $proc = Start-Process -FilePath $ExePath -PassThru -ErrorAction Stop
        $Content += "进程 PID: $($proc.Id)"
        Start-Sleep -Seconds 8
        if ($proc.HasExited) {
            $Content += "状态: 已退出 ❌ - 启动后 8 秒退出,可能崩溃"
            $Content += "退出代码: $($proc.ExitCode)"
        } else {
            $Content += "状态: 运行中 ✅ (8 秒内未退出)"
            # 抓窗口
            $proc.Refresh()
            $Content += "主窗口标题: $($proc.MainWindowTitle)"
            $Content += "主窗口句柄: $($proc.MainWindowHandle)"
            # 等待 5 秒看 wizard
            Start-Sleep -Seconds 5
            $proc.Refresh()
            if ($proc.MainWindowTitle -match "wizard|向导|API") {
                $Content += "  -> 检测到 wizard 窗口 ✅"
            } else {
                $Content += "  -> 当前窗口标题不含 wizard(可能 wizard 在 wizard 内部页或主窗口已开)"
            }
            # 停掉(测试完成)
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
            $Content += "已强制停止 PID $($proc.Id)"
        }
    } catch {
        $Content += "启动失败: $_"
    }
} else {
    $Content += "EXE 不存在,跳过启动测试"
}
$Content += ""

# 7. 收集 logs
Write-Banner "7. 收集 logs"
$LogsDir = "$InstallDir\logs"
if (Test-Path $LogsDir) {
    $LogFiles = Get-ChildItem $LogsDir -ErrorAction SilentlyContinue
    $Content += "logs 目录: $LogsDir (有 $($LogFiles.Count) 个文件)"
    foreach ($lf in $LogFiles) {
        $Content += "  - $($lf.Name) ($($lf.Length) bytes)"
        # 复制到报告目录
        Copy-Item $lf.FullName -Destination $ReportDir -Force -ErrorAction SilentlyContinue
    }
} else {
    $Content += "logs 目录不存在(可能没启动过)"
}
$Content += ""

# 写报告
$Content | Out-File -FilePath $Report -Encoding UTF8

Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  报告已保存: $Report" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""

# 显示结果
Write-Host "总览:"
if (Test-Path "$InstallDir\漫剧助手X-2.exe") {
    Write-Host "  ✅ EXE 存在" -ForegroundColor Green
} else {
    Write-Host "  ❌ EXE 缺失" -ForegroundColor Red
}
if (Test-Path "$InstallDir\hermes\hermes.exe") {
    Write-Host "  ✅ hermes.exe 存在" -ForegroundColor Green
} else {
    Write-Host "  ❌ hermes.exe 缺失" -ForegroundColor Red
}
if (Test-Path "$InstallDir\config\secrets.bin") {
    Write-Host "  ⚠️  secrets.bin 存在(可能装之前启动过?)" -ForegroundColor Yellow
} else {
    Write-Host "  ✅ secrets.bin 不存在(预期)" -ForegroundColor Green
}

Write-Host ""
Write-Host "下一步:"
Write-Host "  1. 看报告 + logs(如果 EXE 启动失败)"
Write-Host "  2. 启动 EXE 手动跑 wizard 6 步(填测试 key)"
Write-Host "  3. 关 EXE,跑 vm_post_install.ps1 第 2 次(验证 secrets.bin 加密)"
Write-Host "  4. 跑 vm_uninstall_check.ps1 测卸载"
Write-Host "  5. 把整个 _vm_test_results 目录发给 dev"
