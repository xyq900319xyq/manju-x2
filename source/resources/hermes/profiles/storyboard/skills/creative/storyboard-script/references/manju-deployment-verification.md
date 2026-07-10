# 漫剧助手部署验证 — storyboard-script 技能

## 背景

2026-07-02 发现：漫剧助手调用 hermes 生成「把师尊炸死了」分镜时，仅输出 54 镜（应为 100+）。根因为 `storyboard-script` 技能目录未部署到漫剧助手的 profile 路径下。

## 调用链路

```
漫剧助手 StoryboardTask
  → hermes.exe chat -q "<prompt>" --quiet
  → env: HERMES_HOME = D:\漫剧助手\resources\hermes\profiles\storyboard
    → hermes 读 SOUL.md（51行摘要，有 "≥100镜" 但无方法论细节）
    → hermes 扫描 skills/ 目录
      → 找不到 creative/storyboard-script/ → 技能无法通过 skill_view 加载
        → 模型仅凭 SOUL.md 的简陋规则 + 剧本自带 "预估镜头数：46 shots"
          → 锚定 46 附近 → 输出 54 镜（"超出预估 17%"）
```

## 对比

| 方式 | 技能状态 | 输出镜头数 |
|------|---------|-----------|
| TUI 直接使用（`~/.hermes/profiles/storyboard/`） | SKILL.md 完整加载 | **106 镜** |
| 漫剧助手调用（`resources/hermes/profiles/storyboard/`） | SKILL.md 缺失 | **54 镜** |

## 部署要求

技能源目录：
```
D:\hermes\profiles\storyboard\skills\creative\storyboard-script\
  ├── SKILL.md           ← 完整方法论（500+行）
  └── references/
      ├── director-lecture.md
      ├── master-director-heart-method.md
      └── 顶级分镜心法与实操手册.md
```

部署目标：
```
D:\漫剧助手\resources\hermes\profiles\storyboard\skills\creative\storyboard-script\
```

## 验证命令

```bash
# 检查技能目录是否存在
test -d "D:\漫剧助手\resources\hermes\profiles\storyboard\skills\creative\storyboard-script" && echo "OK" || echo "MISSING"

# 检查 SKILL.md 是否包含完整方法论（应 > 500 行）
wc -l "D:\漫剧助手\resources\hermes\profiles\storyboard\skills\creative\storyboard-script\SKILL.md"

# 检查 references 目录
ls "D:\漫剧助手\resources\hermes\profiles\storyboard\skills\creative\storyboard-script\references\"
```

## 修复命令

```bash
# 部署 storyboard-script 技能
xcopy /E /Y "D:\hermes\profiles\storyboard\skills\creative\storyboard-script" "D:\漫剧助手\resources\hermes\profiles\storyboard\skills\creative\storyboard-script\"

# 部署 storyboard-self-check 技能（分镜交付前强制自检）
xcopy /E /Y "D:\hermes\profiles\storyboard\skills\creative\storyboard-self-check" "D:\漫剧助手\resources\hermes\profiles\storyboard\skills\creative\storyboard-self-check\"
```

## 软件端预防建议

漫剧助手 `generators.py` 的 `_build_hermes_call()` 函数应在首次调用前检查目标技能目录存在性，缺失时自动从 hermes 主 profile 同步或给出明确报错（而非静默降级到 SOUL.md 模式）。

此外，`prompts.py` 的 `build_storyboard_prompt()` 应将硬约束（忽略剧本预估数字、≥100镜）放在 `{script}` 变量**之前**而非之后，防止模型先读到剧本自带的「预估 46 shots」而被锚定。
