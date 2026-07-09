# Prompt Compilation Formula — Moyin Creator

Derived from source code at `src/packages/ai-core/services/prompt-compiler.ts` and the compiled `index-BiEM7W1o.js` (function `buildCharacterSheetPrompt$1` at line ~139589).

## Character Sheet Prompt

The final prompt sent to `POST {baseUrl}/api/ai/image` is assembled from these layers:

```
finalPrompt = basePrompt + ", " + contentPrompt + ", " + layoutPrompt + ", " + whiteBackground + ", " + styleTokens + ", " + detailSuffix
```

### 1. basePrompt
```
Chinese:  专业角色设计参考图，"陈戈"，{characterDescription}
English:  professional character design sheet for "Chen Ge", {characterDescription}
```

**characterDescription** is composed from:
- **primaryVisualPrompt**: user's `visualPromptZh` (preferred) or `visualPromptEn`
- **anchorPrompt**: from `buildPromptFromAnchors(identityAnchors, hasReferenceImages, promptLanguage)`:
  - *Without* reference images (full detail): face shape, jawline, cheekbones, eye shape/details, nose shape, lip shape, unique marks, color anchors (`瞳色#3D2314，发色#1A1A1A`), skin texture, hair style, hairline
  - *With* reference images (reduced): only unique marks + color anchors
- **eraPrompt**: e.g. `2020年代当代中国时尚，现代休闲风` or `{era}时期服饰风格`

### 2. contentPrompt (from SHEET_ELEMENTS selected by user)
```
three-view   → "front view, side view, back view, turnaround"
expressions  → "expression sheet, multiple facial expressions, happy, sad, angry, surprised, neutral"
proportions  → "body proportion reference, height chart, head-to-body ratio guide"
poses        → "pose sheet, various action poses, standing, sitting, running, jumping"
```

### 3. layoutPrompt
```
Chinese:  角色参考图版式
English:  character reference sheet layout
```

### 4. whiteBackground (fixed hard constraint)
```
pure solid white background, isolated character on white background, absolutely no background scenery
```

### 5. styleTokens (from style preset, e.g. `3d_xuanhuan`)
```
(best quality, masterpiece, 8k, high detailed:1.2), (stunning stylized 3D Chinese animation character render:1.3), (Unreal Engine 5 style:1.2), (cinematic lighting, soft volumetric fog:1.1), (smooth porcelain skin texture:1.1), (intricate traditional Chinese fabric details, fine embroidery, flowing robes:1.1), ethereal atmosphere, glowing spiritual energy, beautiful facial features, (delicate body proportions), sharp focus, detailed background
```

### 6. detailSuffix
```
Chinese:  精细插画, 概念艺术, 角色模型表
English:  detailed illustration, concept art, character model sheet
```

## Negative Prompt Assembly

```javascript
let negative = "blurry, low quality, watermark, text, cropped";  // base
// Realistic mode adds: ", anime, cartoon, illustration"

if (charNegativePrompt) {
    const avoidList = charNegativePrompt.avoid || [];        // e.g. ["金色头发", "蓝色眼睛", "眼镜", ...]
    const styleExclusions = charNegativePrompt.styleExclusions || [];  // e.g. ["动漫风格", "Q版", "抽象艺术", ...]
    negative += ", " + [...avoidList, ...styleExclusions].join(", ");
}
```

## API Request Format

```
POST https://chuangwei.cyou/api/ai/image
Content-Type: application/json

{
  "prompt": "<assembled prompt>",
  "negativePrompt": "<assembled negative>",
  "aspectRatio": "1:1",
  "apiKey": "sk-...",
  "provider": "memefast",
  "referenceImages": ["data:image/png;base64,..."]  // optional
}
```

Note: `apiKey` goes in the request **body**, not in an `Authorization` header.

## Scene Contact Sheet Prompt

Generated via `scene-contact-sheet` job kind. The prompt uses an `<instruction>` tag format:

```
<instruction>
Generate a clean 3x3 storyboard grid with exactly 9 equal-sized panels.
Overall Image Aspect Ratio: 16:9.
Each individual panel must have a 16:9 (horizontal landscape) aspect ratio.
MANDATORY Visual Style for ALL panels: {styleTokens}
...
```

## Why copying the prompt directly to another API fails

1. **chuangwei.cyou proxy**: routes to different backends (SD/Flux/DALL-E), model `gpt-image-2-reverse` is internal mapping
2. **Weight syntax**: `(term:1.2)` only works with SD/Flux backends
3. **Negative prompt enrichment**: software auto-appends character-specific avoid lists
4. **Reference image encoding**: images are base64-encoded and embedded in the request body
5. **Color anchors**: hex codes like `#3D2314` compiled into prompt for color-locking

## Source References

- `src/packages/ai-core/services/prompt-compiler.ts` — Mustache template engine
- `src/components/panels/characters/GenerationPanel.tsx` → `buildCharacterSheetPrompt$1` — assembler
- `src/components/panels/characters/GenerationPanel.tsx` → `buildPromptFromAnchors` — identity anchor compiler
- `src/constants/style-presets.ts` → `STYLES_3D` — style token definitions
