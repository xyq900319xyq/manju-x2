# Debugging Electron Apps: Asar, State Files, and Compiled Code

Techniques for investigating bugs in packaged Electron applications where the source
runs inside an `app.asar` archive and state is scattered across SQLite databases,
JSON files, and media directories.

---

## Toolchain

```bash
# Extract asar
npx @electron/asar extract app.asar /tmp/extracted

# List asar contents without extracting
npx @electron/asar list app.asar

# Repack after modifications
npx @electron/asar pack /tmp/extracted app.asar
```

## Investigation Layers (ordered by data freshness)

### 1. Runtime SQLite Database

Electron apps often use SQLite (via `better-sqlite3`) for task/job tracking.
Find it in the user data directory:

```
%APPDATA%/<app-name>-profiles/default-*/studio-run/runtime.db   (Windows)
~/.config/<app-name>/studio-run/runtime.db                      (Linux)
~/Library/Application Support/<app-name>/studio-run/runtime.db  (macOS)
```

Key queries:
```sql
-- All tables and their schemas
SELECT name FROM sqlite_master WHERE type='table';
PRAGMA table_info(<table_name>);

-- Recent tasks ordered by creation time
SELECT * FROM studio_run_tasks ORDER BY created_at DESC LIMIT 20;

-- Jobs linked to tasks (JOIN on task_id)
SELECT t.*, j.job_kind, j.job_state
FROM studio_run_tasks t
JOIN studio_run_jobs j ON j.task_id = t.id
ORDER BY t.created_at DESC;
```

**Watch for:**
- Tasks stuck in `running` state after API completed
- `completed` tasks whose `summary_json` lacks the expected result field (e.g., missing `imageUrl`)
- Task types that don't appear at all → the operation may bypass the task runtime

### 2. State JSON Files

Locate project-scoped state files alongside the project data:
```
<project-data-dir>/projects/_p/<uuid>/sclass.json   (S-class / video gen state)
<project-data-dir>/projects/_p/<uuid>/director.json (director state)
<project-data-dir>/projects/_p/<uuid>/scenes.json   (scene data)
<project-data-dir>/projects/_p/<uuid>/characters.json (character data)
```

Check for status fields:
```python
# S-class grid generation status
g['gridGenerationStatus']   # 'idle' | 'generating' | 'completed' | 'failed'
g['gridGenerationError']    # error message if failed
g['gridImageUrl']           # should be set when completed
g['groupGridAsset']         # object with localUrl, httpUrl
```

### 3. Media File Directories

Generated images often download to disk even when the state JSON isn't updated:
```
<project-data-dir>/media/scenes/    (scene concept images, contact sheets, orthographic views)
<project-data-dir>/media/shots/     (individual shot images, S-class board grids)
<project-data-dir>/media/characters/ (character design sheets)
```

**Key pattern:** Filenames encode timestamps: `{epoch_ms}_{random}.png`.
Match against scene/character `createdAt` timestamps (within ~500ms tolerance)
to find unlinked generated images.

```python
# Match PNGs to their scenes by timestamp proximity
for scene in scenes:
    scene_ts = int(scene['id'].split('_')[0])
    best_match = min(pngs, key=lambda p: abs(p.timestamp - scene_ts))
```

### 4. Compiled JavaScript in Asar

**Search approach:**
```bash
# Find the error string to locate the relevant code
grep -n "timed out after" /tmp/extracted/out/renderer/assets/index-*.js

# Trace API call paths
grep -n "api/ai/image\|/v1/images/generations\|Authorization" index-*.js

# Follow function call chains
grep -n "function submitGridImageRequest\|function submitViaChatCompletions" index-*.js
```

**Common patterns to look for:**
- Hardcoded timeout values (`6e4`, `12e4` — 60s, 120s in scientific notation)
- `AbortController` + `setTimeout` pairs for request cancellation
- Endpoint construction: `${baseUrl}/v1/images/generations` vs `${baseUrl}/api/ai/image`
- Auth placement: `Authorization: Bearer ${key}` (header) vs `apiKey` in body
- Response field naming: camelCase (`imageUrl`) vs snake_case (`image_url`)

### 5. IndexedDB / LocalStorage / SessionStorage

LevelDB stores in the user data profile directory. Search for image URLs or grid references:
```bash
grep -a 'gridImage\|imageUrl\|boardRecord' *.ldb *.log
```

## Common Multi-Layer Timeout Bug

When an API proxy (like `chuangwei.cyou`) adds latency between the app and the
real backend, timeouts can fire at multiple layers:

```
Layer 1: fetchWithTimeout$1(endpoint, ..., submitTimeoutMs)     — outer timeout
Layer 2: setTimeout(() => controller.abort(), 6e4)              — AbortController in submitViaChatCompletions
Layer 3: Retry timeouts in polling loops (pollTaskStatus, etc.)
```

**Debugging pattern:**
1. Note the EXACT error message (`"拼图生成请求超时"` vs `"Image generation request timed out"`)
2. Search for that string in the compiled JS
3. Trace the call tree leading to that timeout
4. Check for independent timeout layers in called subroutines

## API Endpoint Mismatch Pattern

Some apps use middleware proxies (chuangwei.cyou, memefast.top) that expect
different endpoints and auth formats than standard OpenAI-compatible APIs:

| Aspect | Standard OpenAI | Chuangwei Proxy |
|--------|----------------|-----------------|
| Image endpoint | `/v1/images/generations` | `/api/ai/image` |
| Text endpoint | `/v1/chat/completions` | `/api/ai/screenplay` |
| Auth | `Authorization: Bearer` header | `apiKey` in request body |
| Image response | `data[0].url` or `data[0].image_url` | `imageUrl` (camelCase) |
| Async response | `data[0].task_id` | `taskId` (camelCase) |
| Poll endpoint | `/v1/images/generations/{id}` | `/api/ai/task/{id}?provider=&type=&apiKey=` |

**Fix pattern:** Add baseUrl detection and path/body/auth overrides:
```javascript
const isProxy = /chuangwei\.cyou/i.test(normalizedBase);
const endpoint = isProxy
  ? `${normalizedBase}/api/ai/image`
  : `${rootBase}/v1/images/generations`;
// ...
if (isProxy) {
  body = JSON.stringify({ prompt, negativePrompt, aspectRatio, apiKey, provider, referenceImages });
}
```

## State Recovery Pattern

When the API completed but the local state files weren't updated:

1. **Backup** the state file before any manual modification
2. Find the generated file in `media/` directories via timestamp matching
3. Set the missing fields in the JSON state:
   - `imageUrl`: `"local-image://scenes/{filename}.png"`
   - `imageStatus`: `"completed"`
   - `gridGenerationStatus`: `"idle"` (reset from `"failed"` for retry)
4. Restart the app (Electron loads state at startup)

## Active Project Identification (CRITICAL)

When the user says "不是这个项目 / you're looking at the wrong project":

**Problem:** Filesystem JSON files (characters.json, scenes.json) may belong to a stale
or different project. The user's actual active project may exist ONLY in `runtime.db`
with NO corresponding JSON files on disk (data stored in IndexedDB or in-memory state).

**Resolution workflow:**
1. First, always check `runtime.db` for project IDs with the most recent tasks:
   ```sql
   SELECT DISTINCT project_id, MAX(created_at) as latest
   FROM studio_run_tasks GROUP BY project_id ORDER BY latest DESC;
   ```
2. Tasks with `status='running'` indicate the user's CURRENT active project
3. Match the project_id from runtime.db against filesystem directories:
   ```bash
   ls workspace-data/projects/_p/<project_id>/
   ```
4. If no filesystem directory exists for the active project_id, the app stores
   its state elsewhere (IndexedDB, SessionStorage, or in-memory). **Don't insist
   the user is wrong** — runtime.db task history is the authoritative source.

**Key insight:** `runtime.db` task records are append-only and survive
project recreation/import. Filesystem JSON files may be orphaned from a
different project session entirely.

## Character Image File Verification

When `local-image://` references appear in task summaries or character data
but generated images lack character appearance:

1. Extract the filename from the reference:
   `local-image://characters/1779123367028_3ye0ev.png` → `1779123367028_3ye0ev.png`

2. Check if the file exists:
   ```bash
   ls workspace-data/media/characters/1779123367028_3ye0ev.png
   ```

3. If file is MISSING but task records exist:
   - The image was generated in a previous session where media files were cleaned
   - The `processReferenceImagesForModel` pipeline will silently drop the reference
   - `referenceImages=[]` will be sent to the API

4. **Fix:** Regenerate the character 定妆照 from within the app's character panel.
   The new file will be written to `media/characters/` and future API calls will
   include valid references.

## SQLite Locking Under WSL

When the Electron app is running, its SQLite database is locked with a WAL file.
Direct reads will fail with "disk I/O error":
```bash
# WRONG — will fail while app is running
sqlite3 "$APPDATA/.../runtime.db" "SELECT ..."
```

**Workaround:** Copy to temp first, then query:
```bash
cp runtime.db /tmp/runtime_copy.db && sqlite3 /tmp/runtime_copy.db "SELECT ..."
```
Note: The copy captures a snapshot — running tasks may show stale status.

## Pitfalls

- **Asar repacking MUST include root-level files** (`package.json`, `node_modules/`)
  if the original asar had them. Use `pack .` from the extraction root, not `pack out/`.
- **Modifying the model registry** (e.g., adding a model to a white-list Set) can
  change the API path routing, breaking proxy compatibility. Prefer timeout/path
  overrides over model reclassification.
- **Multiple timeout declarations** exist for the same operation (outer fetch timeout
  + inner AbortController timeout). Fix ALL of them; fixing one means the other still fires.
- **Silent reference image dropping**: The `processReferenceImagesForModel` function
  uses a transport-policy system (`inline` for Gemini, `hosted` default). When
  character images are referenced by `local-image://` URLs and the underlying files
  don't exist on disk, `readImageAsBase64` fails silently, the reference is skipped
  with no visible error, and `referenceImages=[]` is sent to the API. Generated
  images will lack character appearance guidance. Fix by checking file existence
  before the pipeline or converting to data URLs inline.
- **IndexedDB vs filesystem state mismatch**: Apps using Zustand `persist()` may
  store project state in IndexedDB while the filesystem JSON files are stale from
  a previous project/session. Runtime database (SQLite) is the most reliable source
  for task history. Copy WITH the WAL file: `cp runtime.db target.db && cp runtime.db-wal target.db-wal`.

## WSL-Specific Workflow

When debugging Windows Electron apps from WSL:

### Path Mapping
- Windows `D:\` maps to `/mnt/d/`
- `%APPDATA%` maps to `/mnt/c/Users/<username>/AppData/Roaming/`
- Use `taskkill.exe /f /im` from WSL to kill Windows processes

### ASAR Extraction Performance
- Full extraction of large asar (150MB+) from `/mnt/` paths can exceed 30s timeout
- **Prefer single-file extraction** via `asar.extractFile()` instead of `asar.extractAll()`
- Use `background=true` + `notify_on_complete=true` for repacking operations
- `cp` across `/mnt/` boundaries may time out; verify file size after copy

### Single-File Extraction (Fast)
```bash
cd /tmp && npm install asar
node -e "
const asar = require('./node_modules/asar');
const content = asar.extractFile(
  '/mnt/d/AppName/resources/app.asar',
  'out/renderer/assets/index-XXX.js'
).toString();
require('fs').writeFileSync('/tmp/renderer.js', content);
console.log('Size:', content.length);
"
```

### Minified Bundle Navigation
- Bundles are often single-line or heavily folded; use Python for context extraction:
```python
with open("renderer.js") as f:
    content = f.read()
idx = content.find("functionName(params)")
print(content[idx:idx+4000])
```
- Escape sequences in minified code matter: `\\\\.` in file is `\.` in regex
- Use `repr()` on matched substrings to see exact characters before patching
