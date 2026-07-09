---
name: moyin-creator-dev
description: Develop, debug, and modify Moyin Creator (魔因漫创) — an Electron-based AI short drama tool. Covers the prompt pipeline, ASAR patching, contact sheet generation, template libraries, and image storage.
---

# Moyin Creator Development

## Project Structure

- **Pre-built 0.2.8**: `D:\魔因漫创开源版\moyin-creator-0.2.8\moyin-creator.exe`
- **ASAR**: `D:\魔因漫创开源版\moyin-creator-0.2.8\resources\app.asar`
- **Dev source (WSL)**: `/home/administrator/moyin-creator/moyin-creator/` (v0.2.3 — older, differs from 0.2.8 bundled code)
- **Image storage**: `D:\moyinxiangmu\media\{category}\` (shots/, scenes/, characters/)
- **Storage config**: `%APPDATA%\魔因漫创-profiles\default-*\storage-config.json`

## Prompt Pipeline Architecture

The software has multiple independent prompt systems. They do NOT share the same constraints:

### 1. Contact Sheet (联合图) Prompt — `scene-viewpoint-generator.ts`

Generates N×N grid scene backgrounds. Pipeline:
1. AI viewpoint analysis (`viewpoint-analyzer.ts`) → generates viewpoint names/descriptions from shot data
2. `generateContactSheetPrompt()` → assembles structured grid prompt with `<instruction>` block
3. Prompt explicitly says "NO people" (line 582) but **viewpoint descriptions from step 1 can leak character references**

PITFALL: AI viewpoint analyzer receives shot data including character names, actions, dialogues, and characterBlocking. If the system prompt doesn't forbid it, AI-generated `vp.descriptionEn` may contain phrases like "where the elderly man sits". These leak into the contact sheet panel descriptions even though the top-level prompt says "NO people".

FIX (two layers):
- **Layer 1** — viewpoint-analyzer.ts system prompt: add explicit constraint banning character references in viewpoint names/descriptions/props
- **Layer 2** — scene-viewpoint-generator.ts: add regex filter before panel descriptions are built, replacing character terms (中英文) with neutral alternatives

### 2. Scene Image Prompt — `full-script-service.ts`

The system prompt for scene calibration (line 1873) **deliberately requires** character descriptions in `imagePrompt`:
```
c) **人物描述**（每个出场人物都要写）：
   - 年龄段、服装概述、表情神态、姿势动作
```
This is by design — these prompts serve as first-frame/end-frame anchors for video generation.

### 3. S-Class Merged Grid (九宫格一键生成) — `sclass-scenes.tsx`

`generateGridAndSlice()` builds a highly structured prompt:
- `<instruction>` block with grid layout, mandatory style, consistency directive
- Each panel tagged with character count: `(1 person)`, `(N people)`, `(no people)`
- 3-layer style sandwich: MANDATORY in instruction + `[same style]` per panel + IMPORTANT at end
- Negative constraints include style-specific negative prompt

### 4. Individual Scene Image (单独生成) — `sclass-scenes.tsx`

`handleGenerateSingleImage()` uses a flat prompt:
```
{imagePromptZh}. Style: {fullStylePrompt}
```
No consistency directive, no character count, no style sandwich, no negative prompt. This is why 一键九宫格 and 单独生成 produce different results.

## ASAR Patching (Pre-built Version)

When source code changes need to be tested in the pre-built 0.2.8:

1. Kill the running process first: `powershell.exe -Command "Get-Process moyin-creator -ErrorAction SilentlyContinue | Stop-Process -Force"`
2. Extract: `npx @electron/asar extract app.asar /tmp/extract`
3. Edit the bundled JS directly (`out/renderer/assets/index-*.js`) — the code is minified but string patterns are findable
4. Repack: `npx @electron/asar pack /tmp/extract /tmp/patched.asar`
5. Replace: copy patched.asar over original (mv may need process killed first)
6. Backup original: `app.asar.orig`

NOTE: The 0.2.8 bundled code diverges significantly from the v0.2.3 dev source. Functions like `generateContactSheetPrompt` in 0.2.8 include additional features (boardRole, mustShow, mustAvoid, derivedFromZoneIds, normalizeAiViewpointsForSceneLibrary) that don't exist in the older source.

## Template Library (manifest.json)

0.2.8 uses `manifest.json` format for both GPT Image 2 and Seedance 2.0 template libraries:
```json
{
  "prompts": [
    {
      "id": "unique-id",
      "slug": "unique-id",
      "model": "gpt-image-2",
      "title": "Short title",
      "prompt": "Full prompt text with <<<slot>>> markers",
      "description": "",
      "category": "分类",
      "assets": [
        {"kind": "thumbnail", "fileName": "relative/path.jpg", "url": "https://..."},
        {"kind": "reference-image", "fileName": "relative/path.png", "url": "https://..."}
      ]
    }
  ],
  "generatedAt": "ISO timestamp",
  "source": {"url": "...", "description": "..."}
}
```

Validation: directory must contain `manifest.json` at root, with `prompts` as an array. Files referenced in `assets[].fileName` must be present (relative to library root).

Legacy template data in `模版库/catalog/templates.jsonl` uses a different format (SQLite-backed) and needs conversion.

## Manual Export Package (绕过 API 校验)

When the software won't allow export (video model not configured, grid images missing, API unset), build the submission package directly from JSON state files:

1. Read `{basePath}/projects/_p/{projectId}/sclass.json`
2. Extract group and matching splitScenes by `group.sceneIds`
3. Build `prompt.txt` replicating `buildGroupPrompt()` logic:
   ```
   多镜头叙事视频（共N个镜头，总时长Xs）：
   镜头1 [0s-2s]「sceneName」：cameraMovement, shotSize, videoPromptZh, 环境音, 音效
   ```
   Append `groupPromptHints` and `groupNarrativeHints`.
4. Build `manifest.json` with full per-scene metadata
5. Build `README.md` with usage instructions
6. Write to `D:\魔音提示词\sclass_export_{groupName}\`

Current active project IDs: `5928bbce-...` (27 groups) and `a4bbe260-...` (6 groups).

## Export Button Disabled Conditions

\"导出提交包\" greyed out when: `isGeneratingAny || isGridBusy || isExportingPackage || !onExportGroupVideoPackage`. For 九宫格 groups, also requires `canGenerateGroupVideo` (all shots must have images, grid must be assembled).

## S-Class Video Generation Prompt

`buildGroupPrompt()` (sclass-prompt-builder.ts) — priority: manual `mergedPrompt` > AI `calibratedPrompt` > auto-assembly. Format: multi-shot timeline with per-shot cinematography fields (cameraMovement, shotSize, cameraAngle, focalLength, lighting, DoF, focus, rig, atmosphere, mood), character/scene @references, audio design per shot, dialogue lip-sync segments, aspect ratio, and consistency footer.

## Key Files Map

| File | Purpose |
|------|---------|
| `src/lib/script/scene-viewpoint-generator.ts` | Contact sheet prompt assembly |
| `src/lib/script/viewpoint-analyzer.ts` | AI viewpoint analysis system prompt |
| `src/lib/script/full-script-service.ts` | Scene calibration prompt (with character descriptions) |
| `src/components/panels/sclass/sclass-scenes.tsx` | 九宫格 and 单独生成 handlers |
| `src/components/panels/sclass/sclass-calibrator.ts` | S-class group calibration (calls API) |
| `electron/main.ts` | IPC handlers, storage paths, image save |
