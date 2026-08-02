# Hermes Workspace API Reference

Quick-reference for testing a Hermes Workspace deployment end-to-end.

## Architecture

```
Browser → Workspace (localhost:3000)
            ↓ /api/send-stream
          Gateway (127.0.0.1:8642)
            ↓ /v1/chat/completions
          Hermes Agent (model: deepseek-v4-pro, etc.)
```

## Connectivity Test Script

Run in Hermes `execute_code` (Python):

```python
import urllib.request, json

def test_endpoint(url, label, method="GET", headers=None, body=None):
    try:
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(url, data=data, method=method)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

# 1. Gateway health
r1 = test_endpoint("http://127.0.0.1:8642/v1/models",
                    headers={"Authorization": "Bearer $API_SERVER_KEY"})
print("Gateway:", r1.get("data", [{}])[0].get("id") if "data" in r1 else r1)

# 2. Workspace status
r2 = test_endpoint("http://127.0.0.1:3000/api/connection-status")
print("Workspace:", r2.get("status"), r2.get("chatReady"))

# 3. Chat completion
r3 = test_endpoint("http://127.0.0.1:8642/v1/chat/completions",
                    method="POST",
                    headers={"Content-Type": "application/json",
                             "Authorization": "Bearer $API_SERVER_KEY"},
                    body={"model": "deepseek-v4-pro",
                          "messages": [{"role": "user", "content": "hi"}],
                          "stream": False, "max_tokens": 20})
print("Chat:", r3.get("choices", [{}])[0].get("message", {}).get("content"))
```

## Expected /api/connection-status Response

```json
{
  "status": "connected",
  "label": "Connected",
  "health": true,
  "chatReady": true,
  "modelConfigured": true,
  "activeModel": "deepseek-v4-pro",
  "chatMode": "portable",
  "capabilities": {
    "health": true,
    "chatCompletions": true,
    "models": true,
    "streaming": true,
    "sessions": false,
    "skills": false,
    "memory": true,
    "config": false,
    "jobs": true,
    "mcp": false,
    "dashboard": false
  }
}
```

Key signals:
- `status: "connected"` + `chatReady: true` = all good
- `dashboard: false` is expected unless `hermes dashboard` is running
- `sessions: false` without `API_SERVER_KEY` set in `~/.hermes/.env`

## Required Config

| File | Key | Value |
|------|-----|-------|
| `~/.hermes/.env` | `API_SERVER_ENABLED` | `true` |
| `~/.hermes/.env` | `API_SERVER_HOST` | `127.0.0.1` |
| `~/.hermes/.env` | `API_SERVER_PORT` | `8642` |
| `~/.hermes/.env` | `API_SERVER_KEY` | `<secret>` |
| `workspace/.env` | `HERMES_API_URL` | `http://127.0.0.1:8642` |
| `workspace/.env` | `HERMES_API_TOKEN` | `<same secret>` |
| `workspace/.env` | `HERMES_AGENT_PATH` | `/home/<user>/.hermes/hermes-agent` |

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| "Authentication error" in Workspace | `API_SERVER_KEY` not set in `~/.hermes/.env` | Set it + restart gateway |
| Workspace loads but chat hangs | `API_SERVER_ENABLED` not true | Set it + restart gateway |
| "Port 3000 already in use" | Previous instance still running | Check with `ss -tlnp \| grep 3000`; reuse if working |
| Connection status takes 30s+ | First-run probe of dashboard (port 9119) | Wait ~30s, then refresh |
