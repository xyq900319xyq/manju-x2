# 漫剧助手 X-2 — 项目交接文档(开发记录)

## 一、当前版本

- v1.1.5.5 (2026-07-10) — 自带 Git Bash (PortableGit) 装机
- 路径: `D:\漫剧助手\manju-x2`
- Python: 3.11,PyInstaller 6.21.0,Inno Setup 6.7.3
- 用户版 173 MB(+~83MB PortableGit),Setup.exe 命名 `X-2_v{ver}_Setup.exe` (纯 ASCII,GitHub 截断中文)

## 二、v1.1.5 — 16 个 BUG 全面修复(2026-07-10)

### 用户反馈触发
> "仔细查一下还有没有其他BUG,这是给用户的,bug太多了用户反馈体验特别差"

### 系统化排查结果

**方法**:用 3 个 subagent 并行 grep 全 src/ 找可疑 BUG,核对每个发现 + 给出修法。然后 user 选"全修 16 个"。

### 21 个 BUG 清单(已修 17 个,低严重 4 个跳过)

**🔴 致命 (1)**
- A: `_on_import_script_file` 调了不存在的 `_show_storyboard_tab` → AttributeError,导入剧本功能整个坏的

**🟠 高 (7)**
- B1: `_on_new_project` 新项目不自动选中(toolbar 灰的)
- B2: `_on_new_episode` 新剧集不自动跳
- B3: `_on_delete_project` 删完 `_current_*` 不清
- B4: `_on_delete_episode` 删完 `_current_episode` 不清 + 括号 `(N)` 不更新
- B5: `StoryboardTask` 漏 override `cancel()`(hermes 跑满 2h)
- B6: `updater.py` 3 处漏 `ssl._create_unverified_context()`(创维环境)
- B7: `asset_panel._on_prompt_changed` 写库不更新内存(prompt 回滚)

**🟡 中 (10)**
- C1: `_on_rename_project` `_project_overview_cache` 命中
- C2: `_on_edit_episode` 各 tab cache 不失效
- C3: `_maybe_prompt_model_switch` 只覆盖 3 类 task
- C4: `_run_one_asset_image` 空 prompt 直接发 API
- C5: `_on_fetch_models` 非 DreaminaModelsError 异常被吞
- C6: `_on_test_dreamina` 裸调 subprocess
- C7: `_on_dreamina_login` 静默吞 + 启动异常裸抛
- C8: `project_tree` `take*`/`remove*` 触发 `itemSelectionChanged` 误触
- C9: settings 关闭后 UI 缓存可能 stale(实际不是 BUG,subagent 误报,asset_panel 都从 Config.get() 拿最新)
- C10: 25 处 `except: pass` 静默吞(8 处关键加 log)

**🟢 低 (4) — 跳过本版**
- `urllib.parse.quote` 没显式 import
- 散落 debug warning / 重复 import
- 资产浏览器 50+ 图首次打开卡
- 音频路径静默吞

### 修法核心模式

1. **UI 缓存统一失效**:`_invalidate_all_ui_caches()` + setCurrentItem 触发 selection
2. **CRUD 状态清理**:删/改完必须 `self._current_* = None/fresh` + invalidate cache + 主动重画
3. **异常兜底**:所有 `except DomainError` 必须再加 `except Exception` 兜底弹错
4. **blockSignals**:`take*` / `remove*` 之前必须 blockSignals 防误触 selection
5. **task cancel 透传**:长跑 task 必须 override `cancel()` + `mt.cancel()` 透传给内部 ManjuTask
6. **SSL unverified**:所有 `urlopen` 加 `ssl._create_unverified_context()`(创维环境)
7. **写库后更新内存**:dataclass 字段 in-place 更新 + 通知 listw item UserRole

### 改动文件(8 个)

| 文件 | 改动 |
|---|---|
| `ui/main_window.py` | 7 处(致命 A + B1-B4 + C1-C3) |
| `ui/project_tree.py` | 3 处(B1+B2 返回值, C8 block_signals) |
| `ui/asset_panel.py` | 1 处(B7) + 1 处(C10 log) |
| `ui/settings_dialog.py` | 4 处(C5-C7 + C10) |
| `core/updater.py` | 1 处(B6) |
| `core/generators.py` | 2 处(B5 + C4) |
| `core/task_queue.py` | 4 处(C10) |
| `core/image_api.py` | 3 处(C10) |

### 验证

- 8 个文件 `py_compile` 全过
- Setup.exe 86.97 MB build 成功
- md5=ccd3b0ad8af2771db3e6eedb679fe0dd
- update.json 已写 v1.1.5 元数据
- commit `db0b5c3` pushed to origin/main

## 三、关键技术决策

### 1. UI 缓存分两类
- **id-only cache**(必须 invalidate):`_episode_detail_cache` / `_asset_tab_cache`
- **content-key cache**(字段变自动失效):`_prompt_tab_cache` / `_video_tab_cache` / `_project_overview_cache`

### 2. v0.7.8.x 老约束保留
- 生图 API 多 config + active id 切换
- 写 image_path/image_status 不动 image_prompt
- Config.reload 原地更新(`_data`/`_path`/`_project_root`),不替换 instance
- inject_api_to_profile `m["default"] = active["model"]`(无兜底)
- raw.githubusercontent.com 双源回退(无 rate limit)

### 3. v1.1.3+ 新约束
- url 编码 3 层防御(quote + build_x2 写纯 ASCII + Qt 弹框 encode)
- stdout/stderr reconfigure utf-8
- Inno Setup OutputBaseFilename 纯 ASCII
- update.json url 加 v 前缀

### 4. 硬约束集中处
`c:\Users\Administrator\.trae-cn\memory\projects\-d-----\project_memory.md` — 12 条 v1.1.5 硬约束已写入

## 四、发布流程(已自动化部分)

1. `python build_x2.py` → 打 EXE + Inno Setup 编译
2. `git add ... && git commit -F release/.commit_msg_v{ver}.txt`
3. `git push origin main`
4. `python .publish_v{ver}.py`(需要 `MANJU_X2_PAT` 环境变量)
5. `update.json` 自动被 raw.githubusercontent.com 服务,用户软件 24h 内点检查更新可拉到

## 五、用户偏好(从 user_profile 提炼)

- 通信:中文
- 偏好严格复刻老 software,不要随意加 feature
- 同类问题一次都修好
- 6 + 4 不在范围,等下版
- 自动关进程 + 自动打包
- 关闭软件后打包
- 修复后立刻出 Setup.exe 让用户能升级
- GitHub release 创建完直接给 user URL

## 六、用户报告过的具体 BUG(累积)

- v1.1.2:分镜完成 UI 不显示
- v1.1.3:更新报 404
- v1.1.4:资产提取 UI 不显示
- v1.1.5:导入剧本崩溃 + 项目树 CRUD 状态问题 + StoryboardTask cancel 失效 + 创维拉不到更新 + prompt 回滚 + 16 个 BUG 全面修
- v1.1.5.4:清空分镜 / 清空 prompt / 提取到视频 页面不刷新
- v1.1.5.5:生提示词报 "无法读取文件:Git Bash 未安装" → 自带 PortableGit 装机

## 七、v1.1.5.1~v1.1.5.4 — 4 个连续小修复

### v1.1.5.1 — hermes 三个智能体打包丢失
- user 反馈 "软件未安装 skill,三个智能体文件夹都是空的"
- 根因:`build_x2.py` step 3 只拷 hermes.exe,**漏**拷 profiles。EXE 模式 `Config.hermes_home` 探测第 2 选 `<project_root>/resources/hermes/`,profiles 目录不存在 → hermes 报"skill 未在系统中安装"
- 修法:加 step 3.5 `shutil.copytree(<source>/resources/hermes/profiles, <dist>/resources/hermes/profiles)`

### v1.1.5.2 — 批量资产生图 SQLite 跨线程
- 报 `SQLite objects created in a thread can only be used in that same thread`
- 根因:`BatchAssetImageTask.run()` worker thread 调 `self._db.list_assets`,db connection 在 main thread 创的
- 修法:`core/migration.py` `open_db` 改 `sqlite3.connect(p, check_same_thread=False)`

### v1.1.5.3 — 升级后用户 API 配置丢失
- user 反馈"更新后设置过的 api 就没了"
- 根因:`.iss` 拷 `dist\...\*` 时没 Excludes → build_x2.py step 4 拷的 `config/hermes_api.json` 模板覆盖 user 填的 API key
- 修法:`Source` 加 `Excludes: "hermes_api.json"`,line 单独 `onlyifdoesntexist` 装模板(只首次安装生效)

### v1.1.5.4 — 清空分镜 / 清空 prompt / 提取到视频 页面不刷新
- user 反馈"在分镜页点击清空分镜,软件页面并没有清空"
- 根因:`_show_episode_detail` (line 802) 用 id-only cache,同 ep_id 复用旧 widget 不重建。3 个同类 handler:`_on_clear_storyboard` (line 3110) / `_on_clear_prompt` (line 2915) / `_on_extract_prompt_to_video` (line 3060) 写 db 后调 `_show_*` 没失效 cache
- 修法:3 处都在调 `_show_*` 之前先 `self._invalidate_all_ui_caches()`

## 八、v1.1.5.5 — 自带 Git Bash (PortableGit) 装机

### 用户反馈触发
> "我不同意你这样的改法,截断是不明智的选择,我建议你把 Git Bash 装入安装包,更新以后直接给用户的电脑装上,这样是最好的选择"

### 根因
hermes terminal 工具要 `bash -c 'cat <file>'` 读长分镜/剧本 tmp file(>20000 字符要写 tmp file 让 hermes cat 读)。user 电脑没装 Git Bash + env var HERMES_GIT_BASH_PATH 没设 → hermes 默认 bash 查找失败 → 报 "无法读取文件:Git Bash 未安装"。

### 修法(user 明确要求:装 Git Bash,反对截断)
1. `build_x2.py` step 0.5 加 `download_mingit()` 函数(实际下 PortableGit-2.54.0-64-bit.7z.exe ~80MB)
   - 用 `subprocess.run([sfx, f'-o{target}', '-y'])` 7z SFX 自解压,**不**需外部 7z 工具
   - 跟 hermes install.ps1:794-796 一样的方式
   - 缓存机制:installer/PortableGit/bin/bash.exe 存在跳过下载
2. `installer/漫剧助手X-2.iss` 加:
   - `Source: "...\installer\PortableGit\*"; DestDir: "{app}\PortableGit"` 装 PortableGit 到 `<install_root>\PortableGit\`
   - `[Registry] Root: HKCU; Subkey: "Environment"; ValueType: string; ValueName: "HERMES_GIT_BASH_PATH"; ValueData: "{app}\PortableGit\bin\bash.exe"; Flags: uninsdeletevalue` 设 env var
3. `.gitignore` 加 `installer/PortableGit/` + `installer/MinGit-*.zip`(本地 build 缓存,不入 git)
4. **撤回 prompts.py 2 处 + generators.py 1 处截断方案** (user 反对截断会 quality 降,保留长文本写 tmp file + 让 hermes cat 读)

### 踩过的坑
- **build 第一版错下 MinGit**:MinGit 是 minimal-automation 包,**不**含 bash.exe!解出来只有 git + 库。改用 PortableGit(hermes 官方用,自带 bash + git + coreutils)
- **bash 路径**:PortableGit 实际是 `bin\bash.exe`,**不**是 `cmd\bash.exe`(那是完整 Git 安装包布局)也不是 `mingw64\bin\bash.exe`(那是 MinGit mingw 工具路径)
- **Inno Setup [Registry] 段不支持 `errorignore` flag**:ISCC 报"Parameter 'Flags' includes an unknown flag"。HKCU 是 user-scope,普通 user 都有写权限,无需 errorignore

### 版本号 3 处一致
`source/src/main.py` (setApplicationVersion + UpdateChecker.current_version) + `installer/漫剧助手X-2.iss` (`#define MyAppVersion`)

### Installer 大小
90.24 MB → 173 MB (+~83MB PortableGit, LZMA2 压缩后)

### Git commit
`d353887 v1.1.5.5 — 自带 Git Bash (PortableGit) 装机,跟老 software 行为一致`

### 发布脚本
`.publish_v1.1.5.5.py`(等 user 给 `MANJU_X2_PAT` 环境变量)

### 硬约束
`project_memory.md` 加 v1.1.5.5 自带 Git Bash 装机 + version bump 三处一致 2 条硬约束
