# 漫剧助手X-2 v1.1.2 — 分镜/提示词生成完 UI 不刷新修复

## 安装包

- 文件名: `漫剧助手X-2_v1.1.2_Setup.exe`
- 大小: ~91 MB

## 重点修复

### 分镜/提示词生成完成后 UI 一直显示旧内容
**症状**:
- 点"生成分镜",日志显示"完成: 分镜生成 #1",104 镜
- 但**分镜面板还是"暂无分镜"**,**状态一直 "pending"**
- 退出/重启后再看,**分镜可能消失/不显示**(因为一直在用旧 cache)

**根因**:
`main_window.py:794-796` 的剧集详情 tab 用了 id-only cache,剧集 ID 没变就走 early return,直接复用旧 widget 串。
分镜生成完后,`_persist_task_result` 调 `_show_episode_detail(ep_updated, ...)` 想重建 UI,但因为 ID 没变,**widget 复用**,`ep_updated` 的新 storyboard/status 被丢掉。db 实际上**写好了**,只是 UI 没刷。

**修法**:
在 StoryboardTask 和 VideoPromptTask 的 persist 分支里,调 `_show_episode_detail` **之前**先把 `_episode_detail_cache` 清掉。这样下次进函数就是 cache miss,真的重建 UI。

```python
# v1.1.2 fix:
if (self._episode_detail_cache
        and self._episode_detail_cache[0] == ep_id):
    self._episode_detail_cache = None
ep_updated = self.db.get_episode(ep_id)
...
self._show_episode_detail(ep_updated, self._current_project)
```

`_show_prompt_tab` / `_show_video_tab` 的 cache key 包含 `hash(ep.prompt or "")` / `hash(ep.video_segments or "")`,字段变化时本来就会 invalidate,所以不用改。

## 改动

- `ui/main_window.py`: `_persist_task_result` 在 StoryboardTask/VideoPromptTask 分支 invalidate `_episode_detail_cache` 后再调 `_show_episode_detail`
- 版本号 1.1.1 → 1.1.2 (main.py 2 处 + .iss 1 处)

## 升级

覆盖安装。设置、数据、模型配置不丢。已生成的分镜如果之前是 db 写好但 UI 没刷,**重启后这次就能看到**了。
