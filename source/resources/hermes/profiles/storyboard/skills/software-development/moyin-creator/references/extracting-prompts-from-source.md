# Extracting AI Prompts from Moyin Creator Source Code

## When to use this technique

- User wants to see the **exact system prompts** sent to the AI API during script import
- Runtime interception (DevTools Network tab, proxy, logging injection) is not feasible
- Source code is available (open-source or extracted from asar)
- Need to document the full 12-step prompt compilation pipeline

## Context

魔因漫创's script import workflow uses a 12-step AI processing pipeline. Each step sends a different system prompt to the API (feature key: `script_analysis`). The prompts are embedded in TypeScript source files as template literals.

## Key source files containing prompts

All files are under `/home/administrator/moyin-creator/src/lib/`:

| File | Prompts | Purpose |
|------|---------|---------|
| `script/script-normalizer.ts` | 1 | Structure analysis, metadata extraction |
| `script/character-calibrator.ts` | 3 | Character校准, 6-layer visual anchors |
| `script/scene-calibrator.ts` | 2 | Scene art direction, visual design |
| `script/shot-calibration-stages.ts` | 5 | 5-stage shot calibration (narrative → visual → camera → first-frame → motion) |
| `script/trailer-service.ts` | 2 | Trailer shot selection |
| `script/character-stage-analyzer.ts` | 2 | Multi-stage character design |
| `script/script-parser.ts` | 3 | Episode parsing, shot generation |
| `script/viewpoint-analyzer.ts` | 2 | Scene viewpoint/camera angle analysis |
| `script/ai-character-finder.ts` | 2 | Character data generation from script |
| `script/ai-scene-finder.ts` | 2 | Scene data generation from script |
| `character/character-prompt-service.ts` | 2 | Multi-stage character visual design |
| `storyboard/scene-prompt-generator.ts` | 1 | Storyboard contact sheet prompts |
| `script/full-script-service.ts` | 1 | Full-script shot calibration |

Total: **28+ distinct system prompts** across 13 files.

## Extraction technique

### Step 1: Identify prompt patterns

Prompts are stored as:
- Template literals assigned to variables: `const systemPrompt = \`...\``
- Inline in function calls: `systemPrompt: \`...\``
- Multi-line strings with variable interpolation: `${contextLine}`, `${eraContextBlock}`

### Step 2: Use regex extraction with execute_code

```python
from hermes_tools import read_file
import re
import json

files = [
    "/path/to/script-normalizer.ts",
    "/path/to/character-calibrator.ts",
    # ... add all 13 files
]

results = []

for fpath in files:
    data = read_file(fpath, offset=1, limit=2000)  # Adjust limit for large files
    content = data['content']
    
    # Extract systemPrompt template literals
    prompts = re.findall(r'systemPrompt:\s*`([^`]+)`', content, re.DOTALL)
    
    # Also try const/let declarations
    if not prompts:
        prompts = re.findall(r'const\s+\w*[Pp]rompt\s*=\s*`([^`]+)`', content, re.DOTALL)
    
    if prompts:
        fname = fpath.split('/')[-1]
        results.append({
            'file': fname,
            'prompts_count': len(prompts),
            'prompts': prompts[:3]  # Limit output to avoid token overflow
        })

print(json.dumps(results, ensure_ascii=False, indent=2))
```

### Step 3: Handle large files (>2000 lines)

For files like `shot-calibration-stages.ts` (413 lines) or `episode-parser.ts` (1117 lines):

1. **Check line count first**:
   ```bash
   wc -l /path/to/file.ts
   ```

2. **Use search_files with context** to locate prompt start lines:
   ```python
   search_files(
       path="/path/to/file.ts",
       pattern="你是|You are|systemPrompt:",
       context=80
   )
   ```

3. **Read specific line ranges** with `read_file(offset=N, limit=M)`:
   ```python
   # If search shows prompt starts at line 184
   read_file(path="/path/to/shot-calibration-stages.ts", offset=184, limit=100)
   ```

### Step 4: Extract the 5-stage shot calibration prompts

`shot-calibration-stages.ts` contains the most complex pipeline. The 5 stages are:

| Stage | Lines | System Prompt Variable | Purpose |
|-------|-------|------------------------|---------|
| 1 | 184-208 | `s1System` | 叙事骨架 (narrative structure) |
| 2 | 233-243 | `s2System` | 视觉描述 (visual description) |
| 3 | 262-281 | `s3System` | 拍摄控制 (camera control) |
| 4 | 322-342 | `s4System` | 首帧提示词 (first-frame prompt) |
| 5 | 382-397 | `s5System` | 动态+尾帧提示词 (motion + end-frame) |

Each stage uses `runStage()` helper which calls `processBatched()` → `callFeatureAPI()` → `callChatAPI()` in `script-parser.ts`.

### Step 5: Save extracted prompts to output file

```python
import json

output_path = "/mnt/d/魔音提示词/all_system_prompts.json"

with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

print(f"Saved {len(results)} files with prompts to {output_path}")
```

## Pitfalls

1. **Template literal interpolation**: Prompts contain `${variable}` placeholders. To get the **actual runtime prompt**, you need to:
   - Trace variable definitions (e.g., `${eraContextBlock}`, `${narrativeAnchorBlock}`)
   - Understand conditional logic (e.g., `promptLanguage === 'zh'` changes output fields)
   - See `references/api-request-capture.md` for runtime logging approach

2. **Minified code in asar**: If working with pre-built binary without source access, prompts are in minified JS with no line breaks. Use:
   ```bash
   asar extract app.asar app-extracted
   grep -r "你是.*专业" app-extracted/out/main/ | head -20
   ```

3. **Multi-file dependencies**: Some prompts reference shared context builders:
   - `getMediaTypeGuidance()` in `lib/generation/media-type-tokens.ts`
   - `getCinematographyGuidance()` in `lib/constants/cinematography-profiles.ts`
   - `getVisualStyleDescription()` in `lib/constants/visual-styles.ts`

4. **Prompt language switching**: Many prompts have dual-language support controlled by `promptLanguage` parameter:
   - `'zh'` → Chinese-only fields (`imagePromptZh`, `videoPromptZh`)
   - `'en'` → English-only fields (`imagePrompt`, `videoPrompt`)
   - `'both'` → Both languages (default)

5. **File size limits**: `read_file()` rejects reads >100K chars. For large files:
   - Use `offset` and `limit` to read in chunks
   - Or use `terminal()` with `head`/`tail`/`sed` to extract specific line ranges

6. **Cross-filesystem performance**: Reading files from `/mnt/d/` (Windows drive) in WSL is slow. Copy to WSL native filesystem first:
   ```bash
   rsync -a /mnt/d/moyin-creator-source/ /home/administrator/moyin-creator/
   ```

## Alternative: Runtime logging injection

If you need the **actual compiled prompts with all variables resolved**, see `references/api-request-capture.md` for the runtime logging approach:

1. Modify `src/lib/script/script-parser.ts` → `callChatAPI()` function
2. Add `fs.appendFileSync()` to log request body before sending
3. Run in dev mode (`npm run dev`)
4. Trigger script import in the app
5. Read logged requests from output file

This captures the exact JSON sent to the API, including all interpolated variables and conditional logic.

## Example output structure

```json
[
  {
    "file": "script-normalizer.ts",
    "prompts_count": 1,
    "prompts": [
      "你是剧本结构分析专家。分析用户提供的剧本/角色规格文本，识别结构要素并提取剧级元数据。\n\n严格返回以下 JSON 格式（不要添加任何其他内容）：\n{\n  \"title\": \"作品名称\",\n  \"era\": \"时代背景（古代/现代/民国/清末/未来/当代等）\",\n  ..."
    ]
  },
  {
    "file": "character-calibrator.ts",
    "prompts_count": 3,
    "prompts": [
      "你是专业的影视剧本分析师，擅长从剧本数据中识别和校准角色。...",
      "你是好莱坞顶级角色设计大师，曾为漫威、迪士尼、皮克斯设计过无数经典角色。...",
      "请为以下角色生成专业视觉提示词和6层身份锚点：..."
    ]
  }
]
```

## User's installation paths (for reference)

- **Pre-built binary**: `D:\魔因漫创开源版\moyin-creator-0.2.7\win-unpacked\moyin-creator.exe`
- **Project data**: `D:\moyinxiangmu\projects\_p\{project-id}\`
- **Dev source (WSL)**: `/home/administrator/moyin-creator/`
- **Output directory**: `D:\魔音提示词\` (user's preferred location for extracted data)

When user asks "魔因不是你安装的吗？你不知道安装路径？", the answer is YES — these paths are documented in the skill and should be used directly without asking.
