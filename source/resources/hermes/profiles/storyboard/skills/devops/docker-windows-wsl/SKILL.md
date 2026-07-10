---
name: docker-windows-wsl
description: Docker operations on Windows from WSL — use when Docker is installed on Windows (Docker Desktop) but not available inside the WSL distro. Covers the PowerShell bridge pattern for docker compose, image pulling, and container management.
---

# Docker on Windows via WSL

When Docker Desktop is installed on Windows but not integrated with the WSL distro, all Docker commands must go through PowerShell.

## Quick Start

```bash
# Check if Docker is on Windows
powershell.exe -Command "docker --version"

# Start Docker Desktop if not running (find the exe first)
powershell.exe -Command "Get-ChildItem 'D:\\Program Files\\Docker', 'C:\\Program Files\\Docker' -Recurse -Filter 'Docker Desktop.exe' -ErrorAction SilentlyContinue | Select-Object -First 1 FullName"

# Wait for Docker engine to be ready (~30s)
sleep 30 && powershell.exe -Command "docker info" | head -5

# Run compose from a Windows path (D:\)
powershell.exe -Command "cd D:\\project; docker compose pull; docker compose up -d"
```

## Finding the Docker CLI

Docker Desktop may be installed to `C:\Program Files` or `D:\Program Files`. The CLI binary is at `resources\bin\docker.exe`:

```bash
# Find Docker Desktop root
powershell.exe -Command "Get-ChildItem 'D:\\Program Files\\Docker', 'C:\\Program Files\\Docker' -Directory -ErrorAction SilentlyContinue | Select-Object FullName"

# The CLI is always at: <install_root>\resources\bin\docker.exe
# Example: D:\Program Files\Docker\resources\bin\docker.exe
```

Use the full CLI path + PATH fix to avoid credential helper errors:

```powershell
$env:PATH = '<install_root>\resources\bin;' + $env:PATH
$docker = '<install_root>\resources\bin\docker.exe'
cd D:\project
& $docker compose pull
```

## Key Patterns

### 1. Always use `powershell.exe -Command` — never `cmd.exe /c`
`cmd.exe` from WSL has UNC path issues that cause silent failures. `powershell.exe Start-Process` and `powershell.exe -Command` work reliably.

### 2. Use Windows paths (`D:\folder`) not WSL paths (`/mnt/d/folder`)
Inside `powershell.exe -Command`, paths must be Windows-style. Translate `/mnt/d/foo` → `D:\foo`.

### 3. Use Windows process management for the app
```bash
# Kill Windows processes
taskkill.exe /F /IM "process-name.exe"

# Start Windows processes
powershell.exe -Command "Start-Process 'D:\path\to\app.exe'"
```

### 4. Long-running compose operations
For `docker compose pull` + `up` which can take minutes, run in background with `notify_on_complete`:
```bash
terminal(
    command='powershell.exe -Command "cd D:\\project; docker compose pull 2>&1; docker compose up -d 2>&1"',
    background=True,
    notify_on_complete=True,
    timeout=600
)
```

## China Registry Mirrors

`ghcr.io` and `docker.io` are frequently blocked or slow within China. Always try `ghcr.dockerproxy.com` as a mirror:

```powershell
# Pull from proxy mirror, then re-tag for docker-compose
docker pull ghcr.dockerproxy.com/saturndec/waoowaoo:latest
docker tag ghcr.dockerproxy.com/saturndec/waoowaoo:latest ghcr.io/saturndec/waoowaoo:latest
```

This works because:
1. The proxy mirrors the registry transparently (same image digests)
2. `docker-compose.yml` references `ghcr.io/saturndec/waoowaoo:latest`
3. After `docker tag`, the local image is found under both names

Other mirrors to try if the Docker Hub registry is slow: `docker.m.daocloud.io`, `registry.cn-hangzhou.aliyuncs.com`, or configure Docker Desktop's `registry-mirrors` in `daemon.json`.

## Debugging Docker Compose Apps

### Filter logs for errors
```powershell
# Find all ERROR-level log lines
docker logs <container> 2>&1 | Select-String -Pattern 'ERROR'

# Search for specific error codes with context
docker logs <container> 2>&1 | Select-String -Pattern 'TEMPLATE|generateImage|failed' -Context 0,2
```

### Trace an error to source code
When waoowaoo (or any Node.js/Next.js app) logs an error like `OPENAI_COMPAT_IMAGE_TEMPLATE_OUTPUT_NOT_FOUND at template-image.ts:121`, the stack trace tells you:
- **Which file**: `template-image.ts` — the code path taken
- **Which line**: `121` — the exact assertion that failed
- **Which approach**: "Template" mode means the app sent text to the LLM expecting structured output back. Not the same as direct image generation APIs (`/v1/images/generations`).

### Verify app is responding
```powershell
Invoke-WebRequest -Uri 'http://localhost:13000' -TimeoutSec 10 -UseBasicParsing
```

### Check health status of all services
```powershell
docker compose ps
```

### MySQL column modification via docker exec
When a TEXT column (64KB) overflows, expand it to MEDIUMTEXT (16MB):
```powershell
$bin = 'D:\Program Files\Docker\resources\bin'
$env:PATH = "$bin;$env:PATH"
docker exec waoowaoo-mysql mysql -uroot -p<PASSWORD> <DB> -e "ALTER TABLE <table> MODIFY <column> MEDIUMTEXT;"
```

⚠️ **PowerShell quoting trap**: Double-quotes inside `-e"..."` get mangled by the PowerShell parser. Use single-quoted SQL strings, and test with a `SELECT` first:
```powershell
# Verify before modifying
docker exec waoowaoo-mysql mysql -uroot -p<PASSWORD> <DB> '-e' "SELECT COLUMN_NAME, COLUMN_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='<db>' AND TABLE_NAME='<table>' AND COLUMN_NAME='<col>';"
```

## Pitfalls

- **WSL `docker` command not found**: This is normal. Use `powershell.exe -Command "docker ..."`.
- **Docker Desktop not running**: Check first and start if needed. The engine takes ~30s to initialize.
- **WSL sudo prompts block automation**: When installing dependencies (apt-get, etc.) from terminal() calls, sudo requires interactive authentication. Two approaches: (1) Write a one-line install script for the user to run manually in their terminal, or (2) Use non-interactive alternatives when available (e.g., download pre-built binaries, use user-space package managers like conda/pip). **User preference**: Solve problems autonomously without asking the user to run commands manually. Prioritize workarounds that don't require sudo.
- **`docker-credential-desktop` not in PATH**: When calling docker.exe by full path (e.g. from a non-default install dir), the credential helper isn't found. Fix: prepend `<install_root>\resources\bin` to PATH before running docker commands (`$env:PATH = '<root>\resources\bin;' + $env:PATH`).
- **C drive full — install Docker Desktop to D drive**: Use the installer's `--installation-dir` flag. Download the installer to D drive first. See `references/diagnostics.ps1.md` for the full recipe.
- **Port conflicts**: Docker Desktop on Windows binds to the Windows host. Services on `localhost:13000` are accessible from both Windows browser and WSL curl.
- **Volume paths**: Volumes in docker-compose.yml use relative paths (e.g., `./data:/app/data`). The `cd` to the project directory before `docker compose` is critical.
- **PowerShell execution policy**: When running .ps1 scripts from WSL, use `powershell.exe -ExecutionPolicy Bypass -File <path>`.
- **Long pulls / output overflow**: `docker compose pull` produces massive output. Run in background with `notify_on_complete=True` and `timeout=600`. Use `$ProgressPreference = 'SilentlyContinue'` to reduce noise during downloads.
- **PowerShell special character escaping**: Backticks (`` ` ``) and nested quotes in `powershell.exe -Command` cause silent corruption. Prefer writing PowerShell to a `.ps1` file and running with `-File`. If inline is unavoidable, test carefully — what looks right in WSL may fail in PowerShell's parser.
- **Docker Desktop installer filename**: The official download often saves as `Docker Desktop Installer.exe` (with spaces), not `DockerDesktopInstaller.exe`. Always list the download directory after pulling to confirm the actual filename.

## References

- `references/diagnostics.ps1.md` — Battle-tested PowerShell snippets: disk diagnostics, Docker CLI discovery, engine readiness polling, credential helper fix, install-to-D-drive, and cleanup.
- `references/waoowaoo-deploy.md` — Full deployment reference for waoowaoo on Docker: compose config, port map, GHCR proxy, MySQL column fix, and image-generation error debugging.
- `references/wsl-electron-dev.md` — WSL Electron development setup: WSLg detection, dependency installation (libnss3, fonts), DISPLAY configuration, and autonomous setup strategy for user-preference alignment.
- `references/toonflow-deploy.md` — Toonflow AI short drama tool deployment: clone to D: drive, yarn install/build/start, web UI access, and architecture overview.
