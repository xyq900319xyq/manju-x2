# Moyin Creator (魔因漫创) — Complete Analysis

> Reference for `electron-app-analysis` skill. Session: 2026-05-20.

## Software Overview

**Name:** 魔因漫创 (Moyin Creator)
**Version:** 0.2.7 (installed), 0.2.3 (source on GitHub)
**Type:** Electron 30 + React 18 + TypeScript + Zustand 5
**License:** AGPL-3.0 (open source) + Commercial license available
**Repo:** https://github.com/memecalculate/moyin-creator
**Stars:** 3500+
**Author:** MemeCalculate (memecalculate@gmail.com)

### Workflow Panels
```
📝 剧本 → 🎭 角色 → 🌄 场景 → 🎬 导演 → ⭐ S级 (Seedance 2.0)
```

## File Locations (Installed)

| Path | Purpose |
|------|---------|
| `D:\魔因\moyin-creator\` | App install directory |
| `D:\魔因\moyin-creator\resources\app.asar` | Packaged app (150MB) |
| `D:\魔因项目\` | Project data (user configured) |
| `D:\魔因项目\projects\_p/{uuid}/sclass.json` | S-class project state (770KB) |
| `D:\魔因项目\projects\_p/{uuid}/director.json` | Director shot data |
| `D:\魔因项目\projects\_p/{uuid}/script.json` | Parsed script |
| `D:\魔因项目\projects/_shared/` | Shared characters/scenes/media |
| `D:\魔因项目\projects/_system/config-reset-state.json` | Config reset record |
| `D:\魔因项目\media/characters/` | Generated character images |
| `D:\魔因项目\media/scenes/` | Generated scene images |
| `D:\魔因项目\media/shots/` | Generated shot images |
| `%APPDATA%\Roaming\魔因漫创-profiles\default-*/studio-run/runtime.db` | Runtime task DB |
| `%APPDATA%\Roaming\魔因漫创-profiles\default-*/workspace-data/` | Workspace copy |
| `%APPDATA%\Roaming\魔因漫创\` | Legacy user data |
| `%LOCALAPPDATA%\moyin-creator-updater\` | Auto-updater |

## API Architecture

### Proxy Chain
```
Moyin Creator (Electron renderer)
  │
  ├─ POST/GET → https://chuangwei.cyou/api/ai/*   (创维 middleware)
  │              │
  │              ├── /api/ai/screenplay → LLM text (GPT/Gemini)
  │              ├── /api/ai/image        → Image gen
  │              ├── /api/ai/video        → Video gen
  │              └── /api/ai/task/:id     → Polling
  │
  └─ POST/GET → https://memefast.top/alibailian/api/v1/...  (Seedance direct)
                 │
                 ├── .../video-synthesis → Seedance 2.0 submit
                 └── /api/v1/tasks/:id   → Polling
```

### Auth Methods

| Target | Auth Location |
|--------|--------------|
| `chuangwei.cyou/api/ai/*` | `apiKey` in request **body** (no Authorization header) |
| `memefast.top/alibailian/...` | `Authorization: Bearer {apiKey}` header |
| `dashscope.aliyuncs.com/...` | `Authorization: Bearer {apiKey}` + `X-DashScope-Async: enable` |

### API Key
`sk-H6Q****PPDi` (extracted from runtime.db job payloads)

### Providers
Primary: `1ec066ef-c336-40c8-a446-7efc2eb27874` (创维 最新大模型API)

## Runtime Database Schema

### studio_run_tasks (13 rows)
Columns: id, category, label, project_id, module_source, lane, provider, model,
artifact_type, artifact_id, artifact_label, route_tab, route_label,
external_task_id, priority, progress, progress_mode, pausable, cancellable,
max_retries, payload_json, status, error_text, summary_json, attempt_count,
created_at, started_at, updated_at, completed_at, next_run_at

### studio_run_jobs (13 rows)
Columns: task_id, queue_name, job_kind, job_payload_json, job_state,
created_at, updated_at

### Job Kinds Observed
- `script-import-full-workflow` — Import script with Gemini
- `script-generate-synopses` — Generate episode synopses
- `script-scene-calibration` — Calibrate scenes
- `script-character-calibration` — Calibrate characters
- `script-calibrate-episode-shots` — Calibrate shots
- `script-regenerate-all-shots` — Regenerate all 558 shots with GPT-5.4
- `character-image-generation` — Generate character sheets
- `scene-image-generation` — Generate scene concept art
- `scene-contact-sheet` — Generate 3x3 scene grid
- `scene-orthographic-image` — Generate orthographic views

## Models Used (from runtime.db)

| Model | Task | Provider |
|-------|------|----------|
| `gpt-5.4` | Script processing, shot regeneration | custom (chuangwei.cyou) |
| `gemini-3.1-pro-preview` | Scene/character calibration | custom |
| `gpt-image-2-reverse` | Character & scene images, orthographic views | custom |

## Seedance 2.0 Video Generation

### HappyHorse R2V Request (memefast.top path)
```
POST https://memefast.top/alibailian/api/v1/services/aigc/video-generation/video-synthesis
Authorization: Bearer {apiKey}
Content-Type: application/json

{
  "model": "happyhorse-1.0-r2v",
  "input": {
    "prompt": "full shot description...",
    "media": [
      {"type": "reference_image", "url": "https://..."},
      {"type": "reference_image", "url": "https://..."}
    ]
  },
  "parameters": {
    "resolution": "720P",
    "watermark": false,
    "ratio": "16:9",
    "duration": 12
  }
}
```

### Seedance 2.0 Volc Proxy Request (via memefast.top)
```
POST .../video-synthesis
Authorization: Bearer {apiKey}
{
  "model": "happyhorse-1.0-r2v",
  "content": [
    {"type": "text", "text": "prompt... --resolution 720p --ratio 16:9 --duration 12"},
    {"type": "image_url", "image_url": {"url": "..."}, "role": "reference_image"}
  ],
  "resolution": "720p",
  "ratio": "16:9",
  "watermark": false,
  "duration": 12,
  "generate_audio": true,
  "req_id": "req-{timestamp}-{random}",
  "messages": [{"role": "user", "content": [...]}]
}
```

### Seedance 2.0 Constraints
- Input: ≤9 images + ≤3 videos (≤15s each) + ≤3 audio (MP3, ≤15s) + text (≤5000 chars), total ≤12 files
- Output: 4-15s, 480p/720p/1080p, 16:9/9:16/4:3/3:4/21:9/1:1
- Model aliases: doubao-seedance-1-0-pro-250528, doubao-seedance-2-0-260128, doubao-seedance-2-0-fast-260128

## Built-in Model Registry

All models registered in `index-BiEM7W1o.js` under DEFAULT_PROVIDERS:

**Chat models:** gemini-2.5-flash, gpt-5.4, claude-sonnet-4-20250514, claude-haiku-4-5-20251001, deepseek-r1, deepseek-v3, deepseek-v3.1-terminus, qwen3-max, qwen-plus, ...

**Image models:** gpt-image-2-reverse, gpt-image-2-all, flux-dev, flux-pro, flux-ultra, sd3.5-large-turbo, sdxl, ...

**Video models:** happyhorse-1.0-r2v, happyhorse-1.0-i2v, happyhorse-1.0-t2v, happyhorse-1.0-video-edit, doubao-seedance-1-0-pro-250528, doubao-seedance-2-0-260128, doubao-seedance-2-0-fast-260128, kling-video, kling-omni-video, veo3.1, minimax/video-01, grok-video-10s, grok-video-15s, runway, luma, cogvideo, hunyuan-video, pika, ...

## Character Prompt Compilation

### Style: 3d_xuanhuan (3D玄幻)
```
Positive: (best quality, masterpiece, 8k, high detailed:1.2), (stunning stylized 3D Chinese animation character render:1.3), (Unreal Engine 5 style:1.2), (cinematic lighting, soft volumetric fog:1.1), (smooth porcelain skin texture:1.1), (intricate traditional Chinese fabric details, fine embroidery, flowing robes:1.1), ethereal atmosphere, glowing spiritual energy, beautiful facial features, (delicate body proportions), sharp focus, detailed background

Negative: (worst quality, low quality, bad quality:1.4), (blurry, fuzzy, distorted, out of focus:1.3), (2D, flat, drawing, painting, sketch, anime, cartoon:1.2), (realistic, photo, real life, photography:1.1), (western style, modern clothing), (extra limbs, missing limbs, mutated hands, distorted body), ugly, watermark, signature, text, easynegative, bad-hands-5
```

### Full Prompt Assembly Formula (buildCharacterSheetPrompt)
```
finalPrompt = basePrompt + ", " + contentPrompt + ", " + whiteBackground + ", " + styleTokens + ", " + detailSuffix

Where:
  basePrompt = 专业角色设计参考图，"陈戈"，{characterDescription}
  characterDescription = primaryVisualPrompt + anchorPrompt + eraPrompt
  anchorPrompt = faceShape+jawline+cheekbones + eyeShape+eyeDetails+nose+lip
               + uniqueMarks + colorAnchors(#RRGGBB) + skinTexture + hairStyle
  contentPrompt = THREE_VIEW + EXPRESSIONS + PROPORTIONS + POSES
  whiteBackground = "角色参考图版式, pure solid white background, isolated character on white background, absolutely no background scenery"
  styleTokens = (best quality, masterpiece, 8k, high detailed:1.2), (stunning stylized 3D Chinese animation character render:1.3), ...
  detailSuffix = "detailed illustration, concept art, character model sheet"
```

### Identity Anchors (陈戈 example)
```
faceShape: 鹅蛋形
jawline: 棱角分明，展现果敢性格
cheekbones: 略高且清晰，增加智力感
eyeShape: 杏仁形，眼尾略微上挑
eyeDetails: 双眼皮，瞳孔清澈，眼神中带着一种审视物理规律的冷静
noseShape: 高鼻梁，鼻尖微窄，线条流畅
lipShape: 薄唇，唇线清晰，嘴角常带一抹自信的微笑
uniqueMarks: [右眼角下方2cm黑色小泪痣, 左侧眉骨细浅旧伤疤, 指尖暗红色化学痕迹]
colorAnchors: {iris: "#3D2314", hair: "#1A1A1A", skin: "#F5E6D3", lips: "#A65E5E"}
skinTexture: 皮肤细腻，鼻翼两侧有极轻微的毛孔质感
hairStyle: 全束发，头顶梳成发髻，配以墨色玉簪或玉冠，余发自然垂于脑后
hairlineDetails: 带有微小美人尖的自然发际线
```

### SHEET_ELEMENTS (selectable view types)
| ID | Label | Prompt |
|----|-------|--------|
| three-view | 三视图 | front view, side view, back view, turnaround |
| expressions | 表情设定 | expression sheet, multiple facial expressions, happy, sad, angry, surprised |
| proportions | 比例设定 | height chart, body proportions, head-to-body ratio reference |
| poses | 动作设定 | pose sheet, various action poses, standing, sitting, running |

### Character Avoid/Exclusion System
Each character can have:
- `avoid`: ["金色头发", "蓝色眼睛", "眼镜", "现代手表", "拉链", "西装", "T恤", "运动鞋", "手机", "现代实验室器材"]
- `styleExclusions`: ["动漫风格", "Q版", "抽象艺术", "油画厚涂", "赛博朋克霓虹灯"]

These are appended to the base negative prompt at generation time.

## Source Code Architecture

### Key Directories (from GitHub)
```
src/
├── packages/ai-core/          # AI engine (opencut)
│   ├── api/                   # Task queue, poller
│   ├── protocol/              # Worker communication
│   ├── providers/             # Provider interfaces
│   ├── services/
│   │   ├── prompt-compiler.ts # Mustache templates
│   │   └── character-bible.ts # Character consistency
│   └── types/                 # TypeScript types
├── stores/
│   ├── sclass-store.ts        # S-class / Seedance 2.0
│   ├── api-config-store.ts    # API key management
│   ├── director-store.ts      # Director / shot management
│   ├── character-library-store.ts
│   ├── scene-store.ts
│   └── script-store.ts
├── components/panels/
│   ├── sclass/                # S-class UI
│   ├── director/              # Director UI
│   ├── characters/            # Character panel
│   ├── scenes/                # Scene panel
│   └── script/                # Script panel
├── lib/ai/
│   ├── worker-bridge.ts       # Web Worker comm
│   ├── image-generator.ts
│   ├── model-registry.ts
│   └── batch-processor.ts
└── constants/
```

### Build System
- `electron-vite` (Vite 5 based) — compiles main + preload + renderer
- `electron-builder` — packages to NSIS installer (Windows), DMG (macOS)
- Dev: `npm run dev` (electron-vite dev)
- Build: `npm run build` (electron-vite build + electron-builder)
- CORS proxy in dev mode: `/__api_proxy?url=...` middleware

## Submitted Video Prompt (sclass-final-submitted-prompt)

Found at: `D:\魔因项目\projects\sclass-final-submitted-prompt-1-1-青云宗洞府-(镜头1-5)-2026-05-19T15-21-04-085Z\`

**Manifest:**
```json
{
  "debugKind": "sclass-final-submitted-prompt",
  "dumpedAt": "2026-05-19T15:21:04.085Z",
  "request": {
    "projectId": "80120cc3-122b-49ba-b1f8-ba98ff2b992c",
    "groupId": "grp_mpcni2in_5rt397",
    "groupName": "1-1 青云宗洞府 (镜头1-5)",
    "generationStyle": "standard",
    "providerId": "2fbae978-8654-432f-b545-1541408bfab9",
    "platform": "memefast",
    "model": "happyhorse-1.0-r2v",
    "duration": 12,
    "aspectRatio": "16:9",
    "videoResolution": "720p",
    "enableAudio": true,
    "source": "task_runtime"
  }
}
```

The prompt.txt (10,202 chars) contains full cinematographic instructions with:
- Visual style rules with UE5/3D animation tokens
- 5-shot sequence with detailed camera specs per shot
- Role appearance control table
- Audio design per shot (ambient + SFX)
- Director Angel calibration guidance
- Continuity rules across shot groups

## Projects in Runtime DB

| Project ID | Name | Status |
|-----------|------|--------|
| `80120cc3-122b-49ba-b1f8-ba98ff2b992c` | 修仙界禁止搞军火1 | Active, 158 scenes, 30 shot groups |
| `e62613c5-dca1-4c72-afb0-067a6087cdde` | 修仙界禁止搞军火 | Inactive |
| `a4bbe260-0127-49c7-9230-e766402663c7` | 灌篮少女（演示） | Demo |
