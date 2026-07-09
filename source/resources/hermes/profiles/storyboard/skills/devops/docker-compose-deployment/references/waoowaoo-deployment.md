# waoowaoo Deployment Reference

## Service stack
```yaml
services:
  mysql:     mysql:8.0          → port 13306
  redis:     redis:7-alpine     → port 16379
  minio:     minio/minio        → ports 19000/19001
  app:       ghcr.io/saturndec/waoowaoo:latest → port 13000
```

## Key config
- Project directory: `D:\waoowaoo\`
- Access: `http://localhost:13000`
- Bull Board admin: `http://localhost:13010` (port 13010 on host → container 3010)
- MySQL credentials: `root / waoowaoo123`, database `waoowaoo`

## API Key Encryption (AES-256-GCM)
API keys in `user_preferences.customProviders` are encrypted:
- **Algorithm**: AES-256-GCM
- **Key derivation**: PBKDF2-SHA256, 100k iterations, salt `waoowaoo-api-key-salt-v1`
- **Master key**: `API_ENCRYPTION_KEY` env var (default: `waoowaoo-opensource-fixed-key-2026`)
- **Storage format**: `iv:authTag:ciphertext` (all hex)

### Python decryption snippet
```python
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SECRET = "waoowaoo-opensource-fixed-key-2026"
SALT = "waoowaoo-api-key-salt-v1"
key = hashlib.pbkdf2_hmac('sha256', SECRET.encode(), SALT.encode(), 100000, 32)

encrypted = "be15bb9ba7c9651ddd449a90a6305b36:b7e6716a618e5d6069f31f3117765512:..."
iv, auth_tag, ct = [bytes.fromhex(p) for p in encrypted.split(':')]
aesgcm = AESGCM(key)
api_key = aesgcm.decrypt(iv, ct + auth_tag, None).decode()
```

## Image Generation Template Debugging
waoowaoo uses `compatMediaTemplate` stored in `user_preferences.customModels` JSON for OpenAI-compatible image generation.

### Template structure
```json
{
  "compatMediaTemplate": {
    "version": 1,
    "mediaType": "image",
    "mode": "sync",
    "create": {
      "method": "POST",
      "path": "/images/generations",
      "contentType": "application/json",
      "bodyTemplate": {
        "model": "{{model}}",
        "prompt": "{{prompt}}",
        "response_format": "url",
        "size": "1792x1024"
      }
    },
    "response": {
      "outputUrlPath": "$.data[0].url",
      "outputUrlsPath": "$.data",
      "errorPath": "$.error.message"
    }
  }
}
```

### Common template errors
| Error | Cause | Fix |
|-------|-------|-----|
| `OPENAI_COMPAT_IMAGE_TEMPLATE_OUTPUT_NOT_FOUND` | API returns `b64_json` not `url` | Add `"response_format": "url"` to bodyTemplate |
| Wrong aspect ratio | Body template has no `size` | Template body doesn't include `{{size}}` — add `"size": "{{size}}"` or hardcode |

### Template variables
- `{{model}}` — model ID
- `{{prompt}}` — the prompt text (with suffixes added by handler)
- `{{size}}` — resolved from `aspectRatioToOpenAISize()` mapping
- `{{aspectRatio}}` — raw ratio string before size conversion (deleted by generator-api.ts before reaching template)

### Size mapping (generator-api.ts)
```typescript
'1:1': '1024x1024',
'16:9': '1792x1024',
'9:16': '1024x1792',
'3:2': '1536x1024',
'2:3': '1024x1536',
```

## Character Image Prompt Assembly
See `character-image-task-handler.ts:148`:
```
prompt = {appearance.description}，{CHARACTER_PROMPT_SUFFIX}，{artStyle prompt}
```

`CHARACTER_PROMPT_SUFFIX` (constants.ts:192): A fixed suffix specifying left-side portrait + right-side three-view layout on white background.

## Art Style System
Art styles live in `constants.ts` ART_STYLES array. Adding a new style requires:
1. Edit source `constants.ts`
2. Patch ALL compiled `.next/` files that contain the ART_STYLES literal (inlined by webpack)
3. Clear webpack cache: `rm -rf /app/.next/cache/webpack/*`
4. Restart container

### UI visibility control
- `CharacterCreationForm.tsx:172`: Art style selector showed only for `mode === 'asset-hub'`. Patched to show for both modes by removing the mode check.
- `CharacterCardActions`: Direct "regenerate" button uses project default art style — no selector. See character-base-mutations.ts → backend API.

## MySQL direct access
```bash
mysql -h 127.0.0.1 -P 13306 -uroot -pwaoowaoo123 waoowaoo
```

## Compiled file patching (Next.js production)
When source changes can't trigger a rebuild in production:
1. Find source file → modify
2. `docker cp` updated file back to container
3. Search for compiled equivalents: `grep -rl 'unique_string' /app/.next/`
4. Patch each compiled file (Python is safer than sed due to quoting issues)
5. Clear cache: `rm -rf /app/.next/cache/webpack/*`
6. Restart: `docker restart waoowaoo-app`

### Key compiled files for waoowaoo
- `713-bd179f380683c389.js` — main constants chunk (ART_STYLES, ratio map)
- `1639-cda4fdf5a43281a5.js` — client-side CharacterCreationForm
- `9555.js` — server-side CharacterCreationForm
- Server route chunks: `/app/.next/server/app/api/novel-promotion/...`, `/app/.next/server/chunks/`

### Patching gotchas
- Minified JS uses single-letter variable names — find context clues (class names, text strings) to identify the right code
- String constants inlined by webpack can't be replaced globally if they also appear as object keys (e.g., `"3:2"` in both ratio constant AND ratio mapping object)
- Prefer hardcoding values in templates (DB) over patching compiled constants when possible
