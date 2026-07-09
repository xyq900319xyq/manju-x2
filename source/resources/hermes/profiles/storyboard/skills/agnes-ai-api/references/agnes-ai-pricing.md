## Session: Agnes AI Model Configuration & Troubleshooting

**Date:** 2026-06-14
**Session ID:** current

### Problem
- User configured custom provider `Apihub.agnes-ai.com` → `agnes-2.0-flash`
- Gateway kept returning 400 because `hermes model` interactive picker corrupted the API key with `\x16` prefix
- Workspace chat was slow due to `deepseek-v4-pro` + `reasoning_effort: medium` + `show_reasoning: true`

### Steps Taken
1. Read Agnes AI docs from `https://agnes-ai.com/doc/cid2` to extract endpoint and model name
2. Ran `hermes config set` commands to configure custom provider
3. Tested API with curl → worked (top-level config was clean)
4. Tested API via Python requests → got 400
5. Diagnosed: `hermes model` picker wrote `\x16sk-` prefix to custom_providers entry
6. Fixed: Python script replaced `"\\x16sk-` with `"sk-` in config.yaml
7. Verified: Python test → 200 OK

### Root Cause
`hermes model` interactive picker has a bug where it prepends `\x16` (SYN control character) to API keys in `custom_providers` entries when the user selects a saved provider. This causes API auth to fail silently — the key looks correct in the file but the YAML parser includes the `\x16` as part of the string value.

### Fix
```python
with open('/home/administrator/.hermes/config.yaml', 'r') as f:
    content = f.read()
content = content.replace('"\\x16sk-', '"sk-')
with open('/home/administrator/.hermes/config.yaml', 'w') as f:
    f.write(content)
```
