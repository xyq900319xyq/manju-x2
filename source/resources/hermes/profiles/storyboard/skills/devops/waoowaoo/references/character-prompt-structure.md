# 角色图片生成 Prompt 结构

## 完整公式

最终发给图片 API 的 prompt = `{角色外貌描述}，{固定后缀}，{画风prompt}`

源码：`character-image-task-handler.ts:148`
```typescript
const prompt = artStyle
  ? `${addCharacterPromptSuffix(raw)}，${artStyle}`
  : addCharacterPromptSuffix(raw)
```

## 三部分拆解

### 1. 角色外貌描述
由 AI 在角色档案确认阶段生成，存储在 `character_appearances.descriptions`（JSON 数组），通常 3 个变体，各生成一张图。

示例（陈戈变体1）：
> 陈戈，约二十多岁，面容轮廓清晰，带着利落的瓜子脸线条，眉骨分明，剑眉略微上挑，双眼为狭长内双，眼神锐利而专注，鼻梁高挺笔直，唇形偏薄且线条干净，唇角收得很紧，左脸与额前残留爆炸后常见的黑灰覆面。额前黑发被炸成鸟窝般蓬乱，发丝浓密微卷，短长不齐地翘起，几缕碎发压在眉间，整体显得凌乱却极有辨识度。身形修长匀称，肩线利落，透出少年修士特有的劲挺感。身穿灰蓝色宗门短袍，内搭白色交领中衣，衣缘以极细暗金线收边，腰束简洁布带，配少量实用型小挂囊，脚踏黑色布面短靴，靴口收窄便于行走。

### 2. 固定后缀（CHARACTER_PROMPT_SUFFIX）
源码位置：`constants.ts:192`
```
角色设定图，画面分为左右两个区域：【左侧区域】占约1/3宽度，是角色的正面特写（如果是人类则展示完整正脸，如果是动物/生物则展示最具辨识度的正面形态）；【右侧区域】占约2/3宽度，是角色三视图横向排列（从左到右依次为：正面全身、侧面全身、背面全身），三视图高度一致。纯白色背景，无其他元素。
```

### 3. 画风（getArtStylePrompt）
源码位置：`constants.ts:100-189` (ART_STYLES 数组)

| value | 中文 prompt |
|-------|-------------|
| `american-comic` | 美式漫画风格，粗犷线条，高对比，饱和色彩 |
| `chinese-comic` | 现代高质量漫画风格，动漫风格，细节丰富精致，线条锐利干净，质感饱满，超清，干净的画面风格，2D风格，动漫风格。 |
| `japanese-anime` | 现代日系动漫风格，赛璐璐上色，清晰干净的线条，视觉小说CG感。高质量2D风格 |
| `realistic` | 真实电影级画面质感，真实现实场景，色彩饱满通透，画面干净精致，真实感 |
| `3d-xuanhuan` | 3D玄幻、(best quality, masterpiece, 8k, high detailed:1.2), (stunning stylized 3D Chinese animation character render:1.3), (Unreal Engine 5 style:1.2), (cinematic lighting, soft volumetric fog:1.1), (smooth porcelain skin texture:1.1), (intricate traditional Chinese fabric details, fine embroidery, flowing robes:1.1), ethereal atmosphere, glowing spiritual energy, beautiful facial features, (delicate body proportions), sharp focus, detailed background。 |

## 其他参数

- 图片比例：`CHARACTER_ASSET_IMAGE_RATIO = '3:2'`（`constants.ts:201`）→ 常用改动为 `16:9`
- 比例到像素的映射：`generator-api.ts:33-39`
  ```
  '1:1': '1024x1024',  '16:9': '1792x1024',  '9:16': '1024x1792',
  '3:2': '1536x1024',  '2:3': '1024x1536'
  ```
- ⚠️ 生产环境修改比例的最可靠方式是**在 bodyTemplate 硬编码 `"size": "1792x1024"`**（绕过编译代码中常量内联无法更新的问题）
- 生成数量：默认 3 张（3 个描述变体各 1 张）
- 子形象（非主形象）生成时会引用主形象图片保持一致性

## 自定义修改

### 改固定后缀
编辑容器内 `/app/src/lib/constants.ts` 第 192 行 `CHARACTER_PROMPT_SUFFIX`，然后重新构建/重启。

### 改画风
在 waoowaoo 网页设置面板切换画风，或编辑 `ART_STYLES` 数组。

### 改比例
编辑第 201 行 `CHARACTER_ASSET_IMAGE_RATIO`。

### 改图片 API 模板
见 `references/api-image-template-debug.md`。
