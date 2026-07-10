# 魔因漫创 (moyin-creator) — App-Specific Reference

## File Paths

| What | Path |
|------|------|
| App install | `D:\魔因\moyin-creator\` |
| Electron exe | `D:\魔因\moyin-creator\moyin-creator.exe` |
| asar archive | `D:\魔因\moyin-creator\resources\app.asar` |
| Runtime DB | `D:\魔因\moyin-creator\resources\runtime.db` |
| Project data | `D:\moyinxiangmu\projects\_p\<uuid>\` |
| Shared data | `D:\moyinxiangmu\projects\_shared\` |
| Media files | `D:\moyinxiangmu\media\characters\`, `...\scenes\`, `...\shots\` |

**WSL translation**: `/mnt/d/魔因/...` and `/mnt/d/moyinxiangmu/...`

## Project Data Files

Each project UUID directory contains:

| File | Purpose |
|------|---------|
| `scenes.json` | Scene library: scene definitions, viewpoint variants, board configs |
| `sclass.json` | Storyboard/S级: splitScenes (shot list), gridGroups (九宫格), storyboardConfig |
| `characters.json` | Character data: name, primaryImage, variations, prompts |
| `media.json` | Media registry: all generated/uploaded images with `local-image://` URLs |

## `local-image://` URL Scheme

`local-image://characters/<timestamp>_<hash>.png` → `D:\moyinxiangmu\media\characters\<timestamp>_<hash>.png`
`local-image://scenes/<timestamp>_<hash>.png` → `D:\moyinxiangmu\media\scenes\<timestamp>_<hash>.png`

These are local-only references. The chuangwei.cyou proxy cannot access them — they must be converted to base64 data URLs before sending to external APIs.

## Common Fix Patterns

### Aspect ratio changes (1:1 → 16:9)

Key locations in minified JS (line numbers approximate, always re-grep):

| Approx Line | Context | Change |
|-------------|---------|--------|
| ~138030 | `prepareCharacterDraftExecution` | `aspectRatio: "1:1"` → `"16:9"` |
| ~163208 | `resolveCharacterPreparedImageExecution` fallback | `"1:1"` → `"16:9"` + `resolution: void 0` → `"2K"` |
| ~163219 | explicitExecution path | `"1:1"` → `"16:9"` |
| ~163245 | runtime task path | `"1:1"` → `"16:9"` + `void 0` → `"2K"` |
| ~142139/142152 | wardrobe outfitPromptConfig fallback | `\| "1:1"` → `\| "16:9"` |
| ~165284 | wardrobe variation execution | `\| "1:1"` → `\| "16:9"` |

### Timeout fixes

Multiple timeout locations exist across different API paths. Search for ALL of them:

| Location | Code | Default | Change to |
|----------|------|---------|-----------|
| `submitViaChatCompletions` AbortController | `setTimeout(() => controller.abort(...), 6e4)` | 60s | 600s (`6e5`) |
| `submitGridImageRequest` fetchWithTimeout | `submitTimeoutMs = isMemefastGptImage2Model(model) ? 12e4 : 18e4` | 120/180s | 600s (`6e5`) |
| Kling image submit | `fetchWithTimeout$1(..., 6e4, signal, "Kling...")` | 60s | 600s (`6e5`) |

The `submitViaChatCompletions` path has TWO timeouts: the AbortController setTimeout AND the fetchWithTimeout. Both must be fixed.

### API Routing (chuangwei.cyou)

**The `/api/ai/image` endpoint does NOT exist on chuangwei.cyou.** It returns `"Invalid URL"`. The proxy uses standard OpenAI endpoints (`/v1/images/generations`) with Bearer auth. Previous routing code that redirected to `/api/ai/image` with `apiKey` in body was wrong — it caused requests to hang until timeout instead of failing fast with an error.

Correct routing: use standard OpenAI endpoint + Bearer auth + keep `local-image://` → base64 conversion.

### Grid Generation Flow (九宫格)

`handleGenerateGroupGridReference` → `submitGridImageRequest` has three paths:
1. `apiFormat === "openai_chat"` → `submitViaChatCompletions` (has separate timeout; **lacks local-image → base64 conversion** — must add)
2. `apiFormat === "kling_image"` → Kling-specific submit
3. Default → standard image API with MemeFast adapter

The group status lives in `shotGroups[].gridGenerationStatus` (NOT `gridGroups`). States: `idle`, `generating`, `completed`, `failed`. Error stored in `gridGenerationError`.

**Critical pitfall — `canGenerateGroupVideo` blocks first-time grid**: The condition `(!isNineGrid || hasGroupGrid2)` makes `canGenerateGroupVideo` false when no grid exists yet. `handlePrimaryGenerate` checks this BEFORE the nine-grid-first path, causing the button to silently do nothing. Fix: reset failed groups to `idle`, or modify `canGenerateGroupVideo`.

**Character reference images not appearing in grid — three-layer root cause**:
1. `characters.json` `primaryImage: None` → `collectSClassCharacterReferenceImages` returns empty array
2. `local-image://` URLs sent to API without conversion → API ignores them
3. `submitViaChatCompletions` path lacks base64 conversion (only `submitGridImageRequest` has it)

**MemeFast GPT Image 2 adapter — size mapping is critical**: `gpt-image-2-reverse` must be in `MEMEFAST_GPT_IMAGE_2_MODELS` list for the correct pixel-size mapping (`"16:9"` → `"2048x1152"`). Without it, `needsPixelSize` produces `"1280x720"` which the API ignores, defaulting to 1:1 output. Two changes needed: (1) add model to `MEMEFAST_GPT_IMAGE_2_MODELS` constants, (2) add to `needsPixelSize` check if the former isn't feasible.

**`submitTimeoutMs` simplification**: Replace `isMemefastGptImage2Model(model) ? 12e4 : 18e4` with a flat `6e5` (600s). The conditional adds no value — both values are too short for complex grid generation with multiple reference images.

### Missing imageUrl in scene variants

When scene views generate successfully but don't appear in UI, check that each variant has `imageUrl` set (not just `referenceImage`). Also check `_shared/scenes.json` has entries — empty shared store = nothing shows in scene mapping panel.
