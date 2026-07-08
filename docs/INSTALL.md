# 漫剧助手X-2 安装指南

## 系统要求

| 项目 | 最低 | 推荐 |
|---|---|---|
| 操作系统 | Windows 10 (1809+) | Windows 11 22H2+ |
| 架构 | x64 | x64 |
| 内存 | 4 GB RAM | 8 GB+ |
| 硬盘 | 500 MB 可用空间(不含项目数据) | 2 GB+ |
| 网络 | 首次启动需要联网(下载/调用 API) | — |
| Python | **不需要** | — |
| .NET | **不需要** | — |

> 32 位 Windows **不支持**(PyInstaller 只打了 x64)。

---

## 安装步骤

### 1. 下载安装包

从 [Releases](https://github.com/&lt;your-org&gt;/manju-x2/releases) 页面下载最新版本的 `漫剧助手X-2_vX.Y.Z_Setup.exe`(约 91 MB)。

**校验文件完整性**(可选但推荐):
```powershell
# PowerShell 验证 SHA256
Get-FileHash .\漫剧助手X-2_v1.0.0_Setup.exe -Algorithm SHA256
# 对比 GitHub Release 页或 update.json 的 sha256 字段
```

v1.0.0 SHA256:
```
17A3D53E3EB5BBFF9869542E92386FE7C9B6849D52DC4E298336ACD8E4581796
```

### 2. 运行安装程序

- 双击 `漫剧助手X-2_v1.0.0_Setup.exe`
- 看到 UAC 提示?**不会** — 安装器使用 `PrivilegesRequired=lowest`,**不需要管理员权限**
- 选安装目录(默认 `C:\漫剧助手X-2`,建议保持默认)
- 选附加任务(桌面图标、开始菜单快捷方式)
- 点 "安装" → 等待 30-60 秒
- 完成 → 勾选 "启动漫剧助手X-2" → 点 "完成"

### 3. 首次启动向导

启动后会弹 **API key 配置向导**(QWizard 6 步):

1. **欢迎页** - 简短介绍 + DPAPI 加密说明
2. **LLM API key** - 填你的 DeepSeek / Agnes / 创维中转 等大模型 key
3. **图像 API key** - 如果用 AI 生图则填,否则跳过
4. **视频 API key** - 如果用 AI 生视频则填,否则跳过
5. **图床 imgbb key** - 如果需要上传参考图则填,否则跳过
6. **完成** - 显示已填项摘要

填完点 "完成" → 密钥用 **Windows DPAPI**(绑定 Windows 用户账号)加密存到 `config\secrets.bin`。

**没有 API key?** 可以关闭向导,稍后到 设置 → 模型设置 里填。

### 4. 创建第一个项目

- 点 "新建项目" → 输入项目名 → 选 API
- 选 "剧本" 标签 → 填剧情大纲 → 点 "生成分镜"
- 等 30-60 秒 → 分镜出现 → 改/删/加 → 点 "生成视频提示词"
- 导出生图 / 视频提示词到本地文件

---

## 目录结构(安装后)

```
C:\漫剧助手X-2\
├── 漫剧助手X-2.exe          ← 主程序入口
├── _internal\                ← PyInstaller 运行时(只读)
│   ├── 漫剧助手X-2.exe      ← 实际入口(同目录同名)
│   ├── resources\hermes\... ← hermes 资源
│   └── ...
├── hermes\                   ← hermes.exe 独立目录(114 MB)
│   ├── hermes.exe
│   └── _internal\
├── config\
│   ├── hermes_api.json       ← 非敏感配置(base_url / model)
│   └── secrets.bin           ← Windows DPAPI 加密的 API key
├── data\                     ← SQLite 数据库
├── outputs\                  ← 你生成的项目数据(分镜/提示词/资产图)
└── logs\                     ← 运行日志(出问题看这里)
```

**注意**:
- `config\secrets.bin` 删了就丢失 API key(需重填)
- `data\` 删了就丢失所有项目数据(数据库)
- 卸载软件会保留 `config\` / `data\` / `outputs\` / `logs\`,重装后项目数据还在

---

## 升级

### 方式 1: 软件内检查更新(推荐)

- 启动软件时自动后台检查 GitHub Releases(24h 缓存)
- 有新版 → 设置 tab 出现红点 + 状态栏提示
- 点 "🔔 检查更新" → 弹出版本对比 → 点 "去下载" → 浏览器打开 release 页
- 下载新 Setup.exe → 关旧版 → 双击装(覆盖安装,数据保留)

### 方式 2: 手动下载

- 访问 https://github.com/&lt;your-org&gt;/manju-x2/releases
- 找最新版本(顶部)→ 下载 `漫剧助手X-2_vX.Y.Z_Setup.exe`
- 双击 → 选 **相同**安装目录 → 自动覆盖

**注意**:
- 不要先卸载再装(卸载会保留数据但增加风险)
- 覆盖安装会自动保留 `config\` / `data\` / `outputs\`

---

## 卸载

### 标准卸载(控制面板)

1. 开始菜单 → 设置 → 应用
2. 找 "漫剧助手X-2"
3. 点 "卸载" → 确认
4. 卸载完成后:
   - `C:\漫剧助手X-2\` 程序目录 **会删除**
   - `config\` / `data\` / `outputs\` / `logs\` **会保留**(Inno UninstallDelete 只清 logs/cache)

### 彻底清除

```powershell
# 删除残留数据(谨慎!)
Remove-Item -Recurse -Force "C:\漫剧助手X-2"
```

---

## 防火墙/杀毒软件

部分杀软可能误报(UPX 压缩 + PyInstaller bootloader 触发启发式扫描):
- 360 安全卫士: 添加信任目录 `C:\漫剧助手X-2\`
- Windows Defender: 弹窗时选 "更多信息" → "仍要运行"
- 火绒: 信任区 → 添加 `C:\漫剧助手X-2\`

如果还是被拦截,临时关闭实时防护后装。

---

## 故障排查

| 症状 | 解决 |
|---|---|
| 启动报"找不到 hermes.exe" | 检查 `C:\漫剧助手X-2\hermes\hermes.exe` 是否存在,缺失重装 |
| 启动闪退 | 看 `logs\manju-最新.log` 末尾错误信息 |
| API key 无效 | 设置 → 重新填 key(DPAPI 绑定 Windows 用户,换账号失效) |
| 生成卡住 / 不出结果 | 重启软件 / 看 logs / 检查网络 |
| 装到 `D:\` 失败 | 默认装到 `C:\` 最稳(免 UAC);要装到 D:\ 用管理员模式 |

更多问题见 [FAQ.md](FAQ.md)。
