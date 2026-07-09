# 漫剧助手X-2 v1.0.2 — 主题修复

## 🐛 修复:主窗口变成 Qt light default(应该是 X-1 暗色 flat)

**症状**: v1.0.0 / v1.0.1 装好走完首次启动 wizard 后,主窗口渲染成 **Qt light default**(浅色 + 菜单栏白底 + 工具栏浅灰),不是 X-1 设计的 **dark flat**(暗色 + 菜单栏/工具栏/项目树)。

**根因**: Phase 1 fork 源码时漏复制 X-1 的 `assets/` 目录(包含 `theme.qss`)。`_load_theme()` 函数能正确找到 QSS 文件,只是文件不存在。X-1 spec 自己也漏打包 `assets/`,所以 X-1 装的 EXE 也是 Qt light default — 是 X-1 早就有的 bug。

**修复**:
1. 复制 `D:\漫剧助手\assets\theme.qss` (14,656 bytes) → `source/assets/theme.qss`
2. `漫剧助手X-2.spec` `datas` 加 `('assets', 'assets')` 让 PyInstaller 把 theme.qss 打到 `_internal/assets/`
3. `main_window.py` `APP_TITLE` 从 `"漫剧助手X-1 v0.7.8.85"` → `"漫剧助手X-2"`

**影响**: v1.0.0 / v1.0.1 全部用户(主窗口视觉 bug,但功能完整)

---

## 📋 v1.0.2 安装包信息

- **文件名**:`漫剧助手X-2_v1.0.2_Setup.exe`
- **大小**:约 91.2 MB
- **MD5**:`8e8228d1a08e9fc235c216e78abb255d`
- **SHA256**:`e2ec479f3cb7b712a288b0f393d8b6697953ab65f14c098608ec702261ec97bc`
- **下载**:见下方 Assets
- **构建时间**:2026-07-09

---

## 🔄 升级方式

### 方式 1:覆盖升级(推荐,保留 config)

直接运行 v1.0.2 Setup.exe,Inno Setup 会自动检测已安装的 v1.0.0 / v1.0.1 并提示升级。点"是"→ 软件会先关闭旧进程(mutex 检测)→ 覆盖 EXE → 保留 `config\` / `outputs\` / `logs\` 用户数据。

### 方式 2:干净安装

1. 控制面板 → 卸载"漫剧助手X-2 v1.0.x"
2. 运行 v1.0.2 Setup.exe 全新安装

---

## 🐛 已修复问题(累计)

| # | 版本 | 等级 | 描述 |
|---|------|------|------|
| 1 | v1.0.1 | 🔴 P0 | 启动崩溃 `NameError: name 'log' is not defined` |
| 2 | v1.0.2 | 🟡 P2 | 主窗口变 light,应该是 X-1 dark flat |

---

## ⚠️ 已知但**未修**问题

- 🔴 P0 `ChineseSimplified.isl` 缺失(中文用户装好看到英文 Inno Setup UI)
- 🟡 P1 hermes agent "1:1 拆段" 约束
- 🟡 P1 DeepSeek thinking 模式消耗 token
- (更多见 [`V1.0.1_PLAN.md`](https://github.com/xyq900319xyq/manju-x2/blob/main/V1.0.1_PLAN.md))

---

## 📞 反馈

- **Bug 报告**:[GitHub Issues](https://github.com/xyq900319xyq/manju-x2/issues/new?template=bug_report.md)
- **功能请求**:[GitHub Issues](https://github.com/xyq900319xyq/manju-x2/issues/new?template=feature_request.md)
- **问题咨询**:[GitHub Discussions](https://github.com/xyq900319xyq/manju-x2/discussions)
