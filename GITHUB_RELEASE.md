# GitHub 发版操作指南 (Phase 7 v1.0.0)

> 目标:把 `D:\漫剧助手\manju-x2\` 推到 GitHub 公开 repo,发第一个 v1.0.0 release,让用户能下载 Setup.exe + 软件能自动检查更新。

---

## 前置确认(已完成 ✅)

- [x] `D:\漫剧助手\manju-x2\release\漫剧助手X-2_v1.0.0_Setup.exe` (91.18 MB)
- [x] `D:\漫剧助手\manju-x2\release\漫剧助手X-2_v1.0.0_Setup.exe.md5`
- [x] `D:\漫剧助手\manju-x2\release\漫剧助手X-2_v1.0.0_Setup.exe.sha256`
- [x] `D:\漫剧助手\manju-x2\release\update.json` (含真实 md5/sha256)
- [x] `D:\漫剧助手\manju-x2\docs\README.md` / `INSTALL.md` / `FAQ.md` / `更新日志.md`
- [x] `D:\漫剧助手\manju-x2\.gitignore`
- [x] `D:\漫剧助手\manju-x2\build_x2.py` 含 SHA256 计算 + multi-org URL

---

## 步骤 1: 在 GitHub 建 repo

1. 登录 GitHub
2. 右上角 `+` → `New repository`
3. 填写:
   - **Repository name**: `manju-x2`
   - **Description**: `漫剧助手X-2 用户版 - AI 剧本/分镜/视频生成助手(独立 EXE 包)`
   - **Public** (重要!Private 用户无法下载)
   - **不要**勾 "Initialize this repository with a README"(我们要自己推)
4. 点 `Create repository`
5. 记下 URL:`https://github.com/xyq900319xyq/manju-x2.git`(把 `xyq900319xyq` 替换成你的 GitHub 用户名/org 名)

> **`xyq900319xyq` 占位符**: 下面所有命令和文件里的 `xyq900319xyq` 都要替换成你的实际 GitHub 用户名/org 名(小写)。

---

## 步骤 2: 替换 `xyq900319xyq` 占位符

### 2.1 `build_x2.py`(line 177 / 181)
当前:
```python
'url': f'https://github.com/xyq900319xyq/manju-x2/releases/download/{ver}/{latest.name}',
'changelog_url': 'https://github.com/xyq900319xyq/manju-x2/blob/main/docs/更新日志.md',
```
改成你的实际 GitHub 用户名(假设是 `xiaoyu`):
```python
'url': f'https://github.com/xiaoyu/manju-x2/releases/download/{ver}/{latest.name}',
'changelog_url': 'https://github.com/xiaoyu/manju-x2/blob/main/docs/更新日志.md',
```

### 2.2 `installer\漫剧助手X-2.iss`(line 22)
当前:
```ini
#define MyAppURL "https://github.com/xyq900319xyq/manju-x2"
```
改成:
```ini
#define MyAppURL "https://github.com/xiaoyu/manju-x2"
```

### 2.3 `docs\README.md` / `INSTALL.md` / `FAQ.md`
全局搜 `&lt;your-org&gt;` 替换成 `xiaoyu`(在 VSCode 里 `Ctrl+Shift+H` 即可)。

### 2.4 `release\update.json`
**重跑 build_x2.py** 自动用真 URL 重写:
```powershell
cd D:\漫剧助手\manju-x2
python build_x2.py
# (会清 dist/build 重打,约 2-3 分钟,Setup.exe md5/sha256 也会重算)
```

### 2.5 `source\src\core\updater.py`
当前:
```python
DEFAULT_GITHUB_REPO = os.environ.get("MANJU_X2_GITHUB_REPO", "xyq900319xyq/manju-x2")
```
改:
```python
DEFAULT_GITHUB_REPO = os.environ.get("MANJU_X2_GITHUB_REPO", "xiaoyu/manju-x2")
```

---

## 步骤 3: Git 初始化 + 首次 commit

```powershell
cd D:\漫剧助手\manju-x2

# 1. init
git init
git branch -M main

# 2. 配置 user(已经设了 global,这步可省)
# git config user.name "Your Name"
# git config user.email "your@email.com"

# 3. add(注意:.gitignore 已排除 build/dist/outputs/secrets.bin 等)
git add .

# 4. 检查要提交的文件(确认没漏没多)
git status

# 5. 第一次 commit
git commit -m "init: 漫剧助手X-2 v1.0.0 首发

- 完整用户版代码 + hermes.exe + docs
- Inno Setup 安装包 91.18 MB
- DPAPI 加密 API key
- 启动自动检查 GitHub Releases 更新
- 见 docs/更新日志.md
"

# 6. 加 remote
git remote add origin https://github.com/xiaoyu/manju-x2.git

# 7. 验证 remote
git remote -v
```

---

## 步骤 4: 推到 GitHub

```powershell
cd D:\漫剧助手\manju-x2
git push -u origin main
```

**可能弹**:
- GitHub 登录:浏览器弹窗 → 登录 + 授权
- Personal Access Token:如果用 SSH/PAT 认证,GitHub 现在要求 fine-grained PAT(2025+)

> **如果 push 失败**:多半是大文件 `hermes_dist\_internal\` 超过 GitHub 100 MB 限制。检查 `.gitignore` 是否漏了 `source/hermes_dist/`(已包含),或者用 Git LFS。

---

## 步骤 5: 创建 v1.0.0 Release

### 方式 A: 浏览器(推荐,直观)

1. 访问 https://github.com/xiaoyu/manju-x2/releases
2. 点 `Create a new release` (或 `Draft a new release`)
3. 填写:
   - **Choose a tag**: `v1.0.0` (输入框里直接打,会自动创建)
   - **Release title**: `漫剧助手X-2 v1.0.0 首发`
   - **Description**: 复制 `docs\更新日志.md` 里 v1.0.0 那段
   - **Attach binaries**: 拖入下面 3 个文件
     - `D:\漫剧助手\manju-x2\release\漫剧助手X-2_v1.0.0_Setup.exe` (91.18 MB)
     - `D:\漫剧助手\manju-x2\release\漫剧助手X-2_v1.0.0_Setup.exe.md5`
     - `D:\漫剧助手\manju-x2\release\漫剧助手X-2_v1.0.0_Setup.exe.sha256`
   - **Set as latest release**: ✅
   - **Set as pre-release**: ❌(v1.0.0 是稳定版)
4. 点 `Publish release`

### 方式 B: `gh` CLI(快,但需装 gh)

```powershell
# 装 gh(如果没有)
winget install --id GitHub.cli

# 登录
gh auth login

# 创建 release
cd D:\漫剧助手\manju-x2
gh release create v1.0.0 `
  --title "漫剧助手X-2 v1.0.0 首发" `
  --notes-file docs/更新日志.md `
  release\漫剧助手X-2_v1.0.0_Setup.exe `
  release\漫剧助手X-2_v1.0.0_Setup.exe.md5 `
  release\漫剧助手X-2_v1.0.0_Setup.exe.sha256
```

### 方式 C: GitHub REST API(脚本化)

```bash
# 需要 GitHub Personal Access Token
curl -X POST \
  -H "Authorization: token <YOUR_PAT>" \
  -H "Content-Type: application/json" \
  https://api.github.com/repos/xiaoyu/manju-x2/releases \
  -d '{
    "tag_name": "v1.0.0",
    "name": "漫剧助手X-2 v1.0.0 首发",
    "body": "<insert 更新日志 content>",
    "draft": false,
    "prerelease": false
  }'

# 然后用 upload-release-asset API 上传 3 个文件(略)
```

---

## 步骤 6: 把 `update.json` 也放上去(自更新用)

软件启动时 `updater.py` 拉 `https://github.com/xiaoyu/manju-x2/releases/latest`,从 `assets` 找 `update.json` 文件(或者从 `browser_download_url` 解析)。

**两种方式**:

### 方式 A: 作为 release asset(本指南采用)
- 创建 release 时,把 `release\update.json` 也拖到 Attach binaries
- 缺点:用户要先解析 release JSON 找 update.json,而不是直接拉 URL

### 方式 B: 放 raw.githubusercontent.com(更优雅)
1. 把 `release\update.json` 提交到 git(目前 `.gitignore` 没排除它,OK)
2. 推到 main 分支
3. URL: `https://raw.githubusercontent.com/xiaoyu/manju-x2/main/release/update.json`
4. 改 `updater.py` 的 DEFAULT_UPDATE_URL(待 v1.0.1 改进)

> **当前 v1.0.0** 用方式 A,`updater.py` 走 GitHub API 解析 `assets`(更稳)。

---

## 步骤 7: 验证

### 7.1 在另一台机器测自动更新

在干净 Win10/11 VM(没装过这软件):
1. 装 v1.0.0 (从 GitHub release 下载)
2. 启动 → 设置 → 看到 "🔔 检查更新" 可点
3. 点 "检查更新" → 弹框 "已是最新版本 v1.0.0"(因为 v1.0.0 是 latest)
4. (可选) 推一个 v1.0.1 → 启动 v1.0.0 → 看到红点 + 弹窗 "发现 v1.0.1"

### 7.2 验证 update.json

```powershell
# 在浏览器打开 release 页面
# 看 update.json 的内容(下载后用文本编辑器看)
# 验证 URL / md5 / sha256 / size 都对
```

### 7.3 验证 SHA256

```powershell
Get-FileHash ".\漫剧助手X-2_v1.0.0_Setup.exe" -Algorithm SHA256
# 对比 GitHub release 页面的 sha256
```

---

## 步骤 8: 通知第一批用户

- 朋友圈 / 微博 / X(Twitter) 发发版消息
- 链接:`https://github.com/xiaoyu/manju-x2/releases/latest`
- 建议 10-100 人灰度,收集反馈

---

## 故障排查

### Q: push 失败 `GH001: Large files detected`
- `source/hermes_dist\_internal\` 某些文件 > 100 MB(单个文件)
- 解决:加进 `.gitignore`,或用 [Git LFS](https://git-lfs.github.com)
- 之前 `.gitignore` 已写 `source/hermes_dist/`,但只忽略 _internal 外的;需要确认

### Q: 推送 5 MB 限制的 PAT
- GitHub fine-grained PAT 默认 5 MB 推送限制
- 用 classic PAT 或 SSH key 推

### Q: Release 上传慢
- 91 MB 国内到 GitHub 服务器 1-5 分钟
- 用 gh CLI 一般比浏览器快

### Q: 软件查不到 release
- 24h 缓存:删 `config\.update_check_cache.json` 强制刷
- API 速率:60 次/小时/IP,公测够用
- 网络:GitHub 偶尔被墙,可能要用代理

---

## 后续版本流程

v1.0.1 / v1.0.2 / v1.1.0 等:
1. 改代码 → 改 `build_x2.py` 里的 `MyAppVersion`
2. 跑 `python build_x2.py` 重打 Setup.exe
3. 改 `docs\更新日志.md` 加新版本
4. `git add .` + `git commit` + `git push`
5. GitHub 上 `Create release` → tag `v1.0.1` + 拖新 Setup.exe
6. 现有用户启动 → 自动检查 → 红点 + 跳下载

---

## 关键链接

- Repo: https://github.com/xiaoyu/manju-x2
- Release: https://github.com/xiaoyu/manju-x2/releases
- Issues: https://github.com/xiaoyu/manju-x2/issues
- update.json URL: https://github.com/xiaoyu/manju-x2/releases/latest(API 路径)
