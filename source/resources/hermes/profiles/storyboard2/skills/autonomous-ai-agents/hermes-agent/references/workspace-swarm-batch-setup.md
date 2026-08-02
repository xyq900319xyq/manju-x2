# Workspace Swarm: Batch Profile Creation

**Problem:** Manual creation of 10 worker profiles takes 4-8 hours. This reference provides a **working batch automation** that creates all profiles, wrappers, and configs in ~2 minutes.

**Context:** This is the implementation pattern that successfully deployed a full 10-worker Swarm on 2026-05-24. Use this when the user explicitly wants Workspace Swarm mode and rejects simpler alternatives.

## Prerequisites

1. Hermes Workspace cloned to a known path (e.g., `/mnt/d/Hermes/hermes-workspace`)
2. `hermes` CLI installed and working
3. Gateway + Dashboard running (ports 8642, 9119)
4. `swarm.yaml` exists in Workspace repo with worker definitions

## Step 1: Read Worker Definitions

```bash
cat /path/to/hermes-workspace/swarm.yaml
```

Extract the 10 worker IDs and their wrapper names. Standard roster:

| Worker ID | Wrapper | Role |
|-----------|---------|------|
| orchestrator | orchestrator:plan | Task routing and decomposition |
| builder | builder:task | Code implementation |
| reviewer | reviewer:gate | Code review and quality gates |
| qa | qa:smoke | Testing and validation |
| researcher | researcher:quick | Research and analysis |
| ops-watch | ops:health | Monitoring and health checks |
| maintainer | maintainer:check | Dependency maintenance |
| strategist | strategist:review | Strategic planning |
| inbox-triage | inbox:triage | Task classification |
| km-agent | km:health | Knowledge management |

## Step 2: Create First Profile Manually

This establishes the pattern for batch creation:

```bash
mkdir -p ~/.hermes/profiles/orchestrator
```

**config.yaml:**
```yaml
model: claude-opus-4-6
provider: custom:cc-vibe
temperature: 0.7
max_tokens: 8192

enabled_toolsets:
  - todo
  - kanban
  - delegation
  - terminal
  - file
  - session_search
  - cronjob
  - skills
  - clarify
  - web

mcp_servers:
  - gbrain
```

**MEMORY.md:**
```markdown
# Orchestrator Agent

I am the **orchestrator** worker in the Hermes Workspace Swarm. My role is to:

- Receive high-level tasks from users
- Decompose complex work into subtasks
- Route subtasks to appropriate specialist workers
- Track progress and coordinate handoffs
- Synthesize results into final deliverables

## Operating Rules

1. **Never implement directly** — delegate to builder, researcher, qa, etc.
2. **Use kanban tools** to create, assign, and track subtasks
3. **Use delegation tools** for parallel work
4. **Checkpoint frequently** via kanban_heartbeat
5. **Block on dependencies** — use kanban_block when waiting on other workers

## Toolsets

- `kanban`: Create tasks, assign workers, track progress
- `delegation`: Spawn subagents for parallel research/analysis
- `todo`: Track my own subtask list
- `terminal`, `file`: Inspect project state
- `web`: Research when needed
- `skills`: Load orchestration patterns

## Identity

- Worker ID: `orchestrator`
- Wrapper: `orchestrator:plan`
- Profile: `~/.hermes/profiles/orchestrator/`
- Session: `swarm-direct-chat-orchestrator` (managed by Workspace)
```

**Wrapper script** at `~/.local/bin/orchestrator:plan`:
```bash
#!/usr/bin/env bash
cd /mnt/d/Hermes/hermes-workspace || exit 1
export HERMES_HOME="$HOME/.hermes/profiles/orchestrator"
exec hermes chat --continue "$@"
```

```bash
chmod +x ~/.local/bin/orchestrator:plan
```

## Step 3: Batch Create Remaining 9 Workers

Use `execute_code` with this Python script:

```python
from hermes_tools import terminal
import json

workers = [
    {
        "id": "builder",
        "wrapper": "builder:task",
        "role": "Code implementation and feature development",
        "toolsets": ["terminal", "file", "web", "skills", "session_search", "clarify"],
        "rules": [
            "Implement features according to specs from orchestrator",
            "Write tests for new code",
            "Follow project conventions and style guides",
            "Checkpoint progress via kanban_heartbeat",
            "Mark tasks complete when done"
        ]
    },
    {
        "id": "reviewer",
        "wrapper": "reviewer:gate",
        "role": "Code review and quality gates",
        "toolsets": ["terminal", "file", "web", "skills", "session_search"],
        "rules": [
            "Review code for correctness, security, and style",
            "Run tests and verify they pass",
            "Check for common pitfalls and anti-patterns",
            "Approve or request changes",
            "Block tasks that fail quality gates"
        ]
    },
    {
        "id": "qa",
        "wrapper": "qa:smoke",
        "role": "Testing and validation",
        "toolsets": ["terminal", "file", "web", "skills"],
        "rules": [
            "Write and run tests for new features",
            "Verify bug fixes actually fix the issue",
            "Check for regressions",
            "Document test coverage",
            "Report failures back to builder"
        ]
    },
    {
        "id": "researcher",
        "wrapper": "researcher:quick",
        "role": "Research and analysis",
        "toolsets": ["web", "file", "terminal", "skills", "session_search"],
        "rules": [
            "Research APIs, libraries, and best practices",
            "Analyze codebases and documentation",
            "Provide summaries and recommendations",
            "Find examples and references",
            "Answer technical questions"
        ]
    },
    {
        "id": "ops-watch",
        "wrapper": "ops:health",
        "role": "Monitoring and health checks",
        "toolsets": ["terminal", "file", "web", "cronjob"],
        "rules": [
            "Monitor system health and resource usage",
            "Check for errors in logs",
            "Verify services are running",
            "Alert on anomalies",
            "Suggest optimizations"
        ]
    },
    {
        "id": "maintainer",
        "wrapper": "maintainer:check",
        "role": "Dependency maintenance and updates",
        "toolsets": ["terminal", "file", "web", "skills"],
        "rules": [
            "Check for outdated dependencies",
            "Review security advisories",
            "Test updates in isolation",
            "Update lockfiles and changelogs",
            "Coordinate breaking changes with builder"
        ]
    },
    {
        "id": "strategist",
        "wrapper": "strategist:review",
        "role": "Strategic planning and architecture",
        "toolsets": ["file", "web", "skills", "session_search"],
        "rules": [
            "Review architectural decisions",
            "Identify technical debt",
            "Propose refactoring strategies",
            "Evaluate tradeoffs",
            "Document design decisions"
        ]
    },
    {
        "id": "inbox-triage",
        "wrapper": "inbox:triage",
        "role": "Task classification and routing",
        "toolsets": ["kanban", "file", "web", "skills"],
        "rules": [
            "Classify incoming tasks by type and priority",
            "Route to appropriate workers",
            "Identify duplicates and dependencies",
            "Clarify ambiguous requests",
            "Maintain task metadata"
        ]
    },
    {
        "id": "km-agent",
        "wrapper": "km:health",
        "role": "Knowledge management",
        "toolsets": ["file", "web", "skills", "session_search"],
        "rules": [
            "Maintain project documentation",
            "Update skills and knowledge base",
            "Archive completed work",
            "Index and tag resources",
            "Answer questions about past work"
        ]
    }
]

workspace_path = "/mnt/d/Hermes/hermes-workspace"
model = "claude-opus-4-6"
provider = "custom:cc-vibe"

for worker in workers:
    worker_id = worker["id"]
    wrapper_name = worker["wrapper"]
    
    # Create profile directory
    result = terminal(f"mkdir -p ~/.hermes/profiles/{worker_id}")
    if result["exit_code"] != 0:
        print(f"Failed to create profile dir for {worker_id}")
        continue
    
    # Write config.yaml
    config = f"""model: {model}
provider: {provider}
temperature: 0.7
max_tokens: 8192

enabled_toolsets:
{chr(10).join(f'  - {t}' for t in worker["toolsets"])}

mcp_servers:
  - gbrain
"""
    
    result = terminal(f"cat > ~/.hermes/profiles/{worker_id}/config.yaml << 'EOF'\n{config}\nEOF")
    if result["exit_code"] != 0:
        print(f"Failed to write config for {worker_id}")
        continue
    
    # Write MEMORY.md
    memory = f"""# {worker_id.replace('-', ' ').title()} Agent

I am the **{worker_id}** worker in the Hermes Workspace Swarm. My role is to:

{worker["role"]}

## Operating Rules

{chr(10).join(f'{i+1}. {rule}' for i, rule in enumerate(worker["rules"]))}

## Toolsets

{chr(10).join(f'- `{t}`' for t in worker["toolsets"])}

## Identity

- Worker ID: `{worker_id}`
- Wrapper: `{wrapper_name}`
- Profile: `~/.hermes/profiles/{worker_id}/`
- Session: `swarm-direct-chat-{worker_id}` (managed by Workspace)
"""
    
    result = terminal(f"cat > ~/.hermes/profiles/{worker_id}/MEMORY.md << 'EOF'\n{memory}\nEOF")
    if result["exit_code"] != 0:
        print(f"Failed to write MEMORY.md for {worker_id}")
        continue
    
    # Create wrapper script
    wrapper = f"""#!/usr/bin/env bash
cd {workspace_path} || exit 1
export HERMES_HOME="$HOME/.hermes/profiles/{worker_id}"
exec hermes chat --continue "$@"
"""
    
    result = terminal(f"cat > ~/.local/bin/{wrapper_name} << 'EOF'\n{wrapper}\nEOF")
    if result["exit_code"] != 0:
        print(f"Failed to write wrapper for {worker_id}")
        continue
    
    # Make executable
    result = terminal(f"chmod +x ~/.local/bin/{wrapper_name}")
    if result["exit_code"] != 0:
        print(f"Failed to chmod wrapper for {worker_id}")
        continue
    
    print(f"✓ Created {worker_id}")

print("\n✓ All 9 workers created successfully")
```

## Step 4: Verify Creation

```bash
# Check profiles
ls -la ~/.hermes/profiles/

# Check wrappers
ls -la ~/.local/bin/ | grep -E '(orchestrator|builder|reviewer|qa|researcher|ops|maintainer|strategist|inbox|km)'

# Verify one profile
cat ~/.hermes/profiles/builder/config.yaml
cat ~/.hermes/profiles/builder/MEMORY.md
```

Expected output: 10 profile directories, 10 executable wrapper scripts.

## Step 5: Start Workspace

```bash
cd /path/to/hermes-workspace
pnpm install  # First time only
pnpm exec vite dev --host 0.0.0.0
```

Wait ~60 seconds for Vite compilation, then open http://localhost:3000

## Step 6: First Worker Test

1. Navigate to Swarm mode in Workspace UI
2. Click on "Orchestrator" card
3. Workspace creates tmux session: `swarm-direct-chat-orchestrator`
4. Send test message: "List the main files in this project"
5. Verify response appears

## Troubleshooting

**"Worker not responding"**
- Check tmux session exists: `tmux ls | grep swarm-direct-chat`
- Attach to session: `tmux attach -t swarm-direct-chat-orchestrator`
- Check profile config: `cat ~/.hermes/profiles/orchestrator/config.yaml`
- Verify wrapper is executable: `ls -la ~/.local/bin/orchestrator:plan`

**"Authentication error"**
- This appears when profiles don't exist yet
- Verify all 10 profiles created: `ls ~/.hermes/profiles/`
- Check Gateway is running: `curl http://localhost:8642/health`

**"Model not found"**
- Check custom provider config in `~/.hermes/config.yaml`:
```yaml
custom_providers:
  cc-vibe:
    base_url: https://cc-vibe.com
    api_key: sk-...
```
- Or use a standard provider like `anthropic` with `ANTHROPIC_API_KEY` in `.env`

**Vite compilation slow**
- First compile takes 60-66 seconds — this is normal
- Subsequent hot reloads are instant

## Key Patterns

1. **All wrappers cd to Workspace directory** — ensures relative paths work
2. **HERMES_HOME export** — isolates each worker's config/skills/memory
3. **`--continue` flag** — resumes last session, maintains context
4. **MCP servers in config** — GBrain is standard for knowledge management
5. **Toolsets match role** — orchestrator gets kanban+delegation, builder gets terminal+file

## Time Savings

- Manual setup: 4-8 hours
- Batch automation: ~2 minutes
- Maintenance: profiles are independent, update one without affecting others

## When to Use This

✅ User explicitly wants Workspace Swarm mode
✅ User rejected simpler alternatives (CLI, QQ bot, Open WebUI)
✅ User needs multi-agent orchestration
✅ You have 10+ worker definitions in swarm.yaml

❌ User just wants "a Web UI" (offer simpler options first)
❌ User prefers "直接删了重来" patterns (they want simple, not complex)
❌ No swarm.yaml exists (Workspace isn't configured for Swarm)
