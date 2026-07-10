---
name: docker-compose-deployment
description: Deploy Docker Compose applications on Windows hosts with resource constraints — disk space, WSL, registry mirrors, and service debugging.
---

# Docker Compose Deployment on Windows

Deploy and debug `docker compose` services on a Windows host, especially when C: drive is nearly full, WSL is in play, or registry access is limited (GFW).

## Triggers
- User wants to deploy a Docker Compose application on Windows
- Docker Desktop won't start, engine unreachable, or pulls fail with 500
- ghcr.io images won't pull (China / GFW)
- Need to download + install Docker Desktop to a non-C: drive

## Workflow

### 1. Assess disk space first
```powershell
Get-PSDrive C, D | Select-Object Name, Used, Free
```
Docker Desktop setup (~600MB) + WSL vhdx growth + images need space. If C: < 5GB free, **install to D:**.

### 2. Download and install Docker Desktop to D: drive
```powershell
# Download to D: (not C:)
Invoke-WebRequest -Uri 'https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe' `
  -OutFile 'D:\Downloads\DockerDesktopInstaller.exe'

# Install to D:
Start-Process -FilePath 'D:\Downloads\DockerDesktopInstaller.exe' `
  -ArgumentList 'install --accept-license --installation-dir="D:\Program Files\Docker"' -Wait
```

### 3. Start Docker Desktop and wait for engine
```powershell
Start-Process 'D:\Program Files\Docker\Docker Desktop.exe'
# Then poll until engine is ready:
D:\Program Files\Docker\resources\bin\docker.exe info
```

### 4. Docker CLI from WSL — fix PATH
Docker Desktop's CLI lives at `D:\Program Files\Docker\resources\bin`. Add it when running from WSL:
```bash
export PATH="D:\Program Files\Docker\resources\bin:$PATH"
# Or in PowerShell:
$env:PATH = "D:\Program Files\Docker\resources\bin;$env:PATH"
```
Also fix `docker-credential-desktop.exe` by adding the same dir to PATH — the `credsStore: "desktop"` in `~/.docker/config.json` requires it.

### 5. ghcr.io mirror for China (GFW)
`ghcr.io` is often blocked. Use the proxy mirror:
```bash
# Pull via proxy
docker pull ghcr.dockerproxy.com/saturndec/waoowaoo:latest

# Tag so docker-compose finds it
docker tag ghcr.dockerproxy.com/saturndec/waoowaoo:latest ghcr.io/saturndec/waoowaoo:latest
```
Docker Hub (`docker.io`) usually works directly. Only `ghcr.io` needs the proxy.

### 6. Clean up Docker leftovers after uninstall
```powershell
Remove-Item -Recurse -Force 'C:\Program Files\Docker' -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force 'C:\ProgramData\Docker' -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\Docker" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\DockerDesktop" -ErrorAction SilentlyContinue
```

### 7. Accessing services from WSL
Containers running in Docker Desktop are accessible from WSL at `localhost:<port>`.

### 8. Long-running pulls — use background with notify
Image pulls can take minutes. Use `background=true` + `notify_on_complete=true` for pulls, builds, and `docker compose up -d`.

## Pitfalls
- **C: drive full**: Docker Desktop silently fails to install, `Invoke-WebRequest` fails mid-download. Always check disk before starting.
- **Docker Desktop installer needs correct path**: `D:\Program Files\Docker\Docker\Docker Desktop.exe` vs `D:\Program Files\Docker\Docker Desktop.exe` — verify the actual path with `Get-ChildItem`.
- **PowerShell escaping in bash**: Backticks, `$`, and quotes get mangled when passing PS commands through bash. Write PS scripts to `/mnt/c/Windows/Temp/` and run via `powershell.exe -File`.
- **BusyBox `find`/`grep` limitations inside containers**: No `grep -P`, no `sed -i` without argument. Use Python for file operations or `docker cp` + local processing.
- **Credential store error**: If you see `error getting credentials - exec: "docker-credential-desktop.exe": executable file not found`, the Docker bin directory is missing from PATH. See step 4.
