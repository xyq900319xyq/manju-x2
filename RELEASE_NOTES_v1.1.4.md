# 漫剧助手X-2 v1.1.4 — 资产提取/资产生图 UI 不刷新统一修复

## 重点修复

### 资产提取成功了但软件没显示
**症状**:
- 跑资产抽取,日志说 "✓ 完成: 资产抽取 - 111" + "总计: 10个全局唯一资产" + "物品 6 个/场景 2 个/人物 2 个"
- 切到资产 tab,内容**一直是**"暂无人物资产 / 暂无场景资产 / 暂无物品资产",跟分镜生成完的 UI 不刷新是同一类问题(只是分镜在 v1.1.2 修了,资产没修)

### 根因(3 个 bug 叠加)
1. **`_persist_task_result` 入口没统一 invalidate UI cache** — v1.1.2 我只对 StoryboardTask / VideoPromptTask 加了 `_episode_detail_cache = None`,但 `_asset_tab_cache` 仍是 id-only 命中,**资产提取完成 → db 写好 → cache hit 走 early return → UI 永远显示老"暂无"**
2. **`parse_asset_markdown` 段标题正则只认 `## 人物资产` 老格式,新版 hermes 输出用 `# 一、人物资产` / `# 二、场景资产` / `# 三、物品资产` 带中文序号** — 整段被跳过,`result_assets = []` → db 没数据可显示
3. **`if desc:` 过滤掉"只有名字没描述"的资产** — `### 物品4：xxx` 后直接换 `### 物品5`,desc 空被丢,丢的资产永不进 db

### 修法(全栈 3 处)
1. `[main_window.py](file:///D:/%E6%BC%AB%E5%89%A7%E5%8A%A9%E6%89%8B/manju-x2/source/src/ui/main_window.py)` 新增 `_invalidate_all_ui_caches()` helper(失效 `_episode_detail_cache` / `_prompt_tab_cache` / `_video_tab_cache` / `_asset_tab_cache` / `_project_overview_cache`),`_persist_task_result` 入口处统一调用。**任何 task 完成**(资产抽取 / 资产生图 / 批量生图 / 分镜 / 提示词 / 视频 / 未来新增)→ 强制清所有 cache → 下次切 tab 重建/刷新 UI
2. `[asset_parser.py](file:///D:/%E6%BC%AB%E5%89%A7%E5%8A%A9%E6%89%8B/manju-x2/source/src/core/asset_parser.py)` 段标题正则:
   ```python
   r"^#{1,4}\s*"
   r"(?:(?:[\d]+|[一二三四五六七八九十]+)\s*[、.\s]\s*)?"
   r"(人物资产|场景资产|物品资产)\s*$"
   ```
   兼容 `## 人物资产` 旧 + `# 一、人物资产` / `## 一、人物资产` / `# 1. 人物资产` 新
3. `[asset_parser.py](file:///D:/%E6%BC%AB%E5%89%A7%E5%8A%A9%E6%89%8B/manju-x2/source/src/core/asset_parser.py)` 空 desc 资产也保留:`if current_name is not None: ... result.append((kind, current_name, desc, img_prompt))` 无论 desc 是否空都 append

## 验证

parser 测试 5 个 case 全部正确:
- 旧格式 `## 人物资产` → 3 个 ✓
- 新格式 `# 一、人物资产` → 3 个 ✓
- 新格式 `## 一、人物资产` → 3 个 ✓
- 新格式 `# 1. 人物资产` → 3 个 ✓
- user 实际 2+2+6=10 个 → **10 个** ✓(之前漏 3 个空 desc 物品)

## 改动

- `ui/main_window.py` `_invalidate_all_ui_caches` + `_persist_task_result` 入口调用
- `core/asset_parser.py` 段标题正则 + 空 desc 保留
- 版本号 1.1.3 → 1.1.4 (main.py 2 处 + main_window.py 1 处 + .iss 1 处)

## 升级

覆盖安装,设置/数据/模型配置不丢。装完跑一次资产抽取,会真的把 10 个资产写入 db,资产 tab 也会真的显示。
