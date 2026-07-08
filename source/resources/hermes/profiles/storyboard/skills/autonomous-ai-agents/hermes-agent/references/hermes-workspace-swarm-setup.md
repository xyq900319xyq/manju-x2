# Hermes Workspace Swarm Mode Setup

**Context:** Hermes Workspace (https://github.com/outsourc-e/hermes-workspace) is a Web UI for Hermes Agent. It has two modes:

1. **Simple chat mode** — works out of the box, just point at gateway + dashboard
2. **Swarm mode** — multi-agent orchestration system requiring extensive setup

## What Swarm Mode Is

Swarm mode turns Workspace into a **multi-agent control plane** with:
- 10+ specialized Hermes Agent profiles (orchestrator, builder, qa, reviewer, researcher, etc.)
- Persistent tmux sessions for each worker
- Role-based task routing
- Kanban board for work coordination
- Wrapper scripts in `~/.local/bin/`
- Shared skills and MCP servers (typically GBrain)

**This is NOT a simple chat interface.** It's an enterprise-grade multi-agent collaboration system.

## Architecture Requirements

Each worker needs:
1. **Profile** at `~/.hermes/profiles/<workerId>/` with config.yaml, skills, memory
2. **Wrapper script** at `~/.local/bin/<wrapper-name>` (e.g. `builder:task`)
3. **Core skill** named `<workerId>-core` (e.g. `builder-core`)
4. **tmux session** named `swarm-<workerId>`
5. **Entry in swarm.yaml** defining role, tools, skills, model

## Setup Complexity

**Manual setup time:** 4-8 hours for a full 10-worker swarm

**What you need to create:**
- 10 profile directories with isolated configs
- 10 wrapper scripts
- 10+ core skills (one per worker role)
- Shared infrastructure skills (gstack-for-hermes, gbrain, kanban-orchestrator, etc.)
- MCP server configuration (GBrain is heavily used)
- swarm.yaml alignment with all profiles

## When NOT to Use Swarm Mode

**Don't use Swarm if you want:**
- Simple Web chat interface → use Open WebUI, LibreChat, or Chatbox instead
- Single-agent workflow → use `hermes chat` CLI or QQ/Telegram gateway
- Quick setup → Swarm requires hours of configuration

## When to Use Swarm Mode

**Use Swarm if you need:**
- Multiple specialized agents working on different aspects of a project
- Persistent agent sessions that survive across tasks
- Role-based routing (orchestrator delegates to builder, reviewer gates merges, etc.)
- Kanban-style work queue with multi-agent coordination
- Long-running autonomous missions with checkpoints

## Quickstart Path (If You Must)

The official quickstart is at `/mnt/d/Hermes/hermes-workspace/docs/swarm/QUICKSTART.md` but assumes you already have profiles. **There is no automated profile generator.**

Minimal viable swarm (1 worker):

1. Create profile:
```bash
hermes profile create builder
```

2. Configure `~/.hermes/profiles/builder/config.yaml`:
```yaml
model: claude-sonnet-4
provider: anthropic
enabled_toolsets:
  - terminal
  - file
  - web
  - skills
```

3. Create wrapper at `~/.local/bin/builder:task`:
```bash
#!/usr/bin/env bash
cd "$HOME" || exit 1
exec hermes chat --profile builder --continue
```

4. Make executable:
```bash
chmod +x ~/.local/bin/builder:task
```

5. Add to `swarm.yaml`:
```yaml
workers:
- id: builder
  name: Builder
  role: Implementation Agent
  wrapper: builder:task
  profile: builder
  tools: [terminal, file, web, skills]
```

6. Start tmux session:
```bash
tmux new-session -d -s swarm-builder "hermes chat --profile builder --continue"
```

7. Open Workspace UI and use "Add Swarm" dialog to register the worker

**Repeat 7 times for a minimal swarm** (orchestrator, builder, reviewer, qa, researcher, ops-watch, maintainer).

## User Preference Note

**Chinese-speaking users often prefer simpler solutions.** When a user asks for a Web UI and you discover they need Swarm-level complexity, offer:

1. Continue with current method (QQ bot, CLI)
2. Install a simple Web UI (Open WebUI, LibreChat)
3. Full Swarm setup (explain 4-8 hour commitment)

**Do not assume they want the complex option.** The pattern "直接删了重来" (just delete and start over) signals preference for simple, reliable solutions over complex configurations.

## Troubleshooting

**"Authentication error — check your API key"**
- This is a **frontend error message**, not a gateway error
- Workspace expects to talk to workers via tmux + `/api/swarm-direct-chat`
- The error appears when no workers are configured
- **Solution:** Either set up workers OR use a different Web UI

**"Worker not found"**
- Profile doesn't exist at `~/.hermes/profiles/<workerId>/`
- Wrapper script missing or not executable
- tmux session not running

**"Dispatch timeout"**
- Worker received the task but didn't checkpoint in time
- Check `tmux attach -t swarm-<workerId>` to see what it's doing
- Check `~/.hermes/profiles/<workerId>/runtime.json` for status

## Alternative: Dashboard API (Simpler)

Workspace v2 added **dashboard-backed missions** as a fallback when Swarm isn't configured. This uses `hermes dashboard` API endpoints instead of tmux workers. Still requires:
- `hermes dashboard` running on port 9119
- `HERMES_DASHBOARD_URL` set in Workspace `.env`

But **does not require** profiles, wrappers, or tmux sessions. Check Workspace README for "Conductor" feature.

## References

- Workspace repo: https://github.com/outsourc-e/hermes-workspace
- Swarm docs: `/docs/swarm/` in repo
- AGENTS.md: defines the worker contract
- swarm.yaml: source of truth for roster
