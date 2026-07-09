# 漫剧助手X-2 v1.1.3 — 一键更新下载 UnicodeEncodeError 修复

## 重点修复

### 一键更新下载 Setup.exe 时报 UnicodeEncodeError
**症状**:
- 启动后看到红点"🔴 新版 v1.1.2",点一键更新
- 弹"下载失败 - 漫剧助手X-2"对话框,内容:
  ```
  下载安装包失败:
  UnicodeEncodeError: 'ascii' codec can't encode characters in position 51-54: ordinal not in range(128)
  可前往 https://github.com/xyq900319xyq/manju-x2/blob/main/docs/更新日志.md 手动下载。
  ```
- **根本没法下载更新**

**根因**:
`update.json` 里的 `url` 字段是 `https://github.com/.../releases/download/1.1.2/漫剧助手X-2_v1.1.2_Setup.exe`,Setup.exe 文件名含中文"漫剧助手"。`_DownloadWorker` 直接 `urllib.request.Request(self._url)`,传到 `http.client.putrequest` 内部,会执行:
```python
request = 'GET %s HTTP/1.1' % url  # url 含"漫剧助手"
request.encode('iso-8859-1')  # ← 中文 unicode 编码失败
```
抛 `UnicodeEncodeError: 'ascii' codec can't encode characters in position X-Y`(实际 Python 3.11 内部某段包装后的字符串 position 在 51-54,跟"code"对齐,根因都是 url 含中文)。

**修法**(4 层防御):
1. `core/updater.py` `_DownloadWorker.__init__` 阶段用 `urllib.parse.quote(url, safe=":/?&=#%...")` percent-encode 中文,urlopen 拿到的就是纯 ASCII
2. `build_x2.py` 写 `update.json` 时 `url` 字段也对文件名 percent-encode;`changelog_url` 改纯英文 `releases` 页(原 `docs/更新日志.md` 中文路径会让 QMessageBox 弹框也爆)
3. `ui/main_window.py` `_on_error` 防御:`info.html_url` 段强制 `.encode("ascii", "replace").decode("ascii")`(中文 → `?`)
4. `main.py` 启动时 `sys.stdout/stderr.reconfigure(encoding="utf-8", errors="replace")`,防 EXE 启动时 codepage 437/936 触发 `log` 输出 UnicodeEncodeError

## 改动

- `core/updater.py` `_DownloadWorker.__init__`:percent-encode url
- `build_x2.py` 写 `update.json` 字段:url percent-encode + changelog_url 改纯英文
- `ui/main_window.py` `_on_error`:html_url 段 ascii safe
- `main.py` 启动:stdout/stderr reconfigure utf-8
- 版本号 1.1.2 → 1.1.3 (main.py 2 处 + main_window.py 1 处 + .iss 1 处)

## 升级

覆盖安装。设置/数据/模型配置不丢。升级后 v1.1.0/v1.1.1/v1.1.2 用户的"检查更新" / 红点一键更新会真正工作。
