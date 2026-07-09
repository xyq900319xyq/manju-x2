# Prompt Templates — 魔因漫创

Full prompt templates extracted from source code analysis.

## Contact Sheet (联合图) Prompt — `scene-viewpoint-generator.ts`

```
<instruction>
Generate a clean NxN storyboard grid with exactly M equal-sized panels.
Overall Image Aspect Ratio: 16:9.
Each individual panel must have a 16:9 (horizontal landscape) aspect ratio.
MANDATORY Visual Style for ALL panels: {fullStylePrompt}
Structure: No borders between panels, no text, no watermarks, no speech bubbles.
Consistency: Maintain consistent perspective, lighting, color grading, and visual style across ALL panels.
Subject: Interior design and architectural details only, NO people.
</instruction>
Layout: N rows, N columns, reading order left-to-right, top-to-bottom.
Scene Context: Architecture: x, Color palette: y, Era: z, Lighting: w
Panel [row 1, col 1] (no people): VIEWPOINT_NAME: description [same style]
Panel [row 1, col 2] (no people): ...
Panel [row N, col N]: empty placeholder, solid gray background
IMPORTANT - Apply this EXACT style uniformly to every panel: {fullStylePrompt}
Negative constraints: text, watermark, split screen borders, speech bubbles, blur, distortion, bad anatomy, people, characters, distorted grid, uneven panels.
```

Chinese version appends: `只有背景，没有人物。`

## 九宫格 (Merged Grid) Prompt — `generateGridAndSlice`, sclass-scenes.tsx

```
<instruction>
Generate a clean 3x3 storyboard grid with exactly 9 equal-sized panels.
Overall Image Aspect Ratio: 16:9.
Each individual panel must have a 16:9 (horizontal landscape) aspect ratio.
MANDATORY Visual Style for ALL panels: {fullStylePrompt}
Structure: No borders between panels, no text, no watermarks, no speech bubbles.
Consistency: Maintain consistent character appearance, lighting, color grading, and visual style across ALL panels.
</instruction>
Layout: 3 rows, 3 columns, reading order left-to-right, top-to-bottom.
Panel [row 1, col 1] [FIRST FRAME] (1 person): {imagePromptZh} [same style]
Panel [row 1, col 2] [FIRST FRAME] (2 people): {imagePromptZh} [same style]
...
Panel [row 3, col 3]: empty placeholder, solid gray background
IMPORTANT - Apply this EXACT style uniformly to every panel: {fullStylePrompt}
Negative constraints: text, watermark, split screen borders, speech bubbles, blur, distortion, bad anatomy, {styleNegative}
```

Key differences from contact sheet: character appearance consistency, character counts per panel, [FIRST FRAME]/[END FRAME] labels, style-specific negatives.

## Single Image Generation — `handleGenerateSingleImage`, sclass-scenes.tsx

```
{imagePromptZh}. Style: {fullStylePrompt}
```

Flat, no structure. Reference images: scene background + character refs + storyboard image.

## S-Class Video Prompt — `buildGroupPrompt`, sclass-prompt-builder.ts

```
多镜头叙事视频，参考 @图片1 格子图（共N个镜头，总时长Xs）：

镜头1 [0s-5s]「场景名」：{cameraMovement}, {shotSize}, {cameraAngle}, {focalLength}, camera: {cameraPosition}, {videoPrompt}, lighting: {lightingStyle}, {lightingDirection}, {colorTemperature}, DoF: {depthOfField}, focus: {focusTarget}, rig: {cameraRig}, atmosphere: {atmosphericEffects}, mood: {emotionTags}

镜头2 [5s-9s]「场景名」：...

角色参考：@图片2（角色A）保持角色外观一致；@图片3（角色B）保持角色外观一致
场景参考：@图片4 作为场景参考

音频设计：
镜头1：环境音：xxx；音效：xxx

对白与口型同步：
[约2s处] 角色名：「台词」— 口型同步，自然口部动作

画幅：16:9

全部镜头保持角色外观一致，镜头间平滑过渡，不出现文字或水印。
```

## Scene Calibration System Prompt — `full-script-service.ts`

Full system prompt for the 分镜校准 (shot calibration) pipeline — a 30-field output schema covering visual descriptions, 3-tier prompts (image/video/endFrame), narrative design, cinematography controls, and audio design. The prompt explicitly requires character descriptions in image prompts (section c): age, clothing, expression, pose — this is by design, not a bug.

## AI Viewpoint Analysis Prompt — `viewpoint-analyzer.ts`

```
你是专业的影视美术指导，擅长分析场景并确定需要的拍摄视角。

【任务】根据本集大纲、场景信息和分镜内容，分析该场景需要哪些不同的视角/机位来生成场景背景图。

【重要原则】
1. 视角必须与场景类型匹配
2. 从分镜动作和画面描述中提取实际需要的视角
3. 结合本集大纲理解场景的叙事功能
4. 每个视角要有关键道具
5. 输出4-6个视角
```

Input includes shot summaries with actionSummary, visualDescription, visualFocus, dialogue, ambientSound, characterBlocking, shotSize, cameraMovement — hence character leakage into viewpoint descriptions.
