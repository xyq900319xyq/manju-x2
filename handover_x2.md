# 漫剧助手 X-2 — 项目交接文档(开发记录)

## 一、当前版本

- **v1.1.5.22 (2026-08-02) — 🐛 P0 修复:新用户填完 API 后软件闪退无法启动【当前版本】**
- 路径: `D:\漫剧助手\manju-x2`
- Python: 3.11,PyInstaller 6.21.0,Inno Setup 6.7.3
- 用户版 174 MB(+~83MB PortableGit),Setup.exe 命名 `X-2_v{ver}_Setup.exe` (纯 ASCII,GitHub 截断中文)
- GitHub release: https://github.com/xyq900319xyq/manju-x2/releases/tag/v1.1.5.22
- ⚠️ **v1.1.5.20 之前含 user API key 泄露**(sk-5e6...b223 / sk-c3D...TKoE),user 必须立即去 DeepSeek + Agnes 后台 rotate 旧 key

---

## 十四、v1.1.5.22 (2026-08-02) — 🐛 P0 修复:新用户填完 API 后软件闪退无法启动

### 🟠 BUG 现象
- **新用户(没装过 `D:\剧本分镜助手\`)首次下载 v1.1.5.20 / v1.1.5.21 安装后,首次启动 wizard 正常弹出,填完 API key 点「完成」后软件立即关闭**
- **再启动还是同样问题**:wizard 检测到 `secrets.bin` 存在直接跳过,接着 MainWindow 构造失败,软件再次闪退
- **用户报告**:「填完 API 后软件就关了,重开还是这样,根本进不了主界面」

### 🟠 根因
- `source/src/core/migration.py:open_db()` 检查 `data/projects.db` 不存在 → 调 `run_first_migration(root)`
- `run_first_migration` 第 1 行就 `raise FileNotFoundError(f"旧 db 不存在: {old_db}")`
- `DEFAULT_OLD_DB = Path(r"D:\剧本分镜助手\projects.db")` 是老 software 的数据,**新用户机器上根本没有这个文件**
- `MainWindow.__init__` 调 `open_db()` 抛 `FileNotFoundError` → main.py `return 1` 静默退出
- 之前 main.py 致命错误只 `print` 到 stderr,EXE `--windowed` 模式用户看不到任何提示

### 🟢 修复(本版)
1. **`core/migration.py:run_first_migration`** 老 db 不存在时**不再 raise**,而是调新增的 `init_empty_db(root, reason="no_old_db")` 创建一个只有 schema 的空 db,让新用户能正常启动
2. **`core/migration.py:init_empty_db` (新增)**:
   - `data/projects.db` 不存在 → `ensure_data_dir` → `init_new_schema` → `_meta` 写 `source_path="(none)"` / `app_version="1.1.5.22"` / `empty_init_reason="no_old_db"`
   - 老用户行为完全不变:有老 db 仍走原迁移流程
3. **`core/migration.py` 顶部加 `log = logging.getLogger("manju.migration")`**:原文件只 `import logging` 没创建 logger,我第一版栽在这 NameError,测试才发现
4. **`main.py:_run_first_run_wizard` 后新增 `Config.reload()`**:wizard 期间 `Config.get()` 已创建单例(那时 `secrets.bin` 还不存在,api_key 全空),wizard `save_secrets` 后单例不会自动刷新,reload 让所有持 `self._config` 引用的 task 看到新 key,保证**首次 session 就能调 LLM**(避免要重启一次才能用)
5. **`main.py` MainWindow 构造失败加 `QMessageBox.critical` 弹框**:再发生致命错误时,用户能看到具体错误类型 + 信息 + 提示看 `logs/manju.log`,不再静默退出
6. **三处版本号一致 bump** 1.1.5.21 → 1.1.5.22:
   - `source/src/main.py:264` `setApplicationVersion("1.1.5.22")`
   - `source/src/main.py:324` `UpdateChecker(current_version="1.1.5.22")`
   - `installer/漫剧助手X-2.iss:20` `#define MyAppVersion "1.1.5.22"`

### 📋 教训
- **新用户场景必须考虑**:任何代码路径 hardcode 了"老用户必然有的资源路径"(`D:\剧本分镜助手\...`),新用户(没装老 software)会直接踩坑
- **致命错误必须弹框**:EXE `--windowed` 模式 `print` 到 stderr 用户看不到,只让 developer 看 log,用户根本不知道错在哪 → 反复重试同样错误
- **wizard / 设置面板写盘后必须 reload 单例**:`Config.get()` 是单例,任何"先创建再修改"的流程(wizard 写 secrets.bin / settings 改 active),完成后必须 `Config.reload()` 让当前 session 立刻看到新值,不能等下次进程重启
- **`import logging` 后必须 `log = logging.getLogger(__name__)`**:log.warning / log.exception 用 log,没定义直接 NameError

### 🟢 涉及文件
- `source/src/core/migration.py` (`run_first_migration` 改 + 新增 `init_empty_db` + 顶部加 `log`)
- `source/src/main.py` (Config.reload + QMessageBox 致命错误弹框 + 版本号)
- `installer/漫剧助手X-2.iss` (版本号)
- `docs/更新日志.md` (加 v1.1.5.22 段)
- `release/update.json` (v1.1.5.22 url/md5/sha256)
- `.publish_v1.1.5.22.py` (raw binary POST 发布脚本)
- `release/.commit_msg_v1.1.5.22.txt` (commit msg)

### 🟢 自动化发布流程(已跑 2026-08-02 17:35)
1. `python build_x2.py` → `release/X-2_v1.1.5.22_Setup.exe` (174 MB) + .md5 + .sha256
2. **关键踩坑**:首次 commit 误把 174MB Setup.exe 加进 git(`.git add .` 没过滤) → `git push` 报 `File exceeds 100MB limit`
3. **修法**:`git reset --soft HEAD~1` 撤回 → `git reset HEAD release/X-2_v1.1.5.22_Setup.exe{,.md5,.sha256}` 把 3 个大文件从 staged 移出(保留 working dir) → `git commit -F release/.commit_msg_v1.1.5.22.txt` 重做 commit(只剩 8 个文本文件)
4. `git push origin main` → `b09598f..53b8e47 main -> main` 成功
5. `MANJU_X2_PAT=... python .publish_v1.1.5.22.py` → 自动创/更新 GitHub release + raw binary POST 上传 3 个 asset(Setup.exe / .md5 / .sha256)
6. release URL: https://github.com/xyq900319xyq/manju-x2/releases/tag/v1.1.5.22
7. update.json 指向 v1.1.5.22,已装 v1.1.5.21 的 user 启动会看到红点提示升级
8. **硬约束 (新)**:**v1.1.5.22+ Setup.exe (.md5/.sha256) 绝不能 git add 进 commit**,必须留在 working dir,只走 `python .publish_v{ver}.py` 上传(174MB > GitHub 100MB file size limit)
9. **自动化规范 (user 要求)**:以后每次修改无特殊问题,直接 commit + push + publish(完整 3 步),并更新本 handover 文件记录发布结果

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

1. `python build_x2.py` → 打 EXE + Inno Setup 编译 → `release/X-2_v{ver}_Setup.exe`
2. `git add source/ docs/ installer/ handover_x2.md .publish_v{ver}.py release/.commit_msg_v{ver}.txt release/update.json`
   - **绝对不要** `git add release/X-2_v{ver}_Setup.exe{,.md5,.sha256}`(174MB > 100MB limit)
3. `git commit -F release/.commit_msg_v{ver}.txt`
4. `git push origin main`
5. `MANJU_X2_PAT=... python .publish_v{ver}.py`(需要 user 给 PAT;raw binary POST 上传 3 个 asset)
6. `update.json` 自动被 raw.githubusercontent.com 服务,用户软件 24h 内点检查更新可拉到

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
- v1.1.5.20:分镜智能体选择(分镜 / 分镜2 切换) — X-1 加的分镜功能,user 明确要求 X-2 同步

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

## 九、v1.1.5.6~v1.1.5.10 — 一键更新第一轮修复(治标)

### v1.1.5.6 (2026-07-10) — bash 探测 8 候选路径 + 注入 env
- user 反馈 "hermes.exe 找不到 bash,报 hermes-gemini-2.5-pro 模型需要 bash"
- 修法: `core/generators.py` 实现 `_find_bash_exe()` 探测 8 个候选路径,`_ensure_hermes_bash_env()` 注入 env var,装机首次启动即生效
- 硬约束: v1.1.5.6 Git Bash 主动探测

### v1.1.5.7 (2026-07-10) — seedance-prompt profile v3.2.0 同步
- user 反馈 "我的profile seedance-prompt更新了"
- 修法: 手动从 D:\hermes\profiles\seedance-prompt 拷贝到 source/resources/hermes/profiles/seedance-prompt
- 硬约束: v1.1.5.7 profile 同步手动

### v1.1.5.8 (2026-07-10) — 3 profile 全量对齐 D:\hermes\(根)
- user 反馈 "全部与D:\hermes\ 对齐"
- 修法: `release/.sync_profiles.py` 全量同步 3 个 profile(asset-designer / seedance-prompt / storyboard)
- 硬约束: v1.1.5.8 3 profile 全量对齐 + `git add profiles/` 不能加 -f
- commit `8304559`,已发 release

### v1.1.5.9 (2026-07-10) — /FORCECLOSEAPPLICATIONS 修复
- user 反馈 "用户更新安装完软件却依旧是老版本"
- 根因: `/CLOSEAPPLICATIONS` 弹"是否关闭应用"确认框,user 看不到 → 装失败
- 修法: 改 `/FORCECLOSEAPPLICATIONS` + QTimer 500ms 改 1500ms
- 硬约束: v1.1.5.9 /FORCECLOSEAPPLICATIONS
- commit `cc60f36`,已发 release

### v1.1.5.10 (2026-07-10) — Inno Setup [Code] 去 MsgBox + os._exit 强退
- user 反馈 "用户下载安装的,依旧显示这样,更新也更新不了"
- 根因: .iss [Code] 段 `NeedRestart()` 的 MsgBox() 不受 /VERYSILENT /SUPPRESSMSGBOXES 抑制,强制弹"是否继续"框,user 看不到 → 装失败
- 修法: `NeedRestart()` 去掉 MsgBox,直接 taskkill /F /IM 静默杀旧 EXE;`main_window.py` 改 `os._exit(0)` 强退
- 硬约束: v1.1.5.10 Inno Setup [Code] MsgBox
- commit `c92be98`,已发 release

## 十、v1.1.5.11~v1.1.5.12 — 一键更新第二轮修复(治本 + 甩锅教训)

### v1.1.5.11 (2026-07-10) — QProgressDialog 去取消按钮(不彻底)
- user 反馈 "从日志可以看到,所有版本下载成功后都显示'用户取消',没有触发安装流程"
- **assistant 当时推断"user 误点取消按钮"**(甩锅了,实际上是错的)
- 修法: QProgressDialog 第二参改 `""` 去取消按钮;`_on_finished/_on_error` 改 `deleteLater()` 不用 `close()`
- commit `1479b47`,**未发 release**

### v1.1.5.12 (2026-07-11) — 彻底修根因(dlg 挡 QMessageBox)【本次】
- user 强烈反馈 **"你别甩锅了,用户没有取消,不管是任何按键都没取消,重点是软件没用启动安装你不明白吗"**
- **assistant 承认之前甩锅甩错了**:log 里的"用户取消"是 QProgressDialog 销毁时 emit canceled signal 触发 cancel() 写的,**不是 user 主动**。完全是我代码 BUG,不是 user 操作问题。
- **真正根因**: `_on_finished` 调 `dlg.deleteLater()` 只是 schedule delete,Qt 不立即销毁,dlg 仍处 main_window 子 widget 树中,在 z-order 上层挡住 `_launch_setup_silent` 弹的 QMessageBox("v 安装包已就绪,点「是」立即安装")。user 看不到 QMessageBox → 自然没点「是」→ Setup.exe 永远没启动
- **修法(必须三管齐下)**:
  1. `dlg.setParent(None)` 切断 z-order 关系
  2. `dlg.hide()` 立即隐藏
  3. `dlg.deleteLater()` 调度销毁
- **log 文字改明确**: `core/updater.py` `cancel()` log 从 `"用户取消"` 改为 `"内部 cancel signal(非用户主动,通常是 dlg 销毁触发)"`,避免 user 再误读
- **教训**: 任何"user 操作"假设之前必须先排除"代码自身 race/signal/z-order",不要轻率甩锅给 user
- 硬约束: v1.1.5.12 dlg 挡 QMessageBox(甩锅甩错教训)
- commit `5a0438c`,**等 user 给 PAT 发 release**

### v1.1.4 装 v1.1.5.x 死锁问题(未解决,需要 user 手动操作)
- v1.1.4 的 main_window.py 用 `/CLOSEAPPLICATIONS` + `QApplication.quit()`(老代码)
- v1.1.4 启动 v1.1.5.x Setup.exe,Setup.exe 弹"是否关闭应用"框,v1.1.4 user 看不到
- **教 user 手动装**: v1.1.4 → 手动关 manju-x2 → 双击 `X-2_v1.1.5.12_Setup.exe` 装(因为 v1.1.4 自己的 main_window.py bug 让一键更新失败)

## 十一、v1.1.5.13 — 装时 EXE 锁根因修复(2026-07-11)

### 用户反馈触发
> "用户都把1.1.4给删除了,然后安装新的1.1.5.12安装包,结果安好了还是1.1.4" + "同一个目录,同一个!!!"

### 真正根因(_internal/ 整目录被锁,restartreplace 不够)
- `[Files]` 段虽然用了 `ignoreversion` flag + `restartreplace` flag,但 Inno Setup 默认**静默跳过被锁文件**
- `_internal/` 下几千文件被 hermes.exe / python.exe / Defender 扫描锁住,`restartreplace` 对单个被锁文件生效但对几千文件效率极低且经常失败
- 装完后 launcher EXE 换了但 `_internal/` 还是 v1.1.4 旧文件 → 启动显示 v1.1.4

### 修复
1. `[Files]` 段 line 76 加 `restartreplace` flag
2. `[Code]` 段加 `PrepareToInstall()` 回调,装前主动 taskkill 杀 漫剧助手X-2.exe / hermes.exe / python.exe

### 硬约束
v1.1.5.13 EXE 锁装时跳过覆盖(双保险 restartreplace + PrepareToInstall)—— **不够**,还需要 v1.1.5.14 整目录删

## 十二、v1.1.5.14 — 装前整目录删 _internal/(彻底解决)(2026-07-11)【本次】

### 用户反馈触发
> "我刚刚让用户卸载重装了一次,用户反馈,卸载了之前的软件后,手动安装了新版,但安装后软件修改时间缺不是现在,而是之前的23:16的时间"

### 真正根因(EXE 修改时间是 23:16)
- user 反馈"安装后软件修改时间是 23:16(老 v1.1.4 的时间)"= Setup.exe **静默跳过覆盖**了所有文件(EXE + _internal/)
- v1.1.5.13 的 `restartreplace` + `PrepareToInstall` 还是不够,几千个 _internal 文件被锁,逐个 rename 替换效率极低且经常失败

### 修复(整目录删)
1. `[Code]` 段 `procedure CurStepChanged(CurStep: TSetupStep)`:在 Inno Setup 装文件**前**(`ssInstall` 阶段):
   - 杀光 漫剧助手X-2.exe / hermes.exe / python.exe / pythonw.exe
   - Sleep 3 秒等 Windows 文件句柄完全释放
   - `cmd /C del /F /Q "{app}\漫剧助手X-2.exe"` 强删 launcher EXE
   - 删不掉兜底:改名成 `漫剧助手X-2.exe.locked`
   - `cmd /C rmdir /S /Q "{app}\_internal"` 强删整目录
   - 删不掉兜底:改名成 `_internal.locked`
2. Inno Setup 装到**干净目录**,绝对没文件锁

### 关键踩坑修正(Inno Setup 6.7.3)
- `CurStepChanged` 是 **`procedure`,不是 `function`**(官方 Example1.iss 验证)
- 之前用 `function CurStepChanged(...): Boolean;` 报 `Invalid prototype for 'CurStepChanged'`

### 硬约束
v1.1.5.14 整目录删 _internal/(CurStepChanged procedure 不是 function)

### 硬约束
v1.1.5.15 全部 `Exec` 改 `ewWaitUntilTerminated` 同步等子进程退(默认 `ewNoWait` 异步导致旧文件没真删 Inno Setup 装新文件时跳过覆盖)

### 硬约束
v1.1.5.17 `CurStepChanged` 必须 **takeown + icacls 两步都做**(只 takeown 不 icacls ACL 没改 / 只 icacls 不 takeown owner 没换 都不行),按 6 步顺序:taskkill 杀进程 → Sleep 5000 → takeown _internal /R /A /D Y → takeown launcher + icacls launcher /grant administrators:F → icacls _internal /grant administrators:F /T /C /Q → cmd del + cmd rmdir(同步 + 二次检查 + RenameFile 改名兜底)

### 教训
**bump 版本号必须 grep 验证 iss 脚本真的改了 CurStepChanged**(不能光看 Setup.exe 编译成功)。v1.1.5.16 失败根因就是只 bump 版本号 1.1.5.15→1.1.5.16,CurStepChanged 还是 v1.1.5.15 的代码,Setup.exe 跑的是 v1.1.5.15 修复,无效。v1.1.5.17 才真的把 takeown + icacls 写进 CurStepChanged

### 硬约束
v1.1.5.18 **UI 显示版本号必须查具体显示位置的代码**,不一定走 `QApplication.applicationVersion()`。`main_window.py:557` 之前硬编码 `info.current_version = "1.1.4"`,**所有 main.py:264 / 299 / iss #define 版本号 bump 对 UI 都没影响**。修法:hardcoded → `QApplication.applicationVersion()`(跟 main.py:264 同源,单一权威源)。**Edit 工具可能静默假成功**,改完后必须 Grep / Read 重新验证,不能信 Edit 报告。bump 版本号必查 3 处:`main.py:264` + `main.py:299` + `installer/*.iss #define` + **任何 UI 显示版本号的位置**

### v1.1.5.19 新功能
- **首次启动 wizard 加自定义 LLM API**:`_AddCustomAPIDialog` 类([first_run_wizard.py:240-371](file:///D:/%E6%BC%AB%E5%89%A7%E5%8A%A9%E6%89%8B/manju-x2/source/src/ui/first_run_wizard.py#L240-L371))收 4 字段(Name/Base URL/Model/API Key)→ `Config.upsert_config()` 写 `hermes_api.json`
- **wizard 动态刷新行**:`_ConfigKeyGroup.rebuild(items)` 方法([first_run_wizard.py:227-230](file:///D:/%E6%BC%AB%E5%89%A7%E5%8A%A9%E6%89%8B/manju-x2/source/src/ui/first_run_wizard.py#L227-L230))允许加新 config 后重建 UI 行
- **触发按钮**:`_LLMPage._on_add_custom_clicked`([first_run_wizard.py:473-485](file:///D:/%E6%BC%AB%E5%89%A7%E5%8A%A9%E6%89%8B/manju-x2/source/src/ui/first_run_wizard.py#L473-L485))弹 dialog + 调 rebuild + focus 新行
- **关键复用**:`Config.upsert_config(cfg)`(`core/config.py:714`)— v0.6.24 就有,wizard v1.1.5.19 才暴露入口。settings_dialog 早就能加,只是首次启动 wizard 不能
- **不写兜底**:Name/Base URL/Model 必填,API Key 允许空(走 wizard 校验至少 1 个 LLM 有 key)

## 十三、v1.1.5.20 (2026-07-30) — 分镜智能体选择(分镜 / 分镜2 切换)【当前版本】

### 需求来源
- user 反馈:"我要给 X-1 软件里的分镜功能里加一个功能,在点击生成分镜或重新生成分镜时,要设置一个智能体选择,这个选择里现有的智能体是一个选项,另一个选项要你去复制回来,另一个智能体在 D:\Hermes\profiles\storyboard2,名字叫分镜2"

### 实现 4 步
1. **复制 profile**:`D:\Hermes\profiles\storyboard2` → `source/resources/hermes/profiles/storyboard2`
   - 拷 5 项:SOUL.md / config.yaml / auth.json / .env / skills/
   - 跳过 hermes 运行时数据(让 hermes 启动自己重新生成):cache/ logs/ sessions/ projects.db/ .curator_state/ .usage.json/ state.db/ auth.lock/ .bundled_manifest/ .archive/ .hub/ .curator_backups/ tests/ image_cache/ audio_cache/ output/ sandboxes/ curator/ hooks/ plans/ workspace/ home/ prompts/ singularity/ pairing/ terminal
2. **注册 profile**:`source/config/hermes_api.json` `profiles` dict 加 `"storyboard2": "storyboard2"`
3. **Task 参数**:`source/src/core/generators.py`
   - `StoryboardTask.__init__` 加 `profile_key: str = "storyboard"` 参数
   - 存 `self._profile_key`,`_call_hermes_storyboard` 改用 `self._config.profile_for(self._profile_key)`
   - `emit_progress` 消息带 profile 名,方便日志区分哪个智能体在跑
4. **UI 选择器**:`source/src/ui/main_window.py` 分镜 panel 加 `_sb_agent_combo` QComboBox
   - 选项 `("分镜", "storyboard")` + `("分镜2", "storyboard2")`
   - **只列 config 里注册过的 key**(避免出现"选项在但点击报未注册"的不一致状态)
   - `_on_generate_storyboard` 读 `combo.currentData()` 传给 StoryboardTask
   - 状态栏显示 `已入队: <task>（智能体: <profile_key>）`

### 关键设计点
- **profile_key 默认值 = "storyboard"**:保持向后兼容,旧 user 不感知新参数
- **UI 只列已注册 key**:跟 `hermes_api.json` 单一权威源对齐,避免 user 选了但代码报 KeyError
- **不改 prompt 输出文件命名规则**:分镜 / prompt 文件仍按 `项目名--第X集--分镜词` 命名,跟之前完全一致
- **emit_progress 带 profile 名**:日志 `（智能体: storyboard2）` 区分,排查时一眼能看出谁在跑

### 踩坑:storyboard2 同步时 .gitignore 漏过滤
- v1.1.5.20 第一次 `git add source/resources/hermes/profiles/storyboard2/` 误带入运行时文件
- 根因:`.gitignore` 只过滤 `<profile>/xxx/` 模式,但 hermes 运行时数据实际在 `<profile>/skills/xxx/`,**多一层 skills/ 就匹配不到**
- 修法:.gitignore 补全,`<profile>/skills/<name>` 模式跟 `<profile>/<name>` 模式都加(memory hard constraint 1.1.5.8 教训)
- 新增过滤项:logs/ cron/ tirith/ ollama_cloud_models_cache.json/ provider_models_cache.json/ openrouter_model_metadata.json/ *.usage.json/ *.lock/ *.curator_state/ .bundled_manifest/ .curator_backups/ .archive/ .hub/ tests/ image_cache/ audio_cache/ output/ sandboxes/ curator/ hooks/ plans/ workspace/ home/ prompts/ singularity/ terminal
- 验证:`git diff --cached --name-only | grep -E 'state\.db|auth\.lock|\.usage|\.curator|\.bundled|\.archive|\.hub'` 必须为空

### 改动文件(7 个)
| 文件 | 改动 |
|---|---|
| `source/resources/hermes/profiles/storyboard2/` | 新加,5 项 (SOUL.md/config.yaml/auth.json/.env/skills/) |
| `source/config/hermes_api.json` | profiles dict 加 `"storyboard2": "storyboard2"` 1 行 |
| `source/src/core/generators.py` | StoryboardTask 加 profile_key 参数 + 2 处 profile_for 改用 self._profile_key + emit_progress 带 profile 名 |
| `source/src/ui/main_window.py` | 分镜 panel 加 _sb_agent_combo + _on_generate_storyboard 读 combo 传 profile_key |
| `source/src/main.py` | line 264 + 299 bump 1.1.5.19 → 1.1.5.20 |
| `installer/漫剧助手X-2.iss` | `#define MyAppVersion "1.1.5.20"` |
| `.gitignore` | 补全 hermes 运行时数据过滤规则(`<profile>/skills/<name>` 模式) |

### 验证
- 8 个代码文件 `py_compile` 全过
- Setup.exe 174 MB build 成功
- md5=`31a0c11a95396b68152be80e21e10d8a`,sha256=`163e693ba18334163ba2717440d9219ff812b18a74bc2d663098b227fed329b0`
- update.json 自动写到 v1.1.5.20
- commit `d88727b` pushed to origin/main (709 files,无运行时文件污染)
- GitHub release `v1.1.5.20` 创建 + 3 个 asset (Setup.exe/.md5/.sha256) 上传成功

### 硬约束
v1.1.5.20 storyboard2 同步时 `.gitignore` 必须覆盖 `<profile>/skills/<name>` 模式(运行时数据在 skills/ 子目录,**不**是 profile 根)
v1.1.5.20 UI 选择器只列 `hermes_api.json` `profiles` dict 已注册 key(单一权威源)
v1.1.5.20 `StoryboardTask.__init__` `profile_key` 参数必须存到 `self._profile_key`,**不**允许在 `_call_hermes_storyboard` 里硬编码回 "storyboard"

### 临时方案(等不及 v1.1.5.20 的 user)
- 直接编辑 `D:\hermes\profiles\storyboard2` 改 hermes 用的 prompt 即可(所有分镜都走 storyboard profile)

## 十四、v1.1.5.21 (2026-08-02) — 🔒 安全补丁:清理 hermes profile 泄露的用户 API key

### 🟠 安全事件
- v1.1.5.20 同步 `D:\Hermes\profiles\storyboard2` 到 X-2 build 时,**整个 4 个 hermes profile**(`asset-designer` / `seedance-prompt` / `storyboard` / `storyboard2`)的 `config.yaml` 里 `custom_providers[].api_key` 字段都是 user 在 X-1 hermes 里 hardcode 的 DeepSeek / Agnes 真实 API key。
- 同步后这 4 个 profile 直接被 `build_x2.py` step 3.5 拷到 `dist/.../resources/hermes/profiles/`,**PyInstaller 打包进 EXE**,然后 `X-2_v1.1.5.20_Setup.exe` 发布到 GitHub release。
- 结果:任何下载 v1.1.5.20 的用户,**装机后能直接看到 user 的 sk-5e6...b223 / sk-c3D...TKoE 两个 API key**,装机会用 user 自己的 API 余额跑分镜 / 生图 / 视频。
- 同步脚本 `release/.sync_profiles.py` 只同步运行时数据黑名单,**没有**列 api_key 字段,导致敏感信息 leak。

### 🟠 立即修复(本版)
1. **本地代码清理**:`source/resources/hermes/profiles/{asset-designer,seedance-prompt,storyboard,storyboard2}/config.yaml` 全部 4 个文件的 `custom_providers[].api_key` 字段设成 `''`(空字符串),`auth.json` 里 credential_pool 整段清空
   - 同步脚本 `release/.sync_profiles.py` 也加 step:同步前先 strip api_key,避免下次再泄露
2. **bump 版本号** 1.1.5.20 → 1.1.5.21 三处一致:
   - `source/src/main.py` line 264 `setApplicationVersion("1.1.5.21")`
   - `source/src/main.py` line 299 `UpdateChecker(current_version="1.1.5.21")`
   - `installer/漫剧助手X-2.iss` line 20 `#define MyAppVersion "1.1.5.21"`
   - (main_window.py:562 已走 `QApplication.applicationVersion()` 单一权威源,v1.1.5.18 修的)
3. **重新 build**:`build_x2.py` 重打 EXE → v1.1.5.21 Setup.exe 装机后 4 个 profile config.yaml api_key 是空 → 跟老 software 行为一致(用户首启动在【设置】里填自己的 key)
4. **v1.1.5.20 release 加警告横幅**:`.publish_v1.1.5.21.py` 自动 PATCH 旧 release body 顶部加 `> :warning: **安全提醒...**` 横幅,不删旧 release(保留 download link 给已下载 user)
5. **update.json 指向 v1.1.5.21**:已装 v1.1.5.20 的 user 启动时会看到红点提示升级,一键更新到 v1.1.5.21

### 🟠 user 必须立即做的事(本版**不能**替 user 完成)
1. **去 DeepSeek 后台轮换(废弃)旧 API key**:
   - 登录 https://platform.deepseek.com → API Keys → 找到 sk-5e6...b223 → Delete / Revoke
   - 重新创建一个新 key
2. **去 Agnes 后台轮换旧 API key**:
   - 登录 https://apihub.agnes-ai.com → API Keys → 找到 sk-c3D...TKoE → Delete / Revoke
   - 重新创建一个新 key
3. (可选但建议) **去 GitHub 手动删 v1.1.5.20 release**:
   - https://github.com/xyq900319xyq/manju-x2/releases/tag/v1.1.5.20 → Delete
   - 原因:v1.1.5.20 source code zip / Setup.exe 仍含泄露 key
4. (可选) **去 GitHub 删 v1.1.5.20 git tag**:
   - `git push origin --delete v1.1.5.20`(需要 PAT)
   - 防止 user `git fetch` 拿到含 key 的 tag

### ⚠️ 为什么不做 force push 清理 git 历史
- `git filter-branch` / `git filter-repo` 强制重写所有 commit hash,会破坏 collaborator 本地 clone
- 即使 force push,GitHub 内部仍缓存旧 commit blob,`git fetch origin <old_hash>` 仍能访问
- **真正能堵泄露的是 user 去后台 rotate key** —— user 唯一能做的
- v1.1.5.21 + rotate key 已经足够让 user 继续安全使用,force push 风险大收益小

### 改动文件(8 个)
| 文件 | 改动 |
|---|---|
| `source/resources/hermes/profiles/asset-designer/config.yaml` | `api_key: ''` |
| `source/resources/hermes/profiles/seedance-prompt/config.yaml` | `api_key: ''` |
| `source/resources/hermes/profiles/storyboard/config.yaml` | `api_key: ''` |
| `source/resources/hermes/profiles/storyboard2/config.yaml` | `api_key: ''` |
| `source/src/main.py` | line 264 + 299 bump 1.1.5.20 → 1.1.5.21 |
| `installer/漫剧助手X-2.iss` | `#define MyAppVersion "1.1.5.21"` |
| `docs/更新日志.md` | 加 v1.1.5.21 段(安全事件 + 修复) |
| `release/.sync_profiles.py` | 同步前先 strip api_key,避免再泄露(下个版本) |
| `.publish_v1.1.5.21.py` | 发布脚本(改 v1.1.5.20 release + 发 v1.1.5.21) |
| `release/.git_filter_secrets.ps1` | PowerShell 脚本,git filter-branch 用,本次未使用留 audit trail |

### 硬约束
v1.1.5.21 **复制 hermes profile 前必须先 strip 所有 api_key 字段**(硬约束,违反会再次泄露)
v1.1.5.21 复制完**必须** `grep -r "sk-" source/resources/hermes/profiles/` 验证无 key 残留才能 commit
v1.1.5.21 每次 sync_profiles 后**必须**再 grep 一次,不能信脚本报告
v1.1.5.21 **user API key 泄露是不可撤回的硬教训**,DeepSeek/Agnes 后台 rotate 是堵泄露唯一手段

### 临时方案(等不及 v1.1.5.21 的 user)
- 装好 v1.1.5.20 后,**手动编辑** 4 个 profile 的 `config.yaml`:
  - 找到 `<install_root>\resources\hermes\profiles\<name>\config.yaml`
  - 把 `custom_providers` 下所有 `api_key: 'sk-...'` 改成 `api_key: ''`
- 改完启动 manju → 【设置 → API 配置】填自己的 DeepSeek / Agnes key
- 同样要去 DeepSeek / Agnes 后台 rotate 旧 key,否则泄露仍在

---

## 十五、skill 嵌套污染清理(2026-08-15)

**症状**: 跑 seedance-prompt profile 提示词生成时,hermes 报 skill 冲突:
```
Ambiguous skill name 'seedance-prompt-generator': 2 candidates —
  D:\漫剧助手\resources\hermes\profiles\seedance-prompt\skills\creative\seedance-prompt-generator\SKILL.md
  D:\漫剧助手\resources\hermes\profiles\seedance-prompt\skills\skills\creative\seedance-prompt-generator\SKILL.md
```
浪费 1 次 API call 才回退到分类名显式调用。

**根因**: 早期手动同步 `D:\hermes\profiles` 时重复拷贝,产生 `skills/skills/` 嵌套目录。
X-1 的嵌套里 25 个 skill 子目录,1 个 SKILL.md (computer-use) 是真版本(07-29/14081B),其他 24 个全空(SAME 或 0 SKILL.md);
X-2 的嵌套里 0 个 SKILL.md,纯空壳。嵌套目录的 metadata (`.usage.json`、`.bundled_manifest`) 全部是 7-08 老数据,根目录是 8-14 新数据。

**清理动作** (X-1 + X-2 同步):
- X-1: 删 1 个根(嵌套版新) + 删 22 个嵌套副本 + 删整个 `skills/skills/` 嵌套目录(含 .curator_backups)
- X-2: 删整个 `source/resources/hermes/profiles/seedance-prompt/skills/skills/` 嵌套目录

**X-2 commit**:
- `2b7a9d5` (2026-08-15) chore(skills): 清理 seedance-prompt profile 的 skills/skills 嵌套污染
- 6 files changed, 39 deletions(-) - 只删 `.curator_backups/` 里的 3 个时间戳 6 个备份文件(嵌套目录本身在 v1.1.5.20 commit 时就 gitignore 了,不在 repo 里)
- 已 push 到 origin/main: `cabcb57..2b7a9d5 main -> main`

**X-1 不是 git 仓库**,直接 disk 上删,已记录在 `D:\漫剧助手\handover.md` 第十六节。

**硬约束 (新)**:
- 任何同步 `D:\hermes\profiles` → `D:\漫剧助手\resources\hermes\profiles` 或 `D:\漫剧助手\manju-x2\source\resources\hermes\profiles` 的脚本**必须**用 `rsync --delete` 或 `robocopy /MIR`,**绝不**用 `/E`(会产生嵌套污染)
- 同步后**必须**跑验证:
  ```python
  import os
  for root in [r'D:\漫剧助手\resources\hermes\profiles', r'D:\漫剧助手\manju-x2\source\resources\hermes\profiles']:
      for p in os.listdir(root):
          nested = os.path.join(root, p, 'skills', 'skills')
          if os.path.exists(nested):
              print('POLLUTED:', p)
              break
      else:
          print(root, 'OK')
  ```
- hermes 启动日志出现 `Ambiguous skill name` 关键字 → **立刻**检查 `skills/skills/` 嵌套
