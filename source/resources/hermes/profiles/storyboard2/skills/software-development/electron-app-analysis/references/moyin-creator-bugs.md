# Moyin Creator — Bugs Found & Fixes

> Session: 2026-05-20. Part of `electron-app-analysis` skill.

## Bug 1: 9-Grid Board Generation Timeout

### Symptom
- User generates a 3×3 board (九宫格) in S-class panel
- API website (chuangwei.cyou) shows the image was generated and charged
- Software shows "failed" with error: "拼图生成请求超时（60秒）"
- sclass.json: `gridGenerationStatus: "failed"`, `gridGenerationError: "拼图生成请求超时（60秒），请检查网络后重试"`

### Root Cause
In `index-BiEM7W1o.js`, the `submitGridImageRequest` function (line 85495) has model-dependent timeouts:

```javascript
const submitTimeoutMs = isMemefastGptImage2Model(model) ? 12e4 : 6e4;
```

The `MEMEFAST_GPT_IMAGE_2_MODELS` set only contains `"gpt-image-2"` and `"gpt-image-2-all"`.
The user's model `"gpt-image-2-reverse"` was NOT in the set → got 60-second timeout.
The chuangwei.cyou proxy took >60s to respond → timeout fired before getting taskId.
Meanwhile, the API backend completed successfully and charged.

There's a SECOND occurrence of the same pattern at line 85220 in another image submit function.

### Fix Applied

Three changes to `/tmp/moyin-extract/out/renderer/assets/index-BiEM7W1o.js`:

1. **Add model to whitelist** (line 73019):
```javascript
const MEMEFAST_GPT_IMAGE_2_MODELS = new Set([
  "gpt-image-2",
  "gpt-image-2-all",
  "gpt-image-2-reverse"  // ← added
]);
```

2. **Add variant entry** (line 73089):
```javascript
"gpt-image-2-reverse": {
  id: "gpt-image-2-reverse",
  outputFormatField: "output_format",
  editUploadField: "image",
  generationAspectRatios: [...GPT_IMAGE_2_COMMON_ASPECT_RATIOS],
  editAspectRatios: [...GPT_IMAGE_2_COMMON_ASPECT_RATIOS],
  generationSizes: GPT_IMAGE_2_GENERATION_SIZES,
  editSizes: OPENAI_IMAGE_SIZES
}
```

3. **Bump default timeout** in BOTH occurrences (lines 85495 and 85220):
```javascript
// Before:
const submitTimeoutMs = isMemefastGptImage2Model(model) ? 12e4 : 6e4;
// After:
const submitTimeoutMs = isMemefastGptImage2Model(model) ? 12e4 : 18e4;
```

This gives:
- gpt-image-2-reverse: 120s (recognized as memefast model)
- All other models: 180s (bumped from 60s)

### State Recovery

Also needed to reset the stuck "failed" state in sclass.json:

```python
g['gridGenerationStatus'] = 'idle'
g['gridGenerationError'] = None
g['gridImageUrl'] = None    # Remove stale partial data
g['groupGridAsset'] = None
```

### ASAR Repack (Critical Detail)

```bash
# MUST pack from the parent of out/, not from out/ itself!
cd /tmp/moyin-extract
npx @electron/asar pack . "/mnt/d/魔因/moyin-creator/resources/app.asar"

# Verify: must show /node_modules, /out, /package.json at root
npx @electron/asar list app.asar | head -3
```

Wrong: `npx @electron/asar pack out app.asar` → produces `/main` at root, missing node_modules.

### Verification
```bash
grep -c 'gpt-image-2-reverse' index-BiEM7W1o.js  # → 3
grep -c '18e4' index-BiEM7W1o.js                   # → 2
grep -c 'isMemefastGptImage2Model.*: 6e4' index-BiEM7W1o.js  # → 0 (all fixed)
```

## Bug 2: Scene Contact Sheet Results Not Saved

### Symptom
- `scene-contact-sheet` task completes (status=completed, childSceneCount=9)
- 9 child viewpoint scenes created in scenes.json
- BUT all 9 child scenes have `imageUrl` = null (no image links)
- sclass.json shot groups have `gridImageUrl` = null
- PNG files exist in `media/scenes/` but aren't linked to their scenes

### Root Cause
The `scene-contact-sheet` job handler creates child scenes but fails to save the
generated grid image URL back to `scene.imageUrl`. The handler splits the API
result into 9 viewpoint scenes correctly, but the result-saving step doesn't
populate the image URL field.

### Manual Recovery
Match PNG files to scenes by timestamp proximity (scene IDs contain timestamps).

## Key File Locations for Future Debugging

| File | Debug Purpose |
|------|--------------|
| `sclass.json` | Check `shotGroups[].gridGenerationStatus` for timeout/failure |
| `director.json` | Check `splitScenes[].boardImageUrl` for board results |
| `scenes.json` | Check `scenes[].imageUrl` for missing image links |
| `runtime.db` | Check `studio_run_tasks.status` and `studio_run_jobs.job_payload_json` |
| `opencut-api-config.json` | Encrypted API keys (electron-safe-storage) |
| `media/scenes/*.png` | Verify images were actually downloaded (check timestamps) |
