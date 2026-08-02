#!/bin/bash
# Hermes Workspace one-click launcher (WSL side)
# Called by the Windows Desktop .bat shortcut.
# Do NOT inline these commands in a .bat via `wsl bash -c "nohup ... &"` —
# the WSL session terminates and kills child processes. See pitfall #7.

set -e

# Kill stale processes on target ports
fuser -k 3000/tcp 2>/dev/null || true
fuser -k 9119/tcp 2>/dev/null || true
sleep 1

# Start Dashboard Bridge (port 9119) — required for Sessions/Skills/Config panels
nohup python3 ~/.hermes/skills/devops/hermes-workspace-setup/scripts/hermes-dashboard-bridge.py \
  > /tmp/dashboard-bridge.log 2>&1 &
echo "Dashboard Bridge started (PID $!)"

# Start Workspace dev server (port 3000)
cd ~/hermes-workspace
PATH="$HOME/.hermes/node/bin:/usr/local/bin:/usr/bin:/bin"
nohup pnpm run start:dev > /tmp/workspace.log 2>&1 &
echo "Workspace started (PID $!)"

echo "Done. Wait ~6s for Vite to compile, then open http://localhost:3000"
