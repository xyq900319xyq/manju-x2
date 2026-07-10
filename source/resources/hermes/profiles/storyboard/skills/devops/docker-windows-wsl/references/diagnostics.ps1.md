# Docker Desktop Disk Diagnostics (PowerShell)

Run these from WSL via `powershell.exe -ExecutionPolicy Bypass -File <path>`.

## 1. Check Docker installation and VHDX sizes

```powershell
$ErrorActionPreference = "SilentlyContinue"

Write-Host "=== WSL 发行版 ==="
wsl --list --verbose

Write-Host "`n=== 磁盘空间 ==="
Get-PSDrive C, D | Select-Object Name, Used, Free | Format-List

Write-Host "=== Docker VHDX 文件 ==="
$paths = @(
    "$env:LOCALAPPDATA\Docker\wsl\disk"
    "$env:LOCALAPPDATA\Docker\wsl\main"
    "$env:USERPROFILE\AppData\Local\Docker\wsl"
)
foreach ($base in $paths) {
    Get-ChildItem -Path $base -Recurse -Filter "*.vhdx" -ErrorAction SilentlyContinue | ForEach-Object {
        $sizeGB = [math]::Round($_.Length / 1GB, 1)
        Write-Host "$($_.FullName)  -  ${sizeGB}GB"
    }
}
```

## 2. Find Docker Desktop install location

```powershell
Get-ChildItem 'D:\Program Files\Docker', 'C:\Program Files\Docker' -Recurse -Filter 'Docker Desktop.exe' -ErrorAction SilentlyContinue | Select-Object FullName
```

## 3. Launch Docker Desktop from non-default location

```powershell
Start-Process 'D:\Program Files\Docker\Docker Desktop.exe'
```

## 4. Wait for Docker Engine (polling loop)

```powershell
$docker = 'D:\Program Files\Docker\resources\bin\docker.exe'
for ($i=1; $i -le 30; $i++) {
    $result = & $docker info 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host 'Docker Engine is READY!'
        & $docker version --format '{{.Server.Version}}'
        exit 0
    }
    Write-Host "Waiting... ($i/30)"
    Start-Sleep 3
}
Write-Host 'TIMEOUT: Docker Engine did not start'
exit 1
```

## 5. Pull and up with correct PATH (fix docker-credential-desktop)

```powershell
$env:PATH = 'D:\Program Files\Docker\resources\bin;' + $env:PATH
$docker = 'D:\Program Files\Docker\resources\bin\docker.exe'
Set-Location D:\project
& $docker compose pull
# After pull succeeds:
& $docker compose up -d
```

## 6. Clean up old Docker Desktop leftovers

```powershell
Remove-Item -Recurse -Force 'C:\Program Files\Docker' -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force 'C:\ProgramData\Docker' -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\Docker" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$env:USERPROFILE\AppData\Roaming\Docker" -ErrorAction SilentlyContinue
```

## 7. Install Docker Desktop to D drive

```powershell
# Download first
$ProgressPreference = 'SilentlyContinue'
New-Item -ItemType Directory -Path 'D:\Downloads' -Force | Out-Null
Invoke-WebRequest -Uri 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe' -OutFile 'D:\Downloads\Docker Desktop Installer.exe'

# Install to D drive
New-Item -ItemType Directory -Path 'D:\Program Files\Docker' -Force | Out-Null
Start-Process -FilePath 'D:\Downloads\Docker Desktop Installer.exe' -ArgumentList 'install --accept-license --installation-dir=\"D:\Program Files\Docker\"' -Wait
```
