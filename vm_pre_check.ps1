<#
.SYNOPSIS
  漫剧助手X-2 VM 装前预检脚本

.DESCRIPTION
  在干净 Win10/11 VM 装 Setup.exe 前跑这个脚本,做:
  1. SHA256 校验 Setup.exe 完整性
  2. 系统信息收集(OS / 架构 / RAM)
  3. .NET 版本检查
  4. 写报告到 _vm_test_results\pre_check_report.txt

.EXAMPLE
  PS> .\vm_pre_check.ps1 -SetupExe ".\漫剧助手X-2_v1.0.0_Setup.exe" -ExpectedSha256 "492ddfeea45109f366c318623c46c5f25a040c0b7b2bf2a06fe4a9a32718a1b8"
#>

param(
    [Parameter(Mandatory = $true)]
    [string]$SetupExe,
    [string]$ExpectedSha256 = "492ddfeea45109f366c318623c46c5f25a040c0b7b2bf2a06fe4a9a32718a1b8"
)

$ErrorActionPreference = "Continue"
$ReportDir = ".\$env:VM_TEST_RESULTS_DIR"

if (-not $env:VM_TEST_RESULTS_DIR) { $env:VM_TEST_RESULTS_DIR = "_vm_test_results" }
$ReportDir = ".\$env:VM_TEST_RESULTS_DIR"
if (-not (Test-Path $ReportDir)) { New-Item -ItemType Directory -Path $ReportDir | Out-Null }

$Report = Join-Path $ReportDir "01_pre_check_report.txt"

function Write-Banner($msg) {
    Write-Host ""
    Write-Host "================================================" -ForegroundColor Cyan
    Write-Host " $msg" -ForegroundColor Cyan
    Write-Host "================================================" -ForegroundColor Cyan
}

# 主报告内容
$Content = @()
$Content += "漫剧助手X-2 VM 装前预检报告"
$Content += "生成时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$Content += "================================================"
$Content += ""

# 1. Setup.exe SHA256 校验
Write-Banner "1. SHA256 校验 Setup.exe"
$Content += "## 1. Setup.exe 完整性校验"
$Content += "文件: $SetupExe"
if (-not (Test-Path $SetupExe)) {
    $Content += "ERROR: 文件不存在"
    $Content | Out-File -FilePath $Report -Encoding UTF8
    Write-Host "ERROR: $SetupExe 不存在" -ForegroundColor Red
    exit 1
}
$FileSize = (Get-Item $SetupExe).Length
$Content += "大小: $FileSize bytes"
$ActualSha = (Get-FileHash $SetupExe -Algorithm SHA256).Hash.ToLower()
$ExpectedSha = $ExpectedSha256.ToLower()
$Content += "期望 SHA256: $ExpectedSha"
$Content += "实际 SHA256: $ActualSha"
if ($ActualSha -eq $ExpectedSha) {
    $Content += "结果: PASS ✅"
    Write-Host "SHA256 PASS" -ForegroundColor Green
} else {
    $Content += "结果: FAIL ❌ - 重新下载 Setup.exe"
    Write-Host "SHA256 FAIL! 期望 $ExpectedSha, 实际 $ActualSha" -ForegroundColor Red
    $Content | Out-File -FilePath $Report -Encoding UTF8
    exit 1
}
$Content += ""

# 2. 系统信息
Write-Banner "2. 系统信息"
$Content += "## 2. 系统信息"
$OS = Get-CimInstance Win32_OperatingSystem
$Content += "OS 名称: $($OS.Caption) ($($OS.Version))"
$Content += "OS Build: $($OS.BuildNumber)"
$Content += "架构: $([System.Environment]::Is64BitOperatingSystem)"
$Content += "总 RAM: $([math]::Round($OS.TotalVisibleMemorySize / 1MB, 2)) GB"
$Content += "可用 RAM: $([math]::Round($OS.FreePhysicalMemory / 1MB, 2)) GB"
$Content += "用户名: $env:USERNAME"
$Content += "计算机名: $env:COMPUTERNAME"
$Content += "管理员: $(([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))"
$Content += ""

# 3. .NET Framework 版本
Write-Banner "3. .NET Framework 版本"
$Content += "## 3. .NET Framework"
$NetVersions = @("v4.0.30319", "v3.5", "v3.0", "v2.0.50727")
foreach ($v in $NetVersions) {
    $Path = "C:\Windows\Microsoft.NET\Framework64\$v"
    $Installed = Test-Path $Path
    $Content += ".NET $v : $(if ($Installed) { '已装' } else { '未装' })"
}
$Content += ""

# 4. 现有 Python / hermes 检查(应都不存在,VM 干净)
Write-Banner "4. 干净环境检查(应不装 Python / manju)"
$Content += "## 4. 干净环境检查"
$Checks = @{
    "Python" = "python"
    "manju 安装目录" = "C:\漫剧助手X-2"
    "Inno Setup" = "C:\Program Files (x86)\Inno Setup 6"
    "hermes.exe" = "C:\hermes\hermes.exe"
}
foreach ($k in $Checks.Keys) {
    $p = $Checks[$k]
    $exists = Test-Path $p
    $Content += "$k ($p) : $(if ($exists) { '存在(不符合预期)' } else { '不存在 ✅(VM 干净)' })"
}
$Content += ""

# 5. 杀软检查
Write-Banner "5. 杀软检查"
$Content += "## 5. 防病毒软件"
try {
    $av = Get-CimInstance -Namespace "root\SecurityCenter2" -ClassName "AntiVirusProduct" -ErrorAction SilentlyContinue
    if ($av) {
        foreach ($a in $av) {
            $Content += "- $($a.displayName) (state=$($a.productState))"
        }
    } else {
        $Content += "未检测到第三方杀软(可能只有 Windows Defender)"
    }
} catch {
    $Content += "检测失败(可能权限不够): $_"
}
$Content += ""

# 6. 磁盘空间
Write-Banner "6. 磁盘空间"
$Content += "## 6. 磁盘空间"
$Drives = Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -ne $null }
foreach ($d in $Drives) {
    $FreeGB = [math]::Round($d.Free / 1GB, 2)
    $UsedGB = [math]::Round($d.Used / 1GB, 2)
    $Content += "$($d.Root) : 已用 $UsedGB GB / 可用 $FreeGB GB"
}
$Content += ""

# 写报告
$Content | Out-File -FilePath $Report -Encoding UTF8
Write-Host ""
Write-Host "================================================" -ForegroundColor Green
Write-Host "  报告已保存: $Report" -ForegroundColor Green
Write-Host "================================================" -ForegroundColor Green
Write-Host ""
Write-Host "下一步:"
Write-Host "  1. 看报告内容(如果 FAIL 重新下载 Setup.exe)"
Write-Host "  2. 关杀软实时防护(临时)"
Write-Host "  3. 双击 Setup.exe 装(默认 C:\漫剧助手X-2\)"
Write-Host "  4. 装完跑 vm_post_install.ps1"
