---
name: electron-app-analysis
description: Use when analyzing packaged Electron desktop apps to understand their architecture, API endpoints, prompt compilation, data storage, and runtime behavior. Covers asar extraction, SQLite forensics, bundled JS tracing, and proxy-chain mapping.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [electron, reverse-engineering, api, prompts, sqlite, asar, forensics]
    related_skills: [debugging-hermes-tui-commands]
---

# Electron App Analysis & Reverse Engineering

Analyze packaged Electron desktop apps to understand their architecture, API
endpoints, prompt compilation, data storage, and runtime behavior.

## When to Use

- "What does this app send to the API?"
- "How does this Electron app work internally?"
- "Where does this app store its data?"
- "Extract the prompts / API calls from this app"
- User wants to replicate an app's API behavior outside the app
- User wants to analyze an Electron app's source code from a packaged build

## Phase 1: Reconnaissance

### 1.1 App identification
Search the app directory for Electron signatures:
```
search_files pattern="*" target="files" path="/path/to/app/"
```

Indicators: `resources/app.asar`, `resources/app.asar.unpacked/`, `*.pak` files,
`{app-name}.exe` + `resources/` directory, `better-sqlite3` in unpacked node_modules.

### 1.2 Find user data directories

**Windows:**
- `%APPDATA%/{app-name}/` or localized Chinese name
- `%APPDATA%/{app-name}-profiles/default-*/`
- `%LOCALAPPDATA%/Packages/{publisher}*/`

**Search:**
```
find /mnt/c/Users/*/AppData -maxdepth 4 -type d -iname "*{keyword}*"
```

### 1.3 Find runtime databases
Look for SQLite `.db` files. Common names: `runtime.db`, `cache.db`, `storage.db`.
```
find /mnt/c/Users/.../AppData/Roaming -type f -name '*.db'
```

## Phase 2: Source Extraction

### 2.1 Extract app.asar
```
mkdir -p /tmp/app-extract
npx --yes @electron/asar extract "/path/to/resources/app.asar" /tmp/app-extract
```

Extracted structure: `out/renderer/assets/*.js` (all frontend), `out/main/index.cjs`
(main process), `node_modules/` (dependencies).

### 2.2 If open source — use jsDelivr CDN
When git clone fails (China network), pull files individually:
```
curl -sL "https://cdn.jsdelivr.net/gh/{owner}/{repo}@main/path/to/file"
```

For directory listings use GitHub API:
```
curl -sL "https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref=main"
```

## Phase 3: Deep Analysis

### 3.1 Trace API calls in bundled JS
```
search_files pattern="fetch\(|apiBaseUrl|apiKey|Authorization|Bearer|POST|/api/" target="content" path="/tmp/app-extract/out/renderer/assets/"
search_files pattern="chuangwei|memefast|seedance|happyhorse|dashscope" target="content" path="..."
```

### 3.2 Read SQLite runtime database
Copy to /tmp first (WSL NTFS mount issue):
```
cp "/mnt/path/to/runtime.db" /tmp/runtime.db && chmod 644 /tmp/runtime.db
```

Then explore with Python:
```python
import sqlite3, json
conn = sqlite3.connect('/tmp/runtime.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]
for t in tables:
    c.execute(f"PRAGMA table_info({t})")
    print(t, [(col[1], col[2]) for col in c.fetchall()])
    c.execute(f"SELECT * FROM {t} ORDER BY rowid DESC LIMIT 5")
```

### 3.3 Extract prompts from job payloads
```python
c.execute("SELECT job_payload_json FROM studio_run_jobs WHERE job_kind = 'character-image-generation'")
for (payload,) in c.fetchall():
    p = json.loads(payload)
    print(p.get('prompt', ''))
    print(p.get('negativePrompt', ''))
    print(p.get('execution', {}))
```

### 3.4 Reconstruct the prompt compilation pipeline
Read source files that build prompts. Key files:
- `prompt-compiler.ts` — Mustache template engine
- `character-bible.ts` — Character visual trait assembly
- Functions: `buildPromptFromAnchors`, `buildCharacterSheetPrompt`

The pipeline assembles from layers:
1. **basePrompt** — role + name + description prefix
2. **anchorPrompt** — facial features, color hex codes, unique marks
3. **eraPrompt** — time-period clothing styles
4. **contentPrompt** — view types (three-view, expressions, poses, proportions)
5. **whiteBackground** — isolation constraints
6. **styleTokens** — weighted quality/style tags with `:1.2` syntax
7. **detailSuffix** — "detailed illustration, concept art"
8. **negativePrompt** — base negatives + character avoid list + style exclusions

## Phase 4: Deliverables

Present findings clearly:
1. **API architecture diagram** — endpoints, auth method, body format, proxy chain
2. **Complete prompts** — exact text sent, saved as .txt files
3. **Prompt compilation formula** — how user input becomes API prompt
4. **Why direct replication fails** — proxy layers, model mappings, token weights
5. **Working JSON request bodies** — ready for curl/Postman

## Phase 5: Patching Bugs (when applicable)

### 5.1 Identify the fix location
Use `grep -n` to find the exact line number of the problematic code in the
compiled JS. For timeout issues, search for `submitTimeoutMs` or `fetchWithTimeout`.
For model whitelist issues, search for the model set name (e.g. `MEMEFAST_GPT_IMAGE_2_MODELS`).

### 5.2 Apply patches
Use the `patch` tool with `mode='replace'` for targeted edits. Always provide
enough surrounding context to make the match unique. Common patches:

- **Model whitelist**: Add model name to the `Set([...])` and add a variant entry
  to the variant config object with matching resolution/size fields.
- **Timeout values**: Change `6e4` → `18e4` (60s → 180s) in all `submitTimeoutMs`
  lines. Search for ALL occurrences — there are often 2+ (one in
  `submitGridImageRequest`, one in the main image submit function).
- **Polling intervals**: Check `pollInterval` and `maxAttempts` for video/image
  task polling loops.

### 5.3 Proxy endpoint routing fix (chuangwei.cyou-style proxies)
Some apps use middleware proxies that serve non-standard endpoints. When the
proxy expects e.g. `/api/ai/image` but the code calls `/v1/images/generations`,
the fetch fails with "Failed to fetch" (not a timeout). Fix pattern:

```javascript
// Detect the proxy
const isChuangwei = /chuangwei\.cyou/i.test(normalizedBase);

// Override endpoint
const fetchUrl = isChuangwei ? `${normalizedBase}/api/ai/image` : endpoint;

// Override auth (apiKey in body vs Bearer header)
const fetchHeaders = isChuangwei ? { "Content-Type": "application/json" } : {
  "Authorization": `Bearer ${currentApiKey}`,
  ...multipartFormData ? {} : { "Content-Type": "application/json" }
};

// Override body format (camelCase vs snake_case, add provider field)
const fetchBody = isChuangwei ? JSON.stringify({
  prompt: requestBody.prompt,
  negativePrompt: requestBody.negative_prompt || "",
  aspectRatio: requestBody.aspect_ratio || aspectRatio,
  apiKey: currentApiKey,
  provider: "memefast",
  referenceImages: requestBody.image_urls || void 0
}) : (multipartFormData || JSON.stringify(requestBody));

// Override response parsing (camelCase: data.imageUrl not data.url)
if (isChuangwei) {
  if (data.imageUrl && data.status === "completed") return { imageUrl: data.imageUrl };
  if (data.taskId) { /* poll at /api/ai/task/{taskId}?provider=...&type=image&apiKey=... */ }
}
```

**WARNING: Model whitelist side effects**. Adding a model to a whitelist set
(e.g. `MEMEFAST_GPT_IMAGE_2_MODELS`) to fix timeout values also changes the API
endpoint path selection. If the app uses a proxy, the whitelisted model may get
routed to a proxy-incompatible path. Only bump the fallback timeout; do NOT add
models to whitelists unless you verify the full endpoint routing is compatible.

### 5.4 Recover stuck state files
When a task timed out but the API completed, the app's JSON state files show
`status: "failed"` or `gridGenerationStatus: "failed"`. Reset these to enable retry:

```python
g['gridGenerationStatus'] = 'idle'
g['gridGenerationError'] = None
# Also clear any stale partial data
g['gridImageUrl'] = None
g['groupGridAsset'] = None
```

### 5.4 Repack the ASAR (CRITICAL: correct directory)
```bash
# MUST pack from the directory that contains out/ AND node_modules/ AND package.json
cd /tmp/app-extract
npx --yes @electron/asar pack . "/path/to/resources/app.asar"

# Verify structure is correct
npx --yes @electron/asar list "/path/to/resources/app.asar" | head -5
# Expected: /node_modules, /out, /package.json
```

**Wrong**: `npx @electron/asar pack out app.asar` — this produces `/main` at root,
missing `node_modules/` and `package.json`. The app may still launch but lose
native module access.

### 5.5 Verify the fix
```bash
# Extract the repacked asar and grep for the fix
rm -rf /tmp/verify && mkdir /tmp/verify
npx --yes @electron/asar extract app.asar /tmp/verify
grep -c 'gpt-image-2-reverse' /tmp/verify/out/renderer/assets/index-*.js
# Should show >0 occurrences
```

## Common Pitfalls

1. **asar tool name:** Use `npx @electron/asar extract`, not `asar` (npm collision).
2. **SQLite on WSL NTFS:** Copy db to /tmp first; WSL SQLite may fail on mounted drives.
3. **GitHub in China:** Don't rely on `git clone` or raw.githubusercontent.com. Use jsDelivr CDN.
4. **Minified JS:** Don't read linearly — search by unique strings (API paths, endpoint names).
5. **Proxy layers:** Many AI tools route through middleware proxies. Prompt text alone won't replicate results — map the full proxy chain (app → middleware → upstream).
6. **Internal model names:** Models like `gpt-image-2-reverse` may be proxy-internal mappings, not real model IDs. Using them against the upstream API may 404.
7. **Encrypted config:** Some Electron apps use `electron-safe-storage` for API keys. The encrypted payload is a base64 blob that the app decrypts at runtime. You can extract the raw API key from runtime.db job payloads instead.
8. **ASAR repacking directory trap:** `npx @electron/asar pack out app.asar` produces `/main` at root instead of `/out/main`. Always pack from the directory **containing** `out/`, `node_modules/`, and `package.json`: `cd /tmp/app-extract && npx @electron/asar pack . app.asar`. Verify with `@electron/asar list` — you must see `/node_modules`, `/out`, and `/package.json` at root level.
9. **API timeout mismatch by model:** Many apps have model-dependent timeouts. The pattern: `const submitTimeoutMs = isSpecialModel(model) ? 120000 : 60000;`. If the user's model isn't in the whitelist, it gets the short timeout. Fix: add the model to the whitelist set AND bump the fallback.
10. **State file `failed` stuck state:** When an async API call times out at submit (before getting a taskId), the app sets status to `failed` in its JSON state files. The API may still complete on the backend. Recovery: reset the `gridGenerationStatus` / `videoStatus` field from `"failed"` to `"idle"` in the JSON, clear the error message, and let the user retry.

## References

- [moyin-creator-analysis.md](references/moyin-creator-analysis.md) — Complete forensic analysis of 魔因漫创 (Moyin Creator), including API proxy chains, runtime database schema, prompt compilation formulas, identity anchor system, Seedance 2.0 request protocols, and all extracted model registries.
- [moyin-creator-bugs.md](references/moyin-creator-bugs.md) — Known bugs found and fixed: 9-grid board generation 60-second timeout, scene contact sheet result-not-saved. Includes exact patch locations, state recovery procedures, and ASAR repacking verification.

## Verification Checklist

- [ ] app.asar extracted and renderer JS searched for API patterns
- [ ] User data directory found (AppData/Roaming or similar)
- [ ] Runtime SQLite database copied and queried
- [ ] All API endpoints, auth methods, and request body formats documented
- [ ] Complete prompts extracted and validated against source code compilation formula
- [ ] Proxy chain mapped: app → middleware → upstream
- [ ] Differences between direct API use and app-mediated use explained
