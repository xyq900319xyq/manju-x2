# 漫剧助手X-2 v1.0.3 — LLM 校验逻辑修复

## 🐛 修复:设置 LLM API 时所有 config 都校验,只缺一个就报错

**症状**: 设置 → API 配置 → 添加/编辑 LLM config(DeepSeek / Agnes AI / 剑锋中转等)→ 点保存,弹"校验失败 — 第 2 项缺少字段: api_key"。即使 DeepSeek(active)已填好,Agnes AI / 剑锋中转没填也会报错。

**根因**: `source/src/ui/settings_dialog.py:1335-1346` 校验循环**遍历所有 LLM config** 都校验 5 个必填字段,跟视频 API(line 1362-1364 只校验 active)行为不一致。

**修复**: 改 settings_dialog.py:1331-1353,LLM 校验循环加 `if c.get("id") != active_id: continue`,**只校验 active config**。非 active 允许空,用户可同时维护多个未完成的 config;真要调用时再报错。

**对比**:
| 区域 | v1.0.2 行为 | v1.0.3 行为 |
|---|---|---|
| LLM 校验 | 遍历所有 config | **只校验 active** |
| 视频 API 校验 | 只校验 active | 只校验 active(不变) |

## 📋 v1.0.3 安装包信息

- **文件名**:`漫剧助手X-2_v1.0.3_Setup.exe`
- **大小**:约 91.2 MB
- **MD5**:`6f4c0003dd549afdc5f1cd99d178073c`
- **SHA256**:`2bd1ec271ba0b7b4a40868862988dac112977c52ffe5a6980214ab70b9edb7e4`
- **下载**:见下方 Assets
- **构建时间**:2026-07-09

## 🔄 升级方式

### 方式 1:覆盖升级(推荐,保留 config)

直接运行 v1.0.3 Setup.exe,Inno Setup 会自动检测已安装版本并提示升级。点"是"→ 关旧进程 → 覆盖 EXE → 保留 `config\` / `outputs\` / `logs\`。

### 方式 2:干净安装

1. 控制面板 → 卸载"漫剧助手X-2 v1.0.x"
2. 运行 v1.0.3 Setup.exe 全新安装

## 🐛 已修复问题(累计)

| # | 版本 | 等级 | 描述 |
|---|------|------|------|
| 1 | v1.0.1 | 🔴 P0 | 启动崩溃 `NameError: name 'log' is not defined` |
| 2 | v1.0.2 | 🟡 P2 | 主窗口变 light(应该 X-1 dark flat) |
| 3 | v1.0.3 | 🟡 P2 | LLM 校验遍历所有 config(应只校验 active) |

## ⚠️ 已知但**未修**问题

- 🔴 P0 `ChineseSimplified.isl` 缺失(中文用户装好看到英文 Inno Setup UI)
- 🟡 P1 hermes agent "1:1 拆段" 约束
- 🟡 P1 DeepSeek thinking 模式消耗 token

## 📞 反馈

- **Bug 报告**:[GitHub Issues](https://github.com/xyq900319xyq/manju-x2/issues/new?template=bug_report.md)
- **功能请求**:[GitHub Issues](https://github.com/xyq900319xyq/manju-x2/issues/new?template=feature_request.md)
