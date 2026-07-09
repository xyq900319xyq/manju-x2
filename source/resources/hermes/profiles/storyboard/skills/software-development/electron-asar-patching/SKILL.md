---
name: electron-asar-patching
description: Extract, modify, and repack Electron app.asar archives to fix bugs or change behavior in bundled desktop apps without access to source builds. Covers the full modify-repack-replace-restart cycle, pitfalls with minified JS editing, and project-specific conventions for 魔因漫创 (moyin-creator).
---

# Electron ASAR Patching

Modify Electron desktop applications by extracting the `app.asar` archive, editing the bundled JavaScript, repacking, and restarting the app.

## When to Use

- Need to fix a bug or change behavior in a packaged Electron app
- Can't rebuild from source (no build environment, npm issues, proprietary deps)
- Source is available but you need a quick iteration cycle
- You know what to change in the JS but don't want a full build pipeline

## Workflow

### 1. Extract the asar

```bash
npx @electron/asar extract /path/to/app.asar /tmp/extracted/
```

### 2. Locate the JS to modify

Electron bundles typically put renderer JS under `out/renderer/assets/`:

```bash
ls /tmp/extracted/out/renderer/assets/
# → index-XXXXXX.js  (minified, hashed filename)
```

Search for target patterns:

```bash
grep -n 'aspectRatio.*"1:1"' /tmp/extracted/out/renderer/assets/index-*.js
```

### 3. Modify (minified JS)

**CRITICAL**: Editing minified JS is fragile. Use these strategies in order of preference:

**A. Single-line string replacements (safest)**
```bash
sed -i 's/outfitPromptConfig?\.aspectRatio || "1:1"/outfitPromptConfig?.aspectRatio || "16:9"/g' file.js
```

**B. Address-based next-line replacement**
```bash
# Match line containing X, then on the next line (n), replace Y with Z
sed -i '/prompt: input\.prompt,/{n;s/"1:1"/"16:9"/}' file.js
```

**C. Python for complex multi-line matches**
```python
# When sed/perl multi-line fails (they process line-by-line)
old = 'exact\nmulti-line\nstring with "quotes"'
new = 'exact\nmulti-line\nstring with "new text"'
content = content.replace(old, new)
```
Use Python with `read_file` for verification before writing.

### 4. Verify changes stuck

**Always verify** before repacking — sed/perl silently skip non-matches:

```bash
grep -n 'aspectRatio.*"16:9"' file.js | wc -l
grep -n 'aspectRatio.*"1:1"' file.js | grep -v 'aspect_ratio\|aspectRatioInput\|resolutionMap'
```

Common failure: perl `-pe` only processes line-by-line, so multi-line patterns silently fail. If the count doesn't match expectations, switch to Python or sed address patterns.

### 5. Repack

```bash
npx @electron/asar pack /tmp/extracted/ /tmp/app_new.asar
```

### 6. Backup & Replace

```bash
cp /path/to/app.asar /path/to/app.asar.bak_$(date +%Y%m%d_%H%M%S)
cp /tmp/app_new.asar /path/to/app.asar
```

### 7. Restart the app

From WSL, kill Windows processes then start:

```bash
taskkill.exe /F /IM "app-name.exe" 2>/dev/null
powershell.exe -Command "Start-Process 'D:\path\to\app.exe'"
```

**Note**: Don't use `cmd.exe /c start` from WSL — UNC path issues cause silent failures. Use `powershell.exe Start-Process` instead.

## Pitfalls

- **Line-number drift**: Each modification changes line numbers in minified JS. Re-grep after every edit.
- **silent sed failures**: `sed` silently succeeds on non-matching patterns. Always verify.
- **perl multi-line**: `perl -pe` is line-by-line. Use `-0777` for slurp mode or switch to Python.
- **Hash filenames**: The minified JS filename hash changes between builds. Don't hard-code filenames.
- **App code caching**: The Electron app may cache old code. A full process kill + fresh start is necessary.
- **npx download delay**: `npx @electron/asar` may need to download the package. Add `--yes` for non-interactive use.
- **API routing changes — test FIRST**: When modifying API endpoint routing, always `curl` the new endpoint before committing the change. A wrong endpoint (e.g., `/api/ai/image` that returns "Invalid URL") causes requests to hang until timeout instead of failing fast. Hours were wasted on this.
- **Multiple timeout locations**: Hardcoded timeouts exist in 3-4 places per codebase (chat completions AbortController, fetchWithTimeout calls, Kling-specific timeout, polling loops). Fix ALL of them — search for `6e4`, `submitTimeoutMs`, `setTimeout.*abort`.
- **Undefined variable cleanup**: When removing a variable definition, search for ALL remaining references. A single `isChuangweiProxy` left in response-handling code after removing its definition causes a silent `ReferenceError` that crashes the handler.
- **Zombie state after restart**: If the app is killed mid-task, JSON state files retain "generating" status. Reset to "idle" before retrying, or the app may skip already-"busy" groups.
- **Verify asar on disk, not just in extraction dir**: After `cp` to the app directory, re-extract from the target path and grep to confirm the modifications actually landed. Don't trust that `cp` succeeded — check md5sum.
- **DrvFS file locking (WSL → Windows)**: When the target app is running on Windows, its `/mnt/d/` files are locked. `mv`, `os.remove()`, and `cp` will all fail with "Permission denied". Always run `taskkill.exe /F /IM "app.exe"` first via PowerShell, then replace. The error is silent — the old asar stays in place and you won't notice until the fix doesn't take effect.
- **`local-image://` conversion must cover ALL paths**: If an app has both `submitGridImageRequest` and `submitViaChatCompletions` code paths for image generation, `local-image://` → base64 conversion must be added to BOTH. Missing one path means character/scene reference images silently fail for that route.
- **Dead endpoint → timeout, not fast error**: A non-existent API endpoint returns quickly with an error (verified via curl), but sometimes the app's retry loop with delays turns this into an apparent hang. Distinguish "API is slow" from "endpoint is wrong" by testing with curl first.

## Debugging without DevTools (Electron F12 disabled)

When the Electron app has DevTools disabled:

### A. HTTP Ping Server — verify click handlers fire
Start a Python HTTP server on a known port, inject a fetch to it in the suspect button's onClick handler:
```
Server: python3 -u -c "..." listening on :9999, writing to /tmp/ping.log
Inject: onClick: () => { window.electronAPI?.httpRequest({url:"http://127.0.0.1:9999/ping",method:"GET"}).catch(()=>{}); originalHandler?.(); }
```
If pings arrive, the handler fires. If not, the button is disabled or disconnected.

### B. Error Logging via HTTP — capture catch-block errors
Inject into every major catch block:
```js
} catch (e) {
    try { window.electronAPI?.httpRequest({url:"http://127.0.0.1:9999/log?msg="+encodeURIComponent(e.message),method:"GET"}).catch(()=>{}); } catch(_){}
}
```
This reveals the EXACT error message that would otherwise be silently caught.

### C. File-Based State Monitoring — track app progress
Monitor JSON state files for changes using a polling loop:
```python
while True:
    curr = json.dumps(json.load(path))
    if curr != prev: analyze(json.loads(curr))
    prev = curr; time.sleep(3)
```
More reliable than trying to intercept in-app toasts or UI updates.

## Common Modification Patterns

### Timeout values
- Default: `6e4` (60s), too short for image generation
- Change to: `6e5` (600s) for all paths
- Locations: `submitViaChatCompletions` AbortController, `fetchWithTimeout$1` calls, Kling submit

### Hardcoded defaults (aspect ratio, resolution)
- `aspectRatio: "1:1"` → `aspectRatio: "16:9"` — check ALL occurrences, some are model config arrays (don't change those)
- `resolution: void 0` → `resolution: "2K"` — `void 0` means the API gets no resolution hint

### API routing cleanup
When removing proxy-specific routing, use this checklist:
1. Remove condition check (`isChuangweiProxy`)
2. Remove conditional endpoint (`/api/ai/image`)
3. Remove conditional auth (`apiKey` in body)
4. Keep `local-image://` → base64 conversion (always needed)
5. Remove conditional response parsing
6. Search for ALL remaining references before packing

## Reference Files

- `references/moyin-creator.md` — App-specific paths, data structures, common fix patterns for 魔因漫创
