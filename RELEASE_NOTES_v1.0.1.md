# 漫剧助手X-2 v1.0.1 — Hotfix Release

## 🚨 紧急修复

### 启动崩溃 `NameError: name 'log' is not defined`

**v1.0.0 灰度用户**首次启动后立即弹出错误对话框:

```
Unhandled exception in script
Failed to execute script 'main' due to unhandled exception:
name 'log' is not defined

File "main.py", line 229, in _run_first_run_wizard
NameError: name 'log' is not defined
```

**根因**:`source\src\main.py` `import logging` 后**漏写** module-level
`log = logging.getLogger("manju")` 赋值。函数体 `_run_first_run_wizard` 内
5 处 `log.info/log.warning` 调用 + `main()` mutex 检查 1 处 `log.warning`,
全部依赖 module-level `log` 变量,但这个变量根本不存在。

**修复**:`main.py` line 9 加一行 `log = logging.getLogger("manju")`,
所有 `log.xxx` 调用即可解析到 file-level logger(命名 "manju" 跟
`_ensure_home_env` / `_load_theme` 里 `logging.getLogger("manju")` 一致)。

**影响范围**:v1.0.0 全部用户(**P0,启动即崩,完全无法使用**)

---

## 📋 v1.0.1 安装包信息

- **文件名**:`漫剧助手X-2_v1.0.1_Setup.exe`
- **大小**:91,177,116 bytes(≈ 91.18 MB)
- **MD5**:`ffac59b7b64fc0c19d81c8dacd1bee78`
- **SHA256**:`6751461c8149521b6d05bd163305422e8a2dbbd7e3596b43d85389a0b26526ec`
- **下载**:见下方 Assets
- **签名**:(待 GPG 签名,如已配置)
- **构建时间**:2026-07-09

---

## 🔄 升级方式

### 方式 1:覆盖升级(推荐,保留 config)

直接运行 v1.0.1 Setup.exe,Inno Setup 会自动检测已安装的 v1.0.0
并提示"发现已安装版本,是否升级"。点"是"→ 软件会先关闭旧进程
(mutex 检测)→ 覆盖 EXE → 保留 `config\` / `outputs\` / `logs\` 用户数据。

### 方式 2:干净安装

1. 控制面板 → 卸载"漫剧助手X-2 v1.0.0"
2. 运行 v1.0.1 Setup.exe 全新安装

---

## 🐛 已修复问题

| # | 等级 | 描述 |
|---|------|------|
| 1 | 🔴 P0 | 启动崩溃 `NameError: name 'log' is not defined`(_run_first_run_wizard) |

完整 v1.0.1 计划见 [`V1.0.1_PLAN.md`](https://github.com/xyq900319xyq/manju-x2/blob/main/V1.0.1_PLAN.md)。

---

## ⚠️ v1.0.0 → v1.0.1 已知但**未修**问题

- 🔴 P0 `ChineseSimplified.isl` 缺失(中文用户装好看到英文 UI) — 等 ISCC 重装补 Chinese
- 🟡 P1 hermes agent "1:1 拆段" 约束(分镜生成只输出第 1 场景)
- 🟡 P1 DeepSeek thinking 模式消耗 token 导致分镜截断
- (更多见 `V1.0.1_PLAN.md`)

---

## 📞 反馈

- **Bug 报告**:[GitHub Issues](https://github.com/xyq900319xyq/manju-x2/issues/new?template=bug_report.md)
- **功能请求**:[GitHub Issues](https://github.com/xyq900319xyq/manju-x2/issues/new?template=feature_request.md)
- **问题咨询**:[GitHub Discussions](https://github.com/xyq900319xyq/manju-x2/discussions)
