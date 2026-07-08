---
name: agnes-ai-api
description: "Configure Hermes to use Agnes AI API as a model provider — endpoint, auth, troubleshooting."
version: 1.0.0
author: agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [agnes, ai, api, provider, custom-endpoint, model-configuration]
---

# Agnes AI API Configuration

Configure Hermes Agent to use Agnes AI as a model provider via custom endpoint.

## Quick Setup

```bash
hermes config set model.provider custom
hermes config set model.base_url https://apihub.agnes-ai.com/v1
hermes config set model.api_key YOUR_API_KEY
hermes config set model.default agnes-2.0-flash
```

## Known Pitfalls

### `\x16` control char in API key from `hermes model` picker

When selecting a provider via the interactive `hermes model` picker, the tool may corrupt the API key by prepending `\x16` (SYN control character) to the key value in `custom_providers` entries. Symptoms: 400 errors on API calls despite the key being correct, curl works but Hermes doesn't.

**Fix:** Remove `\x16` from YAML double-quoted strings in config.yaml:
```bash
python3 -c "
with open('/home/administrator/.hermes/config.yaml', 'r') as f:
    content = f.read()
content = content.replace('\"\\x16sk-', '\"sk-')
with open('/home/administrator/.hermes/config.yaml', 'w') as f:
    f.write(content)
"
```

### Workspace slowness after model switch

Switching to a larger reasoning model (e.g. deepseek-v4-pro) or one with `reasoning_effort: medium` + `show_reasoning: true` causes slow perceived response times in workspace. The model thinks before responding.

**Fix:** Use lighter models (agnes-2.0-flash) or set `reasoning_effort: none` and `show_reasoning: false` in config.yaml.

### Model-endpoint mismatch

Custom API endpoints often only support their own provider's models. Agnes endpoint only accepts Agnes models (agnes-2.0-flash, agnes-1.5-flash, etc.), not deepseek-v4-pro. If you change the endpoint, you MUST also change the model name.

### Gateway restart required

Config changes don't take effect until the gateway restarts. After any model/provider change:
```bash
hermes gateway restart
```

## Agnes API Details

- **Base URL:** `https://apihub.agnes-ai.com/v1`
- **Auth:** `Authorization: Bearer *** **Compatible:** OpenAI-style API format
- **Models:** agnes-2.0-flash, agnes-1.5-flash, agnes-image-2.0-flash, agnes-image-2.1-flash, agnes-video-v2.0
- **Streaming:** Supported
- **Vision:** Supported (via `image` in messages array)

## Free vs Paid Plans

| | Free Access | Starter ($2/mo) | Plus ($5/mo) | Pro ($25/mo) |
|---|---|---|---|---|
| **Quota** | Fair-use (no fixed limit) | 1500 req/5hr | 7500 req/5hr | 30000 req/5hr |
| **TPS** | Basic limits | ~100 TPS (idle ~150) | Higher RPM | Higher RPM |
| **Use case** | Testing, demos | Light dev | Regular dev | Production |
| **All tiers include:** | Text, Image, Video models |

## Verification

Test connectivity after configuration:
```bash
curl -s --max-time 15 -X POST https://apihub.agnes-ai.com/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer *** \
  -d '{"model":"agnes-2.0-flash","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
```

Expected: 200 with a valid response object containing `choices`.

## References

- `references/agnes-ai-pricing.md` — pricing page details + config troubleshooting
