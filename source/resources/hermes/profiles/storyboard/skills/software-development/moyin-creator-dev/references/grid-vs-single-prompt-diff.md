# 九宫格一键生成 vs 单独生成 — 提示词差异

两者使用相同的 `getStylePrompt(currentStyleId)` 获取风格，差异完全在提示词结构。

## 单独生成 (handleGenerateSingleImage, line 1752)

```
{imagePromptZh}. Style: {fullStylePrompt}
```

无一致性指令、无人物数量约束、无负面提示词、无结构化包装。

## 一键九宫格 (generateGridAndSlice, line 2237)

```
<instruction>
Generate a clean 3x3 storyboard grid with exactly 9 equal-sized panels.
Overall Image Aspect Ratio: 16:9.
Each individual panel must have a 16:9 aspect ratio.
MANDATORY Visual Style for ALL panels: {fullStylePrompt}
Structure: No borders between panels, no text, no watermarks, no speech bubbles.
Consistency: Maintain consistent character appearance, lighting, color grading,
  and visual style across ALL panels.
</instruction>

Layout: 3 rows, 3 columns, reading order left-to-right, top-to-bottom.

Panel [row 1, col 1] [FIRST FRAME] (1 person): {desc} [same style]
Panel [row 1, col 2] [FIRST FRAME] (2 people): {desc} [same style]
...

IMPORTANT - Apply this EXACT style uniformly to every panel: {fullStylePrompt}

Negative constraints: text, watermark, split screen borders, speech bubbles, blur,
  distortion, bad anatomy, {styleNegative}
```

## 四大差异

| 维度 | 单独生成 | 一键九宫格 |
|------|---------|-----------|
| **人物一致性** | 无 | `Maintain consistent character appearance...` |
| **人物数量约束** | 无 | `(1 person)` / `(N people)` 精确标注 |
| **风格施加** | 1层：`Style:` 后缀 | 3层夹击：MANDATORY → [same style] → IMPORTANT |
| **负面提示词** | 无 | 含风格专属 negative prompt |

## 如何缩小差距

要让单独生成效果接近九宫格，需要把 `handleGenerateSingleImage` 的 prompt 也用结构化格式包一层，至少加入：
1. 风格前置 MANDATORY 指令
2. 人物一致性声明
3. 人物数量精确约束
4. 负面提示词
