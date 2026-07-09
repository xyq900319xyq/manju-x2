---
name: hermes-workspace-setup
description: "Deploy and troubleshoot Hermes Workspace (Web UI) on WSL with Gateway API connectivity."
version: 1.0.0
category: devops
---

# Hermes Workspace Setup

Deploy the Hermes Workspace Web UI (https://github.com/outsourc-e/hermes-workspace) on WSL, connect it to the Hermes Gateway API, and verify full-stack connectivity.

## Quick Deploy (WSL)

```bash
# 1. Clone to WSL native filesystem (NOT /mnt/d — see pitfall #1)
git clone https://github.com/outsourc-e/hermes-workspace.git ~/hermes-workspace
cd ~/hermes-workspace

# 2. Ensure pnpm is in PATH (Hermes ships its own node)
export PATH="$HOME/.hermes/node/bin:$PATH"

# 3. Install deps
pnpm install

# 4. Configure .env
cat > .env << 'EOF'
HERMES_API_URL=http://127.0.0.1:8642
HERMES_API_TOKEN=<your-gateway-api-server-key>
HERMES_AGENT_PATH=/home/administrator/.hermes/hermes-agent
PORT=3000
HOST=127.0.0.1
EOF

# 5. Ensure Gateway API server is running
# Check: curl http://127.0.0.1:8642/v1/models
# If down: hermes gateway run --replace

# 6. Start Workspace
pnpm run start:dev
# → http://localhost:3000 (WSL2 auto-forwards to Windows)

# 7. (Optional) Start Dashboard Bridge for session history
# Without this, Sessions/Skills/Config/Jobs panels show empty.
# See pitfall #6 for full explanation.
python3 ~/.hermes/skills/devops/hermes-workspace-setup/scripts/hermes-dashboard-bridge.py &
```

## One-Click Windows Launcher

For a double-clickable desktop shortcut that starts Dashboard Bridge + Workspace and opens the browser:

**Step 1 — Create the WSL-side launcher script** (`~/start-workspace.sh`):

```bash
#!/bin/bash
# Kill stale processes, then start bridge + workspace
fuser -k 3000/tcp 2>/dev/null
fuser -k 9119/tcp 2>/dev/null
sleep 1

nohup python3 ~/.hermes/skills/devops/hermes-workspace-setup/scripts/hermes-dashboard-bridge.py \
  > /tmp/dashboard-bridge.log 2>&1 &
echo "Dashboard Bridge started (PID $!)"

cd ~/hermes-workspace
PATH="$HOME/.hermes/node/bin:/usr/local/bin:/usr/bin:/bin"
nohup pnpm run start:dev > /tmp/workspace.log 2>&1 &
echo "Workspace started (PID $!)"
```

Make it executable: `chmod +x ~/start-workspace.sh`

**Step 2 — Create the Windows `.bat` shortcut** on the Desktop:

```bat
@echo off
chcp 65001 >nul
echo Starting Hermes Workspace...
wsl bash ~/start-workspace.sh
timeout /t 6 /nobreak >nul
start http://localhost:3000
```

See `templates/launcher.bat` for the full version with status messages.

**Critical: Desktop path may NOT be `C:\Users\<name>\Desktop\`.** User profiles can be migrated by tools like 360 MoveData to non-standard locations (e.g. `I:\360MoveData\Users\<name>\Desktop\`). Always verify the actual Desktop path before placing files — ask the user or check `ls /mnt/*/Users/` for non-C drives.

## Pitfalls

### 1. NEVER run `pnpm install` on `/mnt/d` (WSL cross-filesystem)

`pnpm install` on a Windows-mounted drive (`/mnt/d`, `/mnt/c`) is **extremely slow** — 5-10× slower than native WSL filesystem due to NTFS translation overhead for thousands of small files. Expect timeouts on projects with 500+ dependencies.

**Fix:** Always clone and install in WSL native filesystem (`~/`, `/home/`). For D: drive access, keep a copy at `/mnt/d/...` with `.env` only, and symlink `node_modules` back or just run from WSL native.

```bash
# Bad: 10+ minutes, may timeout
cd /mnt/d/Hermes/hermes-workspace && pnpm install

# Good: ~1 minute
cd ~/hermes-workspace && pnpm install
```

### 2. pnpm is NOT in system PATH

Hermes Agent ships its own Node.js and pnpm at `~/.hermes/node/bin/`. This directory is NOT in the default PATH. Running `pnpm` or `npx` without it fails with "command not found" or "spawn sh ENOENT".

**Fix:** Always export the PATH before any pnpm/npx command:

```bash
export PATH="$HOME/.hermes/node/bin:$PATH"
```

For permanence, add to `~/.bashrc`:
```bash
echo 'export PATH="$HOME/.hermes/node/bin:$PATH"' >> ~/.bashrc
```

Note: when running from the Hermes `terminal` tool, the environment is sanitized — include `/usr/bin:/bin` in PATH for shell-dependent tools like `npx`:

```bash
PATH="$HOME/.hermes/node/bin:/usr/local/bin:/usr/bin:/bin" pnpm exec vite dev
```

### 3. API_SERVER_KEY must match on both sides

If Gateway has `API_SERVER_KEY=<secret>` in `~/.hermes/.env`, the Workspace `.env` must set `HERMES_API_TOKEN=<same-secret>`. Mismatch causes 403 errors on `/api/send-stream`.

### 4. Port 3000 "already in use"

If a previous Workspace instance wasn't cleanly killed, kill it first:
```bash
pkill -f "vite dev"
```

### 5. curl to port 3000 times out (port IS listening)

`ss -tlnp | grep 3000` shows the port is bound and `pnpm run start:dev` succeeded, but `curl http://127.0.0.1:3000/` returns timeout. This is normal: Vite compiles lazily on the first HTTP request, and curl's default timeout may expire before compilation finishes. Do NOT restart the server — use `ss -tlnp` to confirm the port, then open the browser directly (browser_navigate handles retries).

### 6. Sessions / Skills / Config / Jobs / MCP panels show empty or "No sessions"

The Workspace has a **zero-fork architecture**: the Gateway API (8642) provides chat/completions/models, but a separate **Dashboard service (port 9119)** provides `/api/sessions`, `/api/skills`, `/api/config`, `/api/jobs`, and `/api/mcp`. The Workspace probes both — if the Dashboard on 9119 is unreachable, these panels silently show "No sessions" / "Unavailable" even though all data exists.

Hermes Agent's Gateway only implements OpenAI-compatible endpoints (`/v1/chat/completions`, `/v1/models`, `/v1/runs`, etc.) — it does **NOT** include the Dashboard. Sessions are stored in `~/.hermes/state.db` (SQLite, `sessions` + `messages` tables) and are fully intact.

**Verification that data exists (state.db):**
```bash
python3 -c "
import sqlite3
conn = sqlite3.connect('$HOME/.hermes/state.db')
sessions = conn.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]
messages = conn.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
print(f'Sessions: {sessions}, Messages: {messages}')
# Show 3 most recent
rows = conn.execute('SELECT id, title, source, started_at FROM sessions ORDER BY started_at DESC LIMIT 3').fetchall()
for r in rows:
    print(f'  {r[0][:30]} | {r[1][:50] if r[1] else \"(no title)\"} | {r[2]}')
conn.close()
"
```

**Fix — Dashboard Bridge (preferred):** Run a lightweight Python bridge on port 9119 that reads `state.db` directly and serves the Dashboard API endpoints the Workspace expects. The bridge script is included in this skill at `scripts/hermes-dashboard-bridge.py`.

```bash
# One-line setup and launch:
python3 ~/.hermes/skills/devops/hermes-workspace-setup/scripts/hermes-dashboard-bridge.py &

# Verify:
curl http://127.0.0.1:9119/api/status
# → {"version": "hermes-bridge-1.0.0", "status": "ok"}

curl -s 'http://127.0.0.1:9119/api/sessions?limit=3' | python3 -m json.tool | head -5
# → { "sessions": [...], "total": 20, ... }

# Then restart Workspace (must restart so server-side re-probes):
fuser -k 3000/tcp && sleep 1
export PATH="$HOME/.hermes/node/bin:/usr/local/bin:/usr/bin:/bin"
cd ~/hermes-workspace && pnpm run start:dev &
```

The bridge serves:
- `GET /` — root HTML with `window.__HERMES_SESSION_TOKEN__` (required for Workspace auth)
- `GET /api/status` — probe endpoint (Workspace's `probeDashboard()` checks this)
- `GET /api/sessions?limit=&offset=` — session list from state.db
- `GET /api/sessions/:id` — single session detail
- `GET /api/sessions/:id/messages` — session messages
- `DELETE /api/sessions/:id` — delete session
- `GET /api/sessions/search?q=` — keyword search

**Workaround (no Dashboard):** Use `session_search` tool (terminal or chat) to query past sessions. The chat panel in Workspace still works — start a new conversation and it will create sessions in state.db.

### 7. `wsl bash -c "nohup ... &"` from a `.bat` file kills child processes

When a Windows `.bat` file runs `wsl bash -c "nohup cmd &"`, the WSL session terminates as soon as the `bash -c` command returns, which kills all backgrounded children — `nohup` does NOT prevent this. The processes appear to start but immediately die, leaving empty log files and no listening ports.

**Fix:** Put all service-startup logic in a WSL-resident shell script (`~/start-workspace.sh`), and have the `.bat` call `wsl bash ~/start-workspace.sh`. The script's own `nohup ... &` calls survive because the script runs *inside* the WSL session and returns cleanly after spawning.

```bat
:: BROKEN — processes die silently
wsl bash -c "nohup python3 bridge.py &"

:: CORRECT — script handles backgrounding internally
wsl bash ~/start-workspace.sh
```

## Verification

```bash
# Step 1: Confirm port is listening (reliable, works immediately)
ss -tlnp | grep 3000
# → LISTEN 0 511 0.0.0.0:3000 ... users:(("node",pid=...,fd=...))

# Step 2: Browser navigate to http://localhost:3000
# → Vite serves a splash screen first, then React hydrates
# → Check console for "[vite] connected." and no JS errors

# Gateway API (port check first, then HTTP)
curl http://127.0.0.1:8642/v1/models
# → {"data":[{"id":"hermes-agent",...}]}

# End-to-end chat test (via Python)
python3 -c "
import urllib.request, json
data = json.dumps({'model':'deepseek-v4-pro','messages':[{'role':'user','content':'hi'}],'max_tokens':10}).encode()
req = urllib.request.Request('http://127.0.0.1:8642/v1/chat/completions', data=data,
    headers={'Content-Type':'application/json','Authorization':'Bearer <api-server-key>'})
print(json.loads(urllib.request.urlopen(req).read())['choices'][0]['message']['content'])
"
```

## Architecture

```
Windows Browser → localhost:3000 (WSL2 auto-forward)
                       ↓
              Vite dev server (WSL)
                       ↓                  ↓
              Gateway API (:8642)    Dashboard (:9119)  ← NOT included in Hermes Agent
              /v1/chat/completions   /api/sessions           (Claude/Anthropic service)
              /v1/models             /api/skills
              /v1/runs               /api/config
              /v1/capabilities       /api/jobs
                       ↓              /api/mcp
              Hermes Agent (LLM)
```

| Service | Port | Provider | Covers |
|---------|------|----------|--------|
| Gateway API | 8642 | Hermes Agent | Chat, models, runs, capabilities |
| Dashboard | 9119 | Claude/Anthropic | Sessions, skills, config, jobs, MCP |

Without the Dashboard, Workspace's Sessions/Skills/Config/Jobs/MCP panels remain empty. The Chat panel works fully via Gateway.

- Access from Windows: `http://localhost:3000` — WSL2 forwards automatically
- Workspace is stateless frontend; Gateway manages chat/model routing; Dashboard manages metadata panels
- Sessions data lives in `~/.hermes/state.db` (SQLite) regardless of Dashboard availability
