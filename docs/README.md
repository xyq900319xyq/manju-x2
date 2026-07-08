# 漫剧助手X-2 用户版

## 快速上手

1. **下载安装包**: 从 [Releases](https://github.com/&lt;your-org&gt;/manju-x2/releases) 下载最新 `漫剧助手X-2_vX.Y.Z_Setup.exe`
2. **运行安装**: 双击 Setup.exe,选安装目录(默认 `C:\漫剧助手X-2`,无需管理员权限)
3. **首次启动**: 启动后会弹 **API key 配置向导**,填入你自己的:
   - DeepSeek API key (https://platform.deepseek.com)
   - 或 Agnes AI / 创维中转 等
4. **开始用**: 选 API → 创建项目 → 生成剧本/分镜/视频提示词

## 目录结构

```
<install_root>\
├── 漫剧助手X-2.exe       ← 入口
├── _internal\            ← 程序文件
├── config\
│   └── hermes_api.json   ← 你的 API key(Windows DPAPI 加密)
├── data\                 ← 数据库
├── outputs\              ← 项目生成结果
└── logs\                 ← 运行日志
```

## 卸载

控制面板 → 程序和功能 → 漫剧助手X-2 → 卸载

**注意**: 卸载只删程序文件,`config\` / `data\` / `outputs\` / `logs\` 保留。重装后你的项目数据还在。要彻底清,手动删安装根目录。

## 更新

- **启动时自动检查** GitHub Releases,有新版在设置 tab 弹红点
- 点"去下载" → 浏览器打开 GitHub Release 页
- 下载新 Setup.exe → 关旧版 → 装新版(自动保留 `config\` / `data\` / `outputs\`)

## 故障

- **"找不到 hermes.exe"**: 安装目录下应该有 `_internal\hermes\hermes.exe`,如缺失请重装
- **"API key 无效"**: 设置 → 重新填 key
- **"生成卡住"**: 看 `logs\` 里最新日志,或重启软件

## 反馈

[GitHub Issues](https://github.com/&lt;your-org&gt;/manju-x2/issues)
