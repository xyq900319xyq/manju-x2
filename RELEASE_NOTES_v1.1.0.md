# 漫剧助手X-2 v1.1.0 — 一键更新

## 安装包

- 文件名: `漫剧助手X-2_v1.1.0_Setup.exe`
- 大小: ~91 MB
- 压缩: LZMA2/ultra64
- 架构: x64
- 最低系统: Windows 10 1809+

## 重点更新:一键自动更新

**v1.0.0 之前**:「检查更新」只能弹 GitHub release 页,用户要手动下载 → 手动关软件 → 手动装新版本。

**v1.1.0 之后**: 检测到新版后,菜单栏「帮助」里会显示 **🔴 新版 vX.X.X** 红点。点红点(或主动「检查更新」)会弹:

```
发现新版本
当前版本: v1.0.3
最新版本: v1.1.0
安装包大小: 91.0 MB

是否立即下载并自动安装？
```

点「是」→ 后台流式下载 Setup.exe(带进度条 + 取消按钮) → 弹"已就绪,开始安装" → 启动 Setup.exe 静默装 → 软件自动关闭 → 装完自动重启新版本。

整个过程不需要用户离开软件,不需要手动下载,不需要手动关软件。

## 技术细节

- 后台下载: `urllib` 流式,64KB chunk,支持取消 + 进度回调
- 安装器参数: `Setup.exe /VERYSILENT /SUPPRESSMSGBOXES /SP- /CLOSEAPPLICATIONS /NORESTART`
- Inno Setup 新增 `CloseApplicationsFilter=漫剧助手X-2.exe;manju-x2.exe` + `SetupMutex=漫剧助手X-2_InstanceMutex`,自动识别 + 等待 + 关闭运行中的旧版本
- `RestartApplications=yes` 装完自动拉起新版本

## 改动

- `core/updater.py`: `UpdateInfo` 加 `asset_url` + `asset_size` 字段;新增 `UpdateDownloader` + `_DownloadWorker` 流式下载类
- `ui/main_window.py`: 加 `_on_badge_clicked` / `_show_update_dialog` / `_launch_setup_silent`;改 `_on_check_update_manual` 走一键更新流程
- `installer/漫剧助手X-2.iss`: 加 `CloseApplicationsFilter` / `CloseApplications` / `RestartApplications` / `SetupMutex` flag
- 版本号 1.0.3 → 1.1.0(`main.py` 3 处 + .iss 1 处)

## 安全

- 下载源: GitHub release `browser_download_url`(直链,HTTPS)
- 无新依赖(继续用 stdlib `urllib`)
- Setup.exe 存到 `%TEMP%`,装完不残留(用户可手动清)
- 取消下载会清半成品文件

## 升级

覆盖安装。数据目录(`config/` / `data/` / `outputs/` / `logs/`)和 hermes 配置不丢。
