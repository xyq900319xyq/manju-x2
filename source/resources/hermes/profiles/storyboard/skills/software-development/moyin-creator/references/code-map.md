# Moyin Creator — Key Code Locations in Minified JS

Reference map for the compiled `index-XXXXX.js` inside `app.asar`.
Line numbers shift between builds — use surrounding context strings to re-locate.

## Image Generation Paths

### submitViaChatCompletions (~line 84968)
- Receives `referenceImages` array, passes to `compressReferenceImage` without local-image conversion
- **FIX**: Add `materializeImageSourceToDataUrl` call BEFORE `compressReferenceImage`
- Timeout: AbortController `setTimeout(..., 6e4)` → change to `6e5`

### submitGridImageRequest (~line 85416)
- Main grid/scene image generation function
- Three paths: `openai_chat` → submitViaChatCompletions, `kling_image` → submitViaKlingImages, else standard
- Standard path has `submitTimeoutMs = isMemefastGptImage2Model(model) ? 12e4 : 18e4` → change to `6e5`
- **FIX**: local-image → base64 conversion added (was chuangwei-only, now universal)
- **FIX**: Removed broken chuangwei proxy routing (`/api/ai/image` → standard OpenAI endpoint)

### resolveImageApiFormat (~line 14805)
- Model → format routing: `gpt-image` regex matches `"openai_images"` (NOT `"openai_chat"`)
- Only gemini-image and sora-image models get `"openai_chat"`

## Nine-Grid (S级) Generation

### handleGenerateGroupGridReference (~line 133518)
- Core grid generation function, collects character refs from `collectSClassCharacterReferenceImages`
- Eventually calls `submitGridImageRequest`
- Line 133628: sets `gridGenerationStatus: "generating"`
- Line 133949-133954: catch block stores `gridGenerationError` from `error.message`

### handlePrimaryGenerate (~line 113617)
- Checks `canGenerateGroupVideo` BEFORE nine-grid-first check → blocks initial grid
- If `canGenerateGroupVideo` false (because `isNineGrid && !hasGroupGrid2`), returns silently

### canGenerateGroupVideo (~line 113446)
```
!isGeneratingAny && !hasDurationBudgetIssue && !isDirectorBlocked && (!isNineGrid || hasGroupGrid2)
```
The `(!isNineGrid || hasGroupGrid2)` clause prevents first-time grid generation.

### Primary group grid button (~line 115224)
- Disabled: `isGeneratingAny || isGridBusy || isOverBudget || !onGenerateGroupGrid`
- Text: "生成九宫格参考图" / "生成更多九宫格参考图" / "生成中"
- NOT the same button as non-primary groups (~line 114425)

## Aspect Ratio Hardcoded Locations

All at `"1:1"` → need `"16:9"`:
| ~Line | Context | Function |
|-------|---------|----------|
| 138030 | `prompt: params.prompt,` | prepareCharacterDraftExecution |
| 142139 | `outfitPromptConfig?.aspectRatio \|\| "1:1"` | wardrobe (log) |
| 142152 | `outfitPromptConfig?.aspectRatio \|\| "1:1"` | wardrobe (return) |
| 156541 | standalone `"1:1"` | (check context) |
| 163208 | `prompt: input.prompt,` + `resolution: void 0` | resolveCharacterPreparedImageExecution fallback |
| 163219 | `prompt: input.prompt,` | resolveCharacterPreparedImageExecution explicit |
| 163245 | `prompt: input.prompt,` + `resolution: void 0` | resolveCharacterPreparedImageExecution runtime |
| 165284 | `input.execution.aspectRatio \|\| "1:1"` | wardrobe variation execution |

Also: `resolution: void 0` → `"2K"` at lines 163210, 163246.

Do NOT change `"1:1"` in model config arrays (aspect_ratio lists like `["16:9", "9:16", "1:1"]`).

## Data Files

### sclass.json
- `projectData.shotGroups[].gridGenerationStatus` — grid status (NOT `projectData.gridGroups`)
- `projectData.shotGroups[].gridGenerationError` — error message
- `projectData.shotGroups[].groupGridAsset` — generated grid image
- `projectData.splitScenes[].characterIds` — characters per scene
- `projectData.storyboardConfig.characterReferenceImages` — mostly empty, refs come from scenes

### scenes.json
- `scenes[].imageUrl` — may be missing for viewpoint variants
- `scenes[].isViewpointVariant` — multi-view scenes
- `scenes[0].viewpoints[]` — board definitions for grid panels

### characters.json
- `characters[].primaryImage` — **MUST be set** for reference images to be collected
- `characters[].thumbnailUrl` — fallback if no primaryImage
- `characters[].images` — array of image URLs
- `characters[].variations` — variation data

### _shared/scenes.json
- Must have entries for scene mapping dropdown to show options
- Format: `{ "id", "name", "parentSceneId", "projectId", "isViewpointVariant", "viewpointId", "imageUrl", "referenceImage", "imageStatus" }`
