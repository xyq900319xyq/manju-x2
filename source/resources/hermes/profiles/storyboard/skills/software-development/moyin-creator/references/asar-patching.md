# ASAR Runtime Debug & Patch Reference

## Button Click Verification (HTTP Ping Injection)

When a button appears enabled but clicking seems to do nothing, verify the onClick actually fires.

### 1. Start local ping server
```bash
python3 -u -c "
import http.server
LOGFILE = '/tmp/hermes_ping.log'
with open(LOGFILE, 'w') as f: f.write('SERVER STARTED\n'); f.flush()
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        with open(LOGFILE, 'a') as f:
            f.write(f'PING {self.log_date_time_string()} — {self.path}\n'); f.flush()
        self.send_response(200); self.end_headers(); self.wfile.write(b'ok')
    def log_message(self, *a): pass
http.server.HTTPServer(('0.0.0.0', 9999), H).serve_forever()
" &
```

### 2. Inject ping into button onClick

Find the button's onClick in the minified JS (e.g., line ~115230 of index-*.js):
```js
// Before:
onClick: () => onGenerateGroupGrid?.(group.id),
// After:
onClick: () => { window.electronAPI?.httpRequest({url:"http://127.0.0.1:9999/ping",method:"GET"}).catch(()=>{}); onGenerateGroupGrid?.(group.id); },
```

### 3. Monitor
```bash
cat /tmp/hermes_ping.log
```
If ping appears but the function still doesn't work → issue is INSIDE the handler, not the button binding.

## Timeout Locations (All in minified index-*.js)

| Location | Code Pattern | Default | Fix |
|----------|-------------|---------|-----|
| `submitViaChatCompletions` (~L85025) | `setTimeout(() => controller.abort(…"60 seconds"…)`, `6e4)` | 60s | → `"600 seconds"`, `6e5` |
| `submitImageTask` (~L85222) | `isMemefastGptImage2Model(model) ? 12e4 : 18e4` | 120s/180s | → `6e5` |
| `submitGridImageRequest` (~L85507) | `isMemefastGptImage2Model(model) ? 12e4 : 18e4` | 120s/180s | → `6e5` |
| Kling path (~L85658) | `6e4, signal, "Kling image request timed out"` | 60s | → `6e5` |

Use `replace_all: true` when patching the two `isMemefastGptImage2Model` lines (they appear in both functions).

## Grid Generation Code Paths

`handleGenerateGroupGridReference` (~L133518) → `submitGridImageRequest` (~L85416):

1. **`apiFormat === "openai_chat"`** → `submitViaChatCompletions` — hardcoded 60s AbortController
2. **`apiFormat === "kling_image"`** → `submitViaKlingImages`  
3. **Standard/MemeFast/chuangwei** → `fetchWithTimeout$1` with `submitTimeoutMs`

## sclass.json State Quick Reference

```python
import json
with open("sclass.json") as f: data = json.load(f)

sgs = data["state"]["projectData"]["shotGroups"]
for sg in sgs:
    print(sg["gridGenerationStatus"], sg.get("gridGenerationError"))

# Reset failed group:
sg["gridGenerationStatus"] = "idle"
sg["gridGenerationError"] = None
```

### Button Disabled Conditions

- **Primary nine-grid group** (~L115229): `disabled: isGeneratingAny || isGridBusy || isOverBudget || !onGenerateGroupGrid` — does NOT check `canGenerateGroupVideo`
- **Child groups** (~L114425): `disabled: isGridBusy || !canGenerateGroupVideo || …` — stricter

A group stuck in `"failed"` can indirectly block the primary button if it sets `isGridBusy` or `isGeneratingAny`.

## Aspect Ratio Hardcoded Locations

In `resolveCharacterPreparedImageExecution` (~L163205) and `prepareCharacterDraftExecution` (~L138030), `aspectRatio: "1:1"` is hardcoded in 7 places. For 16:9 output — sed approach:

```bash
sed -i '/prompt: params\.prompt,/{n;s/"1:1"/"16:9"/}' index.js
sed -i '/prompt: input\.prompt,/{n;s/"1:1"/"16:9"/}' index.js
sed -i 's/resolution: void 0/resolution: "2K"/g' index.js
sed -i 's/outfitPromptConfig?\.aspectRatio || "1:1"/outfitPromptConfig?.aspectRatio || "16:9"/g' index.js
sed -i 's/input\.execution\.aspectRatio || "1:1"/input.execution.aspectRatio || "16:9"/g' index.js
```

## Chuangwei Proxy Detection

In `submitGridImageRequest` (~L85509):
```js
const isChuangweiProxy = /chuangwei\\.cyou/i.test(normalizedBase);
```
When true: endpoint → `/api/ai/image`, apiKey in body, local-image:// → base64.

## Repack & Replace Cycle

```bash
npx --yes @electron/asar pack /tmp/extracted/ /tmp/app_new.asar
cp app.asar app.asar.bak_$(date +%Y%m%d_%H%M%S)
cp /tmp/app_new.asar app.asar
taskkill.exe /F /IM "moyin-creator.exe"
sleep 2
powershell.exe -Command "Start-Process 'D:\魔因\moyin-creator\moyin-creator.exe'"
```
