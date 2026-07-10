---
name: moyin-creator
description: Debug, develop, and modify Moyin Creator (魔因漫创), an open-source (AGPL-3.0) Electron-based AI film production tool. Covers full-source dev workflow (npm run dev/build), prompt compilation pipeline, finding lost generated images, fixing broken data associations, and diagnosing generation failures. The app.asar patching era is over — now we modify TypeScript source directly.
---

# Moyin Creator — Debugging & Data Recovery

## When to load this skill
- User wants to develop/modify 魔因漫创 (now open-source — full TypeScript source available)
- User says generated images/videos don't show up but API was charged
- User wants to find where generated image files are stored locally
- User needs to understand the prompt the software actually sent to an API
- User hit a "task completed on API side but result not displayed" bug
- User wants to extract full prompts or API call details from the SQLite database

## Open-Source Dev Environment

魔因 is now **fully open source** (AGPL-3.0) at `https://github.com/memecalculate/moyin-creator`. We no longer need to extract/patch app.asar — all modifications are done at the TypeScript source level.

### Current setup
- **Pre-built Windows portable**: `D:\\魔因漫创开源版\\moyin-creator-0.2.8\\moyin-creator.exe` (v0.2.8)
- **Dev environment (WSL)**: `/home/administrator/moyin-creator/` — full source, `npm install` done
- **Tech stack**: Electron 30 + React 18 + TypeScript 5 + Tailwind CSS 4 + Zustand 5
- **Code scale**: 285 files, 100K+ lines TypeScript

### Dev commands
```bash
cd /home/administrator/moyin-creator
npm run dev      # Development mode (Electron + HMR)
npm run build    # Build + package for Windows
```

**WSL Electron GUI setup**: `npm run dev` compiles successfully but Electron requires GUI dependencies and X server. Install once:

```bash
# Install Electron dependencies (Ubuntu 25.04+ uses t64 suffix variants)
sudo apt-get install -y libnss3 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 \
  libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2t64

# Set DISPLAY for WSLg (Windows 11 built-in X server)
export DISPLAY=:0
```

Then `npm run dev` will launch the Electron window. Verify WSLg availability: `ls /mnt/wslg` should show `PulseServer`, `versions.txt`, etc.

**Alternative workarounds** if WSLg unavailable:
1. **Compile on WSL, run on Windows**: After `npm run dev` compiles `out/`, copy the entire project to Windows and run `npm run dev` there (requires Node.js on Windows)
2. **Use pre-built binary**: Run the pre-built `moyin-creator.exe` from `D:\魔因漫创开源版\moyin-creator-0.2.7\win-unpacked\` directly — it loads from the same workspace as dev mode

For **API request capture** (logging prompts/request bodies), see `references/api-request-capture.md`.

For **extracting prompts from source code** (static analysis without runtime), see `references/extracting-prompts-from-source.md`.

### Key source locations
| Module | Path | Notes |
|--------|------|-------|
| Prompt compiler | `src/packages/ai-core/services/prompt-compiler.ts` | Template-based prompt building |
| Character bible | `src/packages/ai-core/services/character-bible.ts` | 6-layer identity anchors |
| Task queue | `src/packages/ai-core/task-queue.ts` | Priority concurrent queue |
| API config | `src/stores/api-config-store.ts` | Provider settings, 8-step migration chain |
| Director panel | `src/components/panels/split-scenes.tsx` | 4,066 lines, core scene cutting UI |
| S-Class panel | `src/components/panels/sclass-scenes.tsx` | 3,839 lines, Seedance 2.0 |
| Generation panel | `src/components/panels/generation-panel.tsx` | 3,497 lines, batch generation |
| Video generation | `src/lib/use-video-generation.ts` | Video API + polling |
| Electron main | `electron/main.ts` | 1,719 lines, 36 IPC handlers |
| API call layer | `src/lib/script/script-parser.ts` | `callChatAPI()` at line 210-360, constructs OpenAI format requests |

### API provider notes
- The user is an AI short drama creator/blogger who runs their **own API proxy** at `chuanggwei.cyou` — all API keys and model routing are managed there independently
- 魔因 connects to whatever API provider you configure in Settings — it is NOT locked to 魔因's own API
- To swap providers: modify `src/packages/ai-core/providers/` and `src/stores/api-config-store.ts`
- S-Class / Seedance 2.0 routes through `memefast.top` → Alibaba Bailian by default (configurable)

### 魔因兼容模式 (memefast_compatible)

When adding a **自定义** (custom) API provider, there's an advanced setting labeled **"魔因兼容模式"**. This toggle controls how the app formats requests and parses responses:

| Setting | Internal value | Behavior |
|---------|---------------|----------|
| **开启** | `memefast_compatible` | Uses 魔因/memefast API conventions (non-standard response format) |
| **关闭** | `standard_openai` | Uses standard OpenAI-compatible API format |

**When to enable**: If your API proxy (`chuanggwei.cyou`) was originally set up for the old 魔因漫创 and follows its non-standard format, **enable this**. If your API follows standard OpenAI `/v1/chat/completions` and `/v1/images/generations` conventions, leave it off.

The relevant compiled code (in the pre-built v0.2.7 asar):
```
customCompatibilityMode: checked === true ? "memefast_compatible" : "standard_openai"
```

Image API format resolution checks `provider.platform === "custom" && settings.compatibilityMode === "memefast_compatible"` to decide routing behavior.

## Script Import Format

魔因 uses a strict screenplay format for script import. The format spec is at `docs/SCRIPT_FORMAT_EXAMPLE.md` in the repo. See `references/script-format-template.md` for the full reference.

**Script import workflow**: 12-step AI processing pipeline, all using feature key `script_analysis`:
1. Structure analysis (scene boundaries, character extraction)
2. Scene art calibration (location, time, atmosphere)
3. Character 6-layer anchors (face, eyes, nose, lips, unique marks, color codes)
4. 5-stage shot calibration (composition, camera, lighting, mood, continuity)
5-12. Additional refinement passes

To capture the exact prompts sent during import, see `references/api-request-capture.md`.

### Required elements

| Element | Format | Example |
|---------|--------|---------|
| Scene header | `N-M 日/夜 内/外 地点` | `1-3 夜 外 新沪市` |
| Characters | `人物：角色A、角色B` | `人物：林星野、苏晓` |
| Stage directions | `△` prefix | `△林星野推开玻璃门。` |
| Dialogue | `角色名：台词` | `林星野：我不会再逃了。` |
| Performance notes | `（括号内）` | `苏晓：（轻声）理论基础存在缺陷。` |
| Subtitles/transitions | `【字幕：内容】` | `【字幕：三小时后】` |

### Full document structure
```
**《剧名》**

**大纲：**
一段话概括核心故事

**人物小传：**
角色名（年龄）：身份，性格特征

---

**第X集：集标题**

---

**N-M 日/夜 内/外 地点**
人物：角色A、角色B

△舞台指示。

角色A：台词内容。

---

**N-M 日/夜 内/外 地点**
...
```

### Converting existing scripts
When converting from screenplay format (场x. 地点 - 日 - 内/外) to 魔因 format:
1. Split by `场` markers → each becomes `集-场 日/夜 内/外 地点`
2. `△` before stage directions, no colon separator
3. Dialogues: `角色名：台词` (full-width colon)
4. `[SFX]` can remain as-is or be converted to `△` directions
5. Add `人物：` line at the top of each scene block
6. `【字幕：】` for time/location transitions

### Installing from source (fresh)
```bash
git clone https://github.com/memecalculate/moyin-creator.git
cd moyin-creator
npm install    # ~300s on WSL native filesystem; avoid /mnt/d/ (cross-fs slow)
npm run dev
```

### Cross-filesystem pitfall
npm install on WSL with project on `/mnt/d/` (Windows drive) is extremely slow (~10x). Always copy to WSL native filesystem (`/home/administrator/`) first:
```bash
rsync -a --exclude=node_modules /mnt/d/moyin-creator/ /home/administrator/moyin-creator/
```

## Storage architecture

| Layer | Location (typical) | Format |
|-------|-------------------|--------|
| User data (Electron) | `%APPDATA%/Roaming/魔因漫创-profiles/default-*/` | SQLite + JSON |
| Task/job history | `…/studio-run/runtime.db` | SQLite, 2 tables |
| Project data | `{workspace}/projects/_p/{project-id}/` | JSON files |
| S-Class groups | `sclass.json` → `shotGroups[]` | Zustand persist |
| Scene data | `scenes.json` → `scenes[]` | JSON |
| Generated images | `{workspace}/media/scenes/`, `media/shots/`, `media/characters/` | PNG files |
| API config (encrypted) | `…/workspace-data/projects/opencut-api-config.json` | electron-safe-storage |

The workspace path is configured in `%APPDATA%/Roaming/魔因漫创-profiles/default-*/storage-config.json` (`basePath`).

## runtime.db schema

```
studio_run_tasks: id, category, label, project_id, provider, model,
                  status, error_text, summary_json, payload_json,
                  progress, created_at, started_at, completed_at

studio_run_jobs:   task_id, queue_name, job_kind, job_payload_json,
                   job_state, created_at, updated_at
```

Key job kinds: `character-image-generation`, `scene-contact-sheet`, `scene-orthographic-image`, `scene-image-generation`, `script-import-full-workflow`, `script-calibrate-episode-shots`.

## Image URL format

Images are referenced as `local-image://scenes/{timestamp}_{random}.png` in JSON state files. The actual PNGs live in `media/scenes/` with filenames matching this pattern.

## Common bug: generated images not displayed

**Root cause**: Tasks (especially `scene-contact-sheet` and `scene-orthographic-image`) complete on the API side, the PNG files are downloaded to `media/scenes/`, but the JSON state files are never updated with the `imageUrl`.

**Symptoms**:
- API website shows image generated and fees charged
- `runtime.db` shows `status=completed` with `summary_json` containing child scene IDs but no `imageUrl`
- `scenes.json` entries have `imageUrl: ""` (empty)
- `sclass.json` group has `gridImageUrl: null`
- PNG files DO exist in `media/scenes/` from the right timestamp

**Fix recipe**:
1. Match PNG files to scene records by closest timestamp (filenames encode epoch ms)
2. Set `imageUrl` → `local-image://scenes/{matched_png}`
3. Set `imageStatus` → `completed`, `imageProgress` → `100`
4. For S-Class grids, set `gridImageUrl` on the group
5. **Always backup JSON files first** (`.backup_*`)

See `references/recovery-script.md` for the full recipe.

## Prompt compilation (character sheets)

Characters are generated via `POST https://chuangwei.cyou/api/ai/image` with a compiled prompt built from:

```
finalPrompt = basePrompt + contentPrompt + whiteBackground + styleTokens + detailSuffix
```

- **basePrompt**: `专业角色设计参考图，"陈戈"，{characterDescription}` (Chinese) or `professional character design sheet for "…"` (English)
- **characterDescription**: composed from `primaryVisualPrompt` + `anchorPrompt` (face, eyes, nose, lips, unique marks, color anchors like `#3D2314`, skin texture, hair) + `eraPrompt`
- **contentPrompt**: from `SHEET_ELEMENTS` — `three-view turnaround`, `expression sheet`, `body proportion reference`, `pose sheet`
- **whiteBackground**: `pure solid white background, isolated character on white background, absolutely no background scenery`
- **styleTokens**: e.g. `(best quality, masterpiece, 8k, high detailed:1.2), (stunning stylized 3D Chinese animation character render:1.3), (Unreal Engine 5 style:1.2)…`
- **detailSuffix**: `detailed illustration, concept art, character model sheet`

Negative prompt = `blurry, low quality, watermark, text, cropped` + character-specific `avoid` list + `styleExclusions`.

See `references/prompt-compilation-formula.md` for exact source code references.

For exact line numbers and context strings for all modification points in the minified JS, see `references/code-map.md`.

## API routing

The software sends requests through configurable API providers:

- **Image/text tasks**: `POST https://chuangwei.cyou/api/ai/{screenplay|image|video}` (user's own API proxy — configurable in settings)
- **S-Class / Seedance 2.0**: Configurable; default routes through Alibaba Bailian (`dashscope.aliyuncs.com`)
- **Model `gpt-image-2-reverse`** is a chuangwei.cyou internal mapping

All API routing is in TypeScript source now — edit `src/packages/ai-core/providers/` and `src/stores/api-config-store.ts` directly.

## ASAR Patching & Runtime Debug (LEGACY — for pre-open-source era only)

These techniques were for the closed-source Electron binary era. With the full source available, prefer modifying TypeScript directly. Keep these as fallback only if working with a pre-built binary without source access.

See `references/asar-patching.md` for the full reference. Quick summary:

See `references/asar-patching.md` for the full reference. Quick summary:

### Button click not working?
1. Start local HTTP ping server on :9999
2. Inject `window.electronAPI.httpRequest({url:"http://127.0.0.1:9999/ping",…})` into button's onClick
3. Check `/tmp/hermes_ping.log` — if ping appears, issue is inside handler; if not, button is disabled

### Timeout changes
Four locations in the minified JS control API timeouts. All default to 60s/120s/180s. Change to `6e5` (600s) for slow models. Use `replace_all: true` when patterns appear twice.

### Grid generation is stuck?
Check `sclass.json` → `shotGroups[].gridGenerationStatus`. Groups stuck in `"failed"` can block the primary group's generate button. Reset to `"idle"` and clear `gridGenerationError`.

### Repack cycle
Always backup before replacing: `cp app.asar app.asar.bak_$(date +%Y%m%d_%H%M%S)`

## Asar Extraction & Modification (Legacy Workflow)

When working with pre-built binaries without source access, extract and modify the asar:

```bash
npx --yes @electron/asar extract "/mnt/d/魔因/moyin-creator/resources/app.asar" /tmp/asar_mini/
```

Key bundles:
- `out/renderer/assets/index-BiEM7W1o.js` — main renderer (~7.4MB)
- `out/renderer/assets/ai-worker-CNEoMg1t.js` — worker thread

After patching, repack:
```bash
npx --yes @electron/asar pack /tmp/asar_mini/ /tmp/app_new.asar
cp /tmp/app_new.asar "/mnt/d/魔因/moyin-creator/resources/app.asar"
```

Restart from WSL:
```bash
taskkill.exe /F /IM "moyin-creator.exe"
powershell.exe -Command "Start-Process 'D:\\魔因\\moyin-creator\\moyin-creator.exe'"
```

### Common asar modifications

**CRITICAL**: Never use byte-level binary patching (`data[pos:pos+N] = new_bytes`). Even same-length replacements can corrupt the archive structure (padding spaces inside function bodies, encoding mismatches with Chinese characters, etc.). Always use extract-patch-repack:
```bash
npx @electron/asar extract app.asar /tmp/extract/
# edit files in /tmp/extract/
npx @electron/asar pack /tmp/extract/ /tmp/patched.asar
```

**Timeout values**: Search for `submitTimeoutMs` and `6e4` (60s). Change to `6e5` (600s) for slow models.

**Aspect ratio**: Search for `aspectRatio.*"1:1"` and change to `"16:9"`. Also update `needsPixelSize()` whitelist and MemeFast adapter registration.

**API routing**: Detect `chuangwei.cyou` proxy and override endpoint/auth/response parsing. See `electron-asar-patching` skill for full patterns.

**Character reference images**: Add `local-image://` → base64 conversion in `submitViaChatCompletions` path (already exists in `submitGridImageRequest`).

### Debugging without DevTools

**HTTP ping injection**: Inject `window.electronAPI?.httpRequest({url:"http://127.0.0.1:9999/ping",method:"GET"})` into onClick handlers to verify they fire.

**State file monitoring**: Poll JSON state files for changes to track generation progress.

**Error logging via HTTP**: Inject HTTP requests in catch blocks to capture error messages.

See `references/asar-patching.md` for detailed recipes.

## Template Library Configuration (v0.2.8+)

Settings → "GPT Image 2 模板库根目录" and "Seedance 2.0 模板库根目录" each require a directory containing a `manifest.json` file. The software validates by reading `manifest.json` and checking that `manifest.prompts` is an Array.

### manifest.json format

```json
{
  "prompts": [
    {
      "id": "unique-id",
      "slug": "url-friendly-slug",
      "title": "Display name",
      "prompt": "The prompt text with {argument name=...} placeholders",
      "translatedPrompt": "Optional translated prompt",
      "description": "Short description",
      "model": "gpt-image-2",
      "locale": "zh-CN",
      "language": "中文",
      "category": "海报 / 传单",
      "author": {"name": "Author Name", "link": "https://..."},
      "pageUrl": "https://source-page-url",
      "sourceLink": "https://source-link",
      "sourcePublishedAt": "2025-01-01",
      "thumbnailUrl": "https://thumbnail-url",
      "referenceImageUrls": [],
      "mediaImageUrls": [],
      "videoUrls": [],
      "assets": [
        {"kind": "thumbnail", "fileName": "thumb.png", "url": "https://..."},
        {"kind": "reference-image", "fileName": "ref.jpg", "url": "https://..."}
      ]
    }
  ],
  "generatedAt": "2025-01-01T00:00:00Z",
  "source": {"url": "https://source-url"}
}
```

### Validation flow

See `references/template-manifest-format.md` for the full manifest specification, category inference rules, and legacy format details.

1. `resolveGptImageTemplateLibraryRoot(inputPath)` → looks for `manifest.json` directly in the selected directory (no subdirectory search)
2. `readGptImageTemplateManifest(rootPath)` → `JSON.parse(fs.readFileSync(manifestPath))` → checks `Array.isArray(manifest.prompts)`
3. Status labels: `"ok"` (已连接), `"missing"` (缺少目录/manifest.json 不存在), `"invalid"` (格式错误), `"unconfigured"` (未配置)

### Key template fields accessed by software

| Field | Usage |
|-------|-------|
| `prompt.id` / `prompt.slug` | Template ID (stable identifier) |
| `prompt.title` | Display name |
| `prompt.prompt` | Raw prompt text (with `{argument name=...}` placeholders) |
| `prompt.translatedPrompt` | Translated variant |
| `prompt.description` | Searchable description |
| `prompt.author.name` | Author display |
| `prompt.category` | Auto-inferred via `inferGptImageTemplateCategory()` if not set |
| `prompt.assets[].kind` | `"thumbnail"`, `"reference-image"`, `"media-image"` |
| `prompt.assets[].fileName` | Local file path (resolved relative to library root or `<id>-<slug>/` subfolder) |

### Legacy template format incompatibility

Old template data stored in `模版库/catalog/` (SQLite `.sqlite3` + JSONL `.jsonl`) is NOT compatible with the new `manifest.json` format. The legacy data uses fields like `template_id`, `display_name`, `media_combo`, `template_category`, `slot_signature` — completely different from what v0.2.8 expects. If you need to use old template data, it must be converted to the manifest.json format first.

When images generate successfully on the API but don't appear in the software:

1. **Check runtime.db**: `SELECT * FROM studio_run_tasks WHERE status='completed' ORDER BY created_at DESC LIMIT 10`
2. **Check state files**: `sclass.json` → `shotGroups[].gridGenerationStatus`, `scenes.json` → `scenes[].imageUrl`
3. **Match media files**: Find PNGs in `media/scenes/` with timestamps matching scene `createdAt`
4. **Fix associations**: Set `imageUrl` to `local-image://scenes/{filename}`, `imageStatus` to `"completed"`

See `references/recovery-recipe.md` and `scripts/fix-image-associations.py` for automation.

## Contact Sheet (联合图) Character Leakage Fix

联合图 should be scene-only (no people), but AI-generated viewpoint descriptions from `viewpoint-analyzer.ts` often include character references ("where the old man sits", "protagonist entrance zone"). These leak into the final prompt even though it says "NO people".

### Root cause chain

1. `viewpoint-analyzer.ts` calls AI to analyze scene viewpoints → AI sees shot data with character names, dialogue, characterBlocking → generates descriptions with character terms
2. `scene-viewpoint-generator.ts` → `generateContactSheetPrompt()` uses `vp.descriptionEn` directly in panel descriptions
3. Image model sees "elderly man sits" in a panel description and draws a person despite "(no people)" tag

### Fix approach (two layers)

**Layer 1 — AI prompt constraint** (in `viewpoint-analyzer.ts` system prompt):
Add to the viewpoint analysis system prompt:
```
5. **严格禁止人物信息**：视角名称/描述/道具中均不得包含任何人物相关信息，包括但不限于：角色名、人称、职业、年龄、服装、表情、动作。只描述场景空间和物品。
```

**Layer 2 — Output sanitization** (in `scene-viewpoint-generator.ts`, right after `vp.descriptionEn` assignment):
Filter character-related terms from all viewpoint fields before they reach the contact sheet prompt. Regex covers both Chinese and English:

```typescript
const CHARACTER_TERMS_EN = /\b(man|woman|boy|girl|person|people|character|protagonist|elderly|...)\b/gi;
const CHARACTER_TERMS_ZH = /(男人|女人|男孩|女孩|人物|角色|主角|老人|...)/g;
viewpoints.forEach((vp) => {
  vp.descriptionEn = vp.descriptionEn.replace(CHARACTER_TERMS_EN, 'scene');
  vp.description = vp.description.replace(CHARACTER_TERMS_ZH, '场景');
  vp.nameEn = vp.nameEn.replace(CHARACTER_TERMS_EN, 'Area');
  vp.name = vp.name.replace(CHARACTER_TERMS_ZH, '区域');
  vp.keyPropsEn = vp.keyPropsEn.map(p => p.replace(CHARACTER_TERMS_EN, 'item'));
  vp.keyProps = vp.keyProps.map(p => p.replace(CHARACTER_TERMS_ZH, '物品'));
});
```

### Patching the pre-built 0.2.8 asar

The 0.2.8 bundled JS (`out/renderer/assets/index-BTBs57B6.js`) has evolved significantly from the 0.2.3 source — direct TypeScript source edits won't affect the pre-built binary. Inject the Layer 2 regex filter directly into the minified JS:

1. Extract asar with `npx @electron/asar extract`
2. Find `viewpoints.forEach((vp, index2) => { const propsZh = ...` in the minified JS
3. Insert the filter block immediately after the closing `});` of that forEach block
4. Repack with `npx @electron/asar pack`
5. Kill the running process (`taskkill.exe /F /IM moyin-creator.exe`) before replacing the asar

**DrvFS pitfall**: On WSL, `/mnt/d/` files locked by running Windows processes cannot be `mv`'d or `os.remove()`'d — the process must be killed first. The `mv` command will fail with "Permission denied" silently appearing as though the file is immutable.

## 九宫格 vs 单独生成 — Why Results Differ

When users generate images in the S-class panel, there are two paths that produce noticeably different results:

**单独生成** (`handleGenerateSingleImage`, `sclass-scenes.tsx`): flat prompt `{imagePromptZh}. Style: {fullStylePrompt}` — no consistency constraints, no character count, no structured layout, no negative prompt beyond defaults.

**一键九宫格** (`generateGridAndSlice`, `sclass-scenes.tsx`): structured `<instruction>` block with:
- `MANDATORY Visual Style for ALL panels` (head anchor)
- `Maintain consistent character appearance, lighting, color grading, and visual style across ALL panels`
- Per-panel character count: `(no people)` / `(1 person)` / `(N people)`
- `[same style]` anchor per panel (middle anchor)
- `IMPORTANT - Apply this EXACT style uniformly to every panel` (tail anchor)
- Style-specific negative prompt merged into `Negative constraints`
- Grid layout: `Generate a clean NxN storyboard grid with exactly M equal-sized panels`

The **style tokens are identical** (`getStylePrompt(currentStyleId)`) — the gap is entirely from the structured wrapper: consistency directives, character count control, and the 3-layer style sandwich (MANDATORY → [same style] → IMPORTANT).

## S-Class Video Generation Prompt

Built by `sclass-prompt-builder.ts` (`buildGroupPrompt`). Priority: manual `mergedPrompt` > AI `calibratedPrompt` > auto-assembly.

Auto-assembled format for 九宫格 groups:
```
多镜头叙事视频，参考 @图片1 格子图（共N个镜头，总时长Xs）：

镜头1 [0s-5s]「场景名」：{cameraMovement}, {shotSize}, {cameraAngle}, {focalLength}, camera: {cameraPosition}, {videoPrompt}, lighting: {style/direction/temperature/notes}, DoF: {depthOfField}, focus: {focusTarget}, rig: {cameraRig}, atmosphere: {effects}, mood: {emotionTags}

角色参考：@图片2（角色名）保持角色外观一致
场景参考：@图片4 作为场景参考
画幅：16:9
全部镜头保持角色外观一致，镜头间平滑过渡，不出现文字或水印。
```

Each shot segment (`buildShotSegment`) packs all cinematography fields from the SplitScene data model.

## Export Button Disabled (导出提交包灰掉)

The "导出提交包" button in S-class ShotGroupCard is disabled when any of:
- `isGeneratingAny` — any video generation task is active
- `isGridBusy` — grid image generation or slicing is in progress
- `isExportingPackage` — already exporting (prevent double-click)
- `!onExportGroupVideoPackage` — handler missing (rare, always passed)

For 九宫格 groups specifically, `canGenerateGroupVideo = !isGeneratingAny && !hasDurationBudgetIssue && !isDirectorBlocked && (!isNineGrid || hasGroupGrid2)`. The `hasGroupGrid2` check means all shots must have their first-frame/end-frame images generated and the grid assembled before export is meaningful.

Most common cause: grid images haven't finished generating/slicing (isGridBusy = true).

## "缺少 MemeFast endpoint metadata" Error

This error means the provider is registered (model names visible) but has no transport layer configured. The check is:
```javascript
input.providerTransportSources.length === 0 && input.customTransportSources.length === 0
```

For Seedance specifically, there's an additional gate in `resolveProviderTransportSourcesForInput`:
```javascript
if (family === "seedance" && isMemefastCapabilityInput(input) && !hasSeedanceMemefastProviderTransport(endpointTypes)) {
    return [];
}
```

`hasSeedanceMemefastProviderTransport` checks if endpoint types contain `volc`/`seedance`/`doubao`/`豆包视频异步`. If the provider only has standard OpenAI endpoints, this check fails and returns empty sources → error.

**Fix**: Patch `hasSeedanceMemefastProviderTransport` to always return `true`. Both the main renderer JS and `ai-worker-*.js` contain this function — patch both via extract-patch-repack.

## Finding Storage & Images

Storage config path on Windows: `%APPDATA%\魔因漫创-profiles\default-{hash}\storage-config.json` → `basePath` field.

Images: `{basePath}/media/{category}/` where categories are `shots`, `scenes`, `characters`. The 九宫格 sliced images go to `shots/`. Original grid image is stored in sclass-store as a URL, not a separate file.

To locate quickly from WSL: `cmd.exe /c "dir /s /b %APPDATA%\*storage-config.json"`

See `references/prompt-structures.md` for full prompt templates (contact sheet, 9-grid, single image, S-class video, calibration, viewpoint analysis).

## Related References

- `references/director-angel-prompts.md` — Director Angel vs buildGroupPrompt comparison, actual API payload structure, scene reference image bug
- `references/api-interception.md` — Runtime API request capture via fetch injection + HTTP server

## Pitfalls
- **User expects you to remember installation paths** — when user says "魔因不是你安装的吗？你不知道安装路径？", the answer is YES. Use the documented paths directly:
  - Pre-built: `D:\\魔因漫创开源版\\moyin-creator-0.2.8\\moyin-creator.exe`
    - Project data: `D:\\moyinxiangmu\\`
    - Dev source: `/home/administrator/moyin-creator/`
    - Output: `D:\\魔音提示词\\`
    - Template data (legacy): `G:\\人物库\\模版库\\`
- The `scene-contact-sheet` task summary has `childSceneCount` and `childSceneIds` but **NEVER** includes the grid `imageUrl` — this is the source of the "API shows generated but software doesn't" bug
- Timestamp matching between scene IDs and PNG filenames is approximate; use a diff threshold of ~500ms
- The `opencut-api-config.json` uses `electron-safe-storage` encryption with the scheme `electron-safe-storage` — API keys are encrypted at rest
- `local-image://` paths must match exactly; the software resolves them relative to the workspace media directory
- Always backup JSON state files before patching; a bad write can corrupt the project state
- **Grid button not responding?** Reset all `gridGenerationStatus: "failed"` groups to `"idle"` — stale failure state blocks the primary group's generate button
- **API timeouts** come from 4 different code paths in the minified JS, not a single config value; check `references/asar-patching.md` for exact locations
- **Electron renderer has no filesystem access** — use `window.electronAPI.httpRequest` for ping-based debugging, not `fs.writeFile` injections
- **Character reference images missing in grid?** Three-layer root cause: (1) `characters.json` `primaryImage: None` → `collectSClassCharacterReferenceImages` returns empty; (2) even with `primaryImage` set, `local-image://` URLs sent as-is fail because API can't access local files; (3) `submitViaChatCompletions` lacks base64 conversion unlike `submitGridImageRequest` path
- **Grid status monitoring: check `shotGroups[]`, NOT `gridGroups`** — `gridGroups` key doesn't exist in `sclass.json`. Use `shotGroups[i].gridGenerationStatus`
- **四视图 not appearing in scene mapping?** Two issues: (1) `imageUrl` field may be missing on viewpoint variant scenes — set to `referenceImage`; (2) `_shared/scenes.json` may be empty — populated entries are needed for the scene mapping dropdown
- **Template library validation fails on `G:\人物库`?** v0.2.8 requires `manifest.json` with `prompts` array at the directory root. The legacy template data in `模版库/catalog/` (SQLite/JSONL) is a different format — it cannot be used directly. Either generate a `manifest.json` from the old data or point to a directory that already has one.
