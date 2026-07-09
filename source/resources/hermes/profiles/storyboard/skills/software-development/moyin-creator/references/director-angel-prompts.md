# Director Angel vs buildGroupPrompt — Two Completely Different Prompts

The prompt that `buildGroupPrompt` (in `sclass-prompt-builder.ts`) assembles is NOT what gets sent to the API. The actual video submission goes through **Director Angel**, which wraps the base prompt in a much richer structure.

## Director Angel Output Structure

```
提交级视觉风格硬规则：
最终视频必须使用项目视觉风格：{style tokens}
该视觉风格优先级高于 Board 参考图...
[九宫格文字模式声明]

Director Angel guidance:

Base compiled prompt:
{buildGroupPrompt auto-assembled output}

导演校准要点：组间承接策略；动作因果；同一空间约束
组间承接建议：当前组默认独立提交
【单镜出镜控制】：
- 出镜表：镜头1: 无角色/环境镜；镜头2: 陈戈...
【标准分组连续构图锁定】：（仅标准分组）
- 构图基准、硬锁位、轴线规则、站位摘要
片段级改编事实层：
1. 【空间建立】...
2. 【动作爆发】...
3. 连续性控制...
4. 【结果落点】...

镜头1 [0s-2s]「场景名」：
  出镜角色: 无；只拍环境/空间/道具
  镜头语言: 景别 MS；运镜 固定机位；特殊技法 字幕先行
  镜头职责: 动作起势 + 氛围铺垫
  表演节点: 手部/起势动作
  动作推进: ...
  叙事职责: action / 动作起势
  组织要求: 节奏 build

Execution profile: Seedance 2.0 · 标准叙事 --resolution 720p --ratio 16:9 --duration 12 --camera_fixed false
```

## Key Differences from buildGroupPrompt

| Aspect | buildGroupPrompt | Director Angel |
|--------|-----------------|----------------|
| Per-shot metadata | cameraMovement, shotSize, action | + 出镜角色, 镜头职责, 表演节点, 叙事职责, 组织要求 |
| Character control | `@图片1（角色名）保持角色外观一致` | Per-shot 出镜表 + 硬锁位 + 开场露出要求 |
| Style injection | NONE (line 734 disabled) | Injected in 提交级视觉风格硬规则 block |
| Scene references | Collected but NOT sent as images | Text-only: "场景参考图只锁物理空间/光线/方向" |
| Group chaining | N/A | Always "独立提交" strategy |

## API Request Structure

- **Model**: `doubao-seedance-2-0-260128`
- **Endpoint**: `POST /v1/volc/v1/contents/generations/tasks` (through user's proxy at `chuangwei.cyou`)
- **Content format**:
  ```json
  {
    "model": "doubao-seedance-2-0-260128",
    "content": [
      {"type": "text", "text": "{Director Angel compiled prompt}"},
      {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}, "role": "first_frame"}
    ]
  }
  ```
- Reference images are base64-encoded inline (not HTTP URLs)
- Scene reference images NEVER appear despite being available

## Scene Reference Image Bug

`collectSceneRefs` correctly collects `local-image://scenes/xxx.png` URLs. But Director Angel's video submission pipeline silently drops them — only `first_frame` images are resolved and included. Scene refs appear only as text instructions in the prompt body.
