# 漫剧助手X-2 v1.0.0 首发 🎉

> **下载**: `漫剧助手X-2_v1.0.0_Setup.exe` (91.18 MB)
> **MD5**: `c1401573aa3f0600654ffcac82080126`
> **SHA256**: `492ddfeea45109f366c318623c46c5f25a040c0b7b2bf2a06fe4a9a32718a1b8`

## 一句话

**AI 漫剧创作助手用户版** — 输入剧情大纲,自动生成剧本 / 分镜 / 视频提示词,支持 DeepSeek / Agnes / 创维中转 等多种 API。

## 5 分钟上手

1. 下载 `漫剧助手X-2_v1.0.0_Setup.exe`
2. 双击安装(默认 `C:\漫剧助手X-2\`,**无需管理员**)
3. 启动 → 填 API key(wizard 引导,加密存到 `secrets.bin`)
4. 创建项目 → 生成分镜 → 生成视频提示词 → 完事

## 系统要求

- Windows 10 1809+ (推荐 Win11 22H2+)
- x64 架构
- 4 GB RAM (推荐 8 GB+)
- 500 MB 可用空间
- 联网(首次启动 + API 调用)

## ✨ 主要特性

### 一键安装,无依赖
- 单文件 Setup.exe(91 MB)
- 自包含 hermes.exe(无需装 Python)
- Windows DPAPI 加密 API key(绑 Windows 用户)

### 多种 AI API 支持
- **LLM**: DeepSeek / Agnes / 创维中转 / 自定义
- **图像**: Agnes / 创维中转
- **视频**: Agnes / 创维中转
- **图床**: imgbb(参考图上传)

### 完整工作流
- 剧本生成(剧情 → 多集)
- 分镜生成(每集 → 多个 Segments)
- 资产图生成(角色 / 场景 / 道具)
- 视频提示词生成(适配 Seedance / Veo / Sora)

### 自动更新
- 启动后台检查 GitHub Releases
- 有新版在设置 tab 弹红点
- 一键去下载页

## 📚 文档

- [README.md](https://github.com/&lt;your-org&gt;/manju-x2/blob/main/docs/README.md) - 快速上手
- [INSTALL.md](https://github.com/&lt;your-org&gt;/manju-x2/blob/main/docs/INSTALL.md) - 详细安装
- [FAQ.md](https://github.com/&lt;your-org&gt;/manju-x2/blob/main/docs/FAQ.md) - 40+ 常见问题
- [更新日志.md](https://github.com/&lt;your-org&gt;/manju-x2/blob/main/docs/更新日志.md) - 版本历史
- [API配置说明.md](https://github.com/&lt;your-org&gt;/manju-x2/blob/main/docs/API配置说明.md) - 各 API 详解

## 🐛 反馈

- [GitHub Issues](https://github.com/&lt;your-org&gt;/manju-x2/issues) - Bug / 建议
- 看 [FAQ](https://github.com/&lt;your-org&gt;/manju-x2/blob/main/docs/FAQ.md) 先,大概率已解答
- 必带 logs\manju-最新.log

## 📋 完整更新日志

### 新增
- 用户版独立 repo `manju-x2`
- Inno Setup 安装包(Setup.exe)
- 自包含 hermes.exe
- 启动检查 GitHub Releases `latest` API
- 设置 tab "检查更新" 红点 + 跳下载页
- Windows DPAPI 加密 API key

### 安全
- 0 dev API key 写入用户版
- 0 dev 项目数据写入用户版
- hermes auth.json 模板化,credential_pool 清空

### 改动
- 标题/版本: 漫剧助手X-1 v0.0.1 → 漫剧助手X-2 v1.0.0
- 路径常量自动定位 install_root

## 🙏 致谢

- **hermes-agent** - LLM CLI 引擎
- **PySide6** - Qt for Python
- **Inno Setup** - Windows 安装器
- **PyInstaller** - Python → EXE

---

**完整 commit**: 见 [commits](https://github.com/&lt;your-org&gt;/manju-x2/commits/main)
