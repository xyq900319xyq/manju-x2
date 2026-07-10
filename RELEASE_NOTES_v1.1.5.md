# Release Notes — 漫剧助手X-2 v1.1.5

> 发布日期: 2026-07-10
> 用户反馈"bug 太多体验差",这一版系统化排查了 16 个 BUG(1 致命 + 6 高 + 10 中),全部修完。

## 🔴 致命修复(1 个)

### 导入剧本按钮崩溃 → AttributeError
点"📥 导入剧本"按钮 → AttributeError → Qt 弹"内部错误"。**整个导入剧本功能是坏的**。
- `_on_import_script_file` 调了不存在的 `_show_storyboard_tab`(整个文件 0 处定义)
- 改用真正的分镜 tab 方法 `_show_episode_detail`
- 加 `_invalidate_all_ui_caches()` 防 id-only cache 命中旧 widget

## 🟠 高严重修复(6 个)

| BUG | 修法 |
|---|---|
| 新建项目不自动选中,toolbar 灰的 | `add_project` 返回 item,`setCurrentItem` 触发 selection |
| 新建剧集不自动跳到新剧集 | `add_episode` 返回 child,`setCurrentItem` 触发 selection |
| 删项目后右侧 tab 显示已删内容 | 清空 `_current_project`/`_current_episode` + 切空态 + invalidate cache |
| 删剧集后项目行括号 `(N)` 不更新 | `set_episodes` 重画括号数字 |
| **点"取消分镜"后 hermes 跑满 2 小时** | `StoryboardTask` 补 `cancel()` override,透传 `mt.cancel()` 给 hermes |
| 创维等环境拉不到 update.json | updater.py 3 处全加 `ssl._create_unverified_context()` |
| 资产 image_prompt 切走再回来被回滚 | 写库后 in-place 更新 `self._asset.image_prompt` + 通知 listw item |

## 🟡 中严重修复(10 个)

- 重命名项目后概览 tab 显示旧名(`_project_overview_cache` 命中)
- 编辑剧集后各 tab 显示旧 title/script(`_invalidate_all_ui_caches()` 入口失效)
- 资产生图/批量生图/生视频失败不弹"换模型"对话框(扩到 6 类 task)
- 空 `image_prompt` 直接发给生图 API(返回透明图/随机图)→ 抛 RuntimeError 提示补全
- 拉取模型列表网络异常被吞(按钮恢复但没错误)→ 加 `except Exception` 弹错误框
- 测试 dreamina.exe 异常裸抛 → 加 try/except 弹友好错误
- dreamina OAuth `_dreamina_logged_in` 静默吞 + 启动异常裸抛 → 加 `log.warning` + try/except
- 删项目/剧集时 `itemSelectionChanged` 误触 → `blockSignals` 包 `take*`/`remove*`
- `task_queue` 4 处 emit 信号异常被吞 → 加 `log.warning/exception`
- 数据迁移 / b64 decode / comdlg32 异常被静默吞 → 加 `log.debug` 留痕迹

## 📊 修改文件清单

| 文件 | 改动 |
|---|---|
| `ui/main_window.py` | 7 处(B1-B4, C1-C3, A 致命) |
| `ui/project_tree.py` | 3 处(B1+B2 返回值, C8 block_signals) |
| `ui/asset_panel.py` | 1 处(B7 写库后更新内存) + 1 处(C10 log) |
| `ui/settings_dialog.py` | 4 处(C5-C7 + C10) |
| `core/updater.py` | 1 处(B6 三处加 SSL context) |
| `core/generators.py` | 2 处(B5 cancel override, C4 空 prompt 校验) |
| `core/task_queue.py` | 4 处(C10 emit 异常加 log) |
| `core/image_api.py` | 3 处(C10 b64/on_output 异常加 log) |
| `main.py` | 版本号 v1.1.5 |
| `installer/漫剧助手X-2.iss` | `MyAppVersion` v1.1.5 |
| `docs/更新日志.md` | 加 v1.1.5 段 |

## 验证

- 8 个文件 `py_compile` 全部通过
- pyflakes 静默(无 warning)
- 4 个低严重 BUG 不在本版修复范围(下次)
