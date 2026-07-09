# 外部 Prompt 注入覆盖 Skill 规则 — 诊断案例

## 症状

模型输出中出现「根据用户特别指令，打破单段≤15秒限制……」等文字，同时格式严重退化：场景不拆分、镜头用简化格式、审查缺条、Base Prompt 写英文。

## 根因

调用软件 `src/core/prompts.py` 第 458 行注入了与 Skill 冲突的指令：

```
不要按 SKILL 里的"单段 ≤15秒"规则……一段分镜对应一个 Segment……让 Seedance 自己处理分段。
```

模型不是违反规则，而是在执行调用方注入的指令。

## 修复

将 `prompts.py` L458 替换为执行 Skill 规则的版本：

```
严格按照 skill 的拆段规则：每个 Segment ≤5 镜，≤15s。场景超限必须拆分。禁止整场景塞一个 Segment。
```

## 诊断命令

```bash
grep -rn "不要按 SKILL\|Seedance 自己处理\|一段分镜对应一个 Segment\|特别指令" .
```

## 教训

Skill 规则可被外部 prompt 注入覆盖。格式退化 + "特别指令"关键词 = 先查调用代码。
