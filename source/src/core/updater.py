"""v1.0.0 用户版：启动后台检查 GitHub releases 有无新版。

设计要点（v1.0.0 用户版）：
- 后台 QThread 拉 GitHub `releases/latest` API（超时 10 秒）
- 比 current_version 跟 tag_name，有新版 → 主线程 UI 红点提示
- 拉失败（无网 / GitHub 限流）→ 静默，不弹错
- 缓存上次结果到 `config/.update_check_cache.json`：
  - 24 小时内不重复拉（避免每次启动都打 GitHub）
  - 缓存结构同 UpdateInfo，启动时直接用缓存
- 用户主动"检查更新" → 跳过缓存强制拉
- 不做 EXE 内下载（避免 EXE 占用 + 防病毒误报），只给 release 页 URL 让浏览器打开

v1.0.0【硬约束】：
- 不写兜底：拉取失败静默，但**不**塞"已是最新版"假数据
- 缓存不算"权威结果"：UI 显示红点时**必须**有真版本号
- 不在 QThread 构造里访问 QWidget（Qt 线程亲和性）
- 不引入新依赖：用 stdlib urllib
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal

log = logging.getLogger("manju.updater")

# GitHub repo 占位符（Phase 7 发版前用环境变量覆盖）
DEFAULT_GITHUB_REPO = os.environ.get("MANJU_X2_GITHUB_REPO", "xyq900319xyq/manju-x2")
GITHUB_API_LATEST = "https://api.github.com/repos/{repo}/releases/latest"
# v1.1.1【静态回退源】：raw.githubusercontent.com 不限速,build 后把
# release/update.json 推到 main 分支即可。优先用这个,GitHub API 仅作兜底
# (60 次/小时/IP 限速,大量用户同时用会撞墙)
UPDATE_JSON_URL = os.environ.get(
    "MANJU_X2_UPDATE_JSON_URL",
    "https://raw.githubusercontent.com/xyq900319xyq/manju-x2/main/release/update.json",
)
CACHE_FILENAME = ".update_check_cache.json"
CACHE_TTL_SECONDS = 24 * 3600  # 24h
HTTP_TIMEOUT = 10  # 秒


# ---------- 数据 ----------

@dataclass
class UpdateInfo:
    """更新检查结果。

    has_update / error_msg 互斥：
    - 拉取成功:has_update=True/False, latest_version/html_url/release_notes/asset_url 有意义
    - 拉取失败:error_msg 有值, has_update=False
    """
    has_update: bool = False
    current_version: str = ""
    latest_version: str = ""
    html_url: str = ""
    release_notes: str = ""
    asset_url: str = ""  # v1.1.0: Setup.exe 的 browser_download_url
    asset_size: int = 0  # v1.1.0: 字节数,UI 进度条用
    error_msg: str = ""
    checked_at: float = 0.0  # time.time() 时间戳

    def to_cache_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_cache_dict(cls, d: dict) -> "UpdateInfo":
        return cls(
            has_update=bool(d.get("has_update", False)),
            current_version=str(d.get("current_version", "") or ""),
            latest_version=str(d.get("latest_version", "") or ""),
            html_url=str(d.get("html_url", "") or ""),
            release_notes=str(d.get("release_notes", "") or ""),
            asset_url=str(d.get("asset_url", "") or ""),
            asset_size=int(d.get("asset_size", 0) or 0),
            error_msg=str(d.get("error_msg", "") or ""),
            checked_at=float(d.get("checked_at", 0) or 0),
        )


# ---------- 缓存 ----------

def _cache_path(project_root: Path) -> Path:
    return Path(project_root) / "config" / CACHE_FILENAME


def load_cache(project_root: Path) -> Optional[UpdateInfo]:
    """读缓存。不存在 / 损坏 / TTL 过期 → 返回 None（让 UI 不显示红点）。"""
    p = _cache_path(project_root)
    if not p.exists():
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        log.warning("updater: 缓存读失败 %s: %s", p, e)
        return None
    return UpdateInfo.from_cache_dict(d)


def save_cache(project_root: Path, info: UpdateInfo) -> None:
    """写缓存。失败静默（不影响主流程）。"""
    p = _cache_path(project_root)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(info.to_cache_dict(), f, ensure_ascii=False, indent=2)
    except OSError as e:
        log.warning("updater: 缓存写失败 %s: %s", p, e)


def is_cache_fresh(info: Optional[UpdateInfo], ttl: int = CACHE_TTL_SECONDS) -> bool:
    """缓存是否在 TTL 内 + 拉取过（不是首次） + 没出错。"""
    if info is None:
        return False
    if not info.checked_at:
        return False
    if info.error_msg:
        return False  # 失败的缓存不能算"fresh"，让重试
    return (time.time() - info.checked_at) < ttl


# ---------- 版本比对 ----------

def _ver_tuple(v: str) -> tuple:
    """把 '1.0.0' / 'v1.0.1' / '1.2.3-beta' 解析成可比较的 tuple。

    数字段按 int 比，非数字段按字符串比。无法解析的字符归零。
    例：'1.0.0' → (1,0,0, '')
         'v1.0.1' → (1,0,1, '')
         '1.2.3-beta' → (1,2,3, 'beta')
    """
    if not v:
        return (0,)
    s = str(v).strip()
    if s.startswith(("v", "V")):
        s = s[1:]
    parts = s.split("-", 1)
    main = parts[0]
    suffix = parts[1] if len(parts) > 1 else ""
    nums = []
    for seg in main.split("."):
        seg = seg.strip()
        try:
            nums.append(int(seg))
        except ValueError:
            # 含非数字字符（少见），退回 0
            nums.append(0)
    return tuple(nums) + (suffix,)


def has_newer_version(current: str, latest: str) -> bool:
    """latest > current？严格比较，相等 / latest < current → False。"""
    return _ver_tuple(latest) > _ver_tuple(current)


# ---------- 拉取（同步，QThread 调） ----------

def fetch_update_json(url: str = UPDATE_JSON_URL, timeout: int = HTTP_TIMEOUT) -> UpdateInfo:
    """v1.1.1：拉 release/update.json(静态文件,raw.githubusercontent.com 不限速)。

    update.json 结构(由 build_x2.py 写):
        {
          "version": "1.1.0",
          "url": "https://github.com/.../Setup.exe",
          "md5": "...",
          "sha256": "...",
          "size": 91186388,
          "changelog_url": "https://github.com/.../更新日志.md",
          "release_date": "2026-07-09"
        }

    Returns:
        UpdateInfo: 成功时 latest_version/asset_url/asset_size/html_url 填好
        失败时 error_msg 填好
    """
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "manju-x2-updater/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return UpdateInfo(
                    error_msg=f"update.json HTTP {resp.status}",
                    checked_at=time.time(),
                )
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return UpdateInfo(error_msg=f"{type(e).__name__}: {e}", checked_at=time.time())
    except Exception as e:  # noqa: BLE001
        return UpdateInfo(error_msg=f"{type(e).__name__}: {e}", checked_at=time.time())

    ver = str(data.get("version", "") or "").strip()
    asset_url = str(data.get("url", "") or "").strip()
    asset_size = int(data.get("size", 0) or 0)
    html_url = str(data.get("changelog_url", "") or "").strip()
    if not ver:
        return UpdateInfo(error_msg="update.json 无 version 字段", checked_at=time.time())
    return UpdateInfo(
        has_update=False,  # 由调用方比 current 后再设
        latest_version=ver,
        html_url=html_url,
        asset_url=asset_url,
        asset_size=asset_size,
        current_version="",  # 由调用方注入
        error_msg="",
        checked_at=time.time(),
    )


def fetch_latest_release(repo: str = DEFAULT_GITHUB_REPO, timeout: int = HTTP_TIMEOUT) -> UpdateInfo:
    """同步拉最新 release 信息。

    v1.1.1【优先级】:
    1. 先试 release/update.json(raw.githubusercontent.com,不限速)
    2. 失败再走 GitHub API(api.github.com,60/h/IP 限速)
    3. 两个都失败 → error_msg 填好返回

    Returns:
        UpdateInfo：成功时 has_update/latest_version/html_url 填好；
        失败时 error_msg 填好, has_update=False。
        任何异常都包成 info 返回，**不**抛（让 QThread 拿到结果发信号给 UI）。
    """
    # 1) 优先 update.json(无 rate limit)
    info = fetch_update_json(timeout=timeout)
    if not info.error_msg and info.latest_version:
        log.info("updater: update.json 命中 %s", info.latest_version)
        return info
    if info.error_msg:
        log.info("updater: update.json 失败(%s),降级到 GitHub API", info.error_msg)
    # 2) 兜底 GitHub API
    url = GITHUB_API_LATEST.format(repo=repo)
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "manju-x2-updater/1.0",
                "Accept": "application/vnd.github+json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return UpdateInfo(
                    error_msg=f"HTTP {resp.status}",
                    checked_at=time.time(),
                )
            raw = resp.read().decode("utf-8", errors="replace")
            data = json.loads(raw)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return UpdateInfo(error_msg=f"{type(e).__name__}: {e}", checked_at=time.time())
    except Exception as e:  # noqa: BLE001
        return UpdateInfo(error_msg=f"{type(e).__name__}: {e}", checked_at=time.time())

    tag = str(data.get("tag_name", "") or "").strip()
    html_url = str(data.get("html_url", "") or "").strip()
    notes = str(data.get("body", "") or "")
    if not tag:
        return UpdateInfo(error_msg="API 响应无 tag_name", checked_at=time.time())
    # 解析 assets 找 Setup.exe
    asset_url = ""
    asset_size = 0
    for a in (data.get("assets") or []):
        name = str(a.get("name", "") or "")
        if not name:
            continue
        if name.startswith("Source code"):
            continue
        if not name.lower().endswith(".exe"):
            continue
        asset_url = str(a.get("browser_download_url", "") or "").strip()
        asset_size = int(a.get("size", 0) or 0)
        break
    return UpdateInfo(
        has_update=False,  # 由调用方比 current 后再设
        latest_version=tag,
        html_url=html_url,
        release_notes=notes[:2000],  # 截断防内存炸
        asset_url=asset_url,
        asset_size=asset_size,
        current_version="",
        error_msg="",
        checked_at=time.time(),
    )


# ---------- QObject worker + QThread ----------

class _UpdateWorker(QObject):
    """跑在 QThread 上的 worker，emit result(UpdateInfo) 信号回主线程。"""
    finished = Signal(object)  # UpdateInfo

    def __init__(self, current_version: str, repo: str, force: bool) -> None:
        super().__init__()
        self._current = current_version
        self._repo = repo
        self._force = force  # True: 用户点"检查更新" 跳过缓存

    def run(self) -> None:
        info = fetch_latest_release(repo=self._repo)
        info.current_version = self._current
        if not info.error_msg and info.latest_version:
            info.has_update = has_newer_version(self._current, info.latest_version)
        self.finished.emit(info)


class UpdateChecker(QObject):
    """主线程持有的 controller，对外暴露 start_async / use_cache / latest_info。

    使用：
        checker = UpdateChecker(project_root, current_version, parent=window)
        checker.start_async()  # 启动后台拉取
        # ... UI 监听 checker.update_available 信号 ...
    """
    update_available = Signal(object)  # UpdateInfo（有新版）
    no_update = Signal(object)         # UpdateInfo（无新版 / 拉取失败）
    checked = Signal(object)           # 任意拉取完成（含失败）

    def __init__(self, project_root: Path, current_version: str,
                 parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._project_root = Path(project_root)
        self._current = current_version
        self._latest_info: Optional[UpdateInfo] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[_UpdateWorker] = None
        # 启动时读缓存（如果 fresh 就不主动拉）
        self._latest_info = load_cache(self._project_root)

    @property
    def latest_info(self) -> Optional[UpdateInfo]:
        return self._latest_info

    def is_update_available(self) -> bool:
        return self._latest_info is not None and self._latest_info.has_update

    def start_async(self, force: bool = False) -> bool:
        """启动后台拉取。

        Returns:
            True: 已启动 / 缓存可用跳过拉取
            False: 已有拉取任务在跑（不重复启动）
        """
        # 缓存 fresh 且非强制 → 跳过拉取
        if not force and is_cache_fresh(self._latest_info):
            log.info("updater: 缓存 24h 内，跳过拉取 latest=%s",
                     self._latest_info.latest_version if self._latest_info else "?")
            # 仍 emit 一次让 UI 同步
            if self._latest_info is not None:
                if self._latest_info.has_update:
                    self.update_available.emit(self._latest_info)
                else:
                    self.no_update.emit(self._latest_info)
                self.checked.emit(self._latest_info)
            return True
        if self._thread is not None and self._thread.isRunning():
            log.info("updater: 已有任务在跑，跳过新启动")
            return False

        self._thread = QThread(self)
        self._worker = _UpdateWorker(self._current, DEFAULT_GITHUB_REPO, force)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_finished)
        # 清理：worker 完成后自动 quit thread
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._reset_thread_refs)
        self._thread.start()
        log.info("updater: 启动后台拉取 force=%s", force)
        return True

    def _on_finished(self, info: UpdateInfo) -> None:
        self._latest_info = info
        save_cache(self._project_root, info)
        if info.error_msg:
            log.info("updater: 拉取失败 %s（不弹错）", info.error_msg)
            self.no_update.emit(info)
        elif info.has_update:
            log.info("updater: 有新版 %s → %s", self._current, info.latest_version)
            self.update_available.emit(info)
        else:
            log.info("updater: 已是最新版 %s", info.latest_version or self._current)
            self.no_update.emit(info)
        self.checked.emit(info)

    def _reset_thread_refs(self) -> None:
        self._thread = None
        self._worker = None


# ---------- v1.1.0 一键更新：后台下载 Setup.exe ----------

class _DownloadWorker(QObject):
    """跑在 QThread 上,流式下载 Setup.exe 到磁盘,emit progress / finished / error。

    取消: 设 self._cancel = True(由 UpdateDownloader.cancel() 调)。
    流式 read(64KB),每 ~1% 触发一次 progress,避免频繁 signal 阻塞主线程。
    """
    progress = Signal(int, int, int)  # percent (0-100), received, total
    finished = Signal(str)            # dest_path
    error = Signal(str)               # error msg

    CHUNK = 64 * 1024  # 64KB

    def __init__(self, url: str, dest_path: str) -> None:
        super().__init__()
        # v1.1.3【防 UnicodeEncodeError】:url 可能含中文(比如
        # update.json 的 url 字段是 ".../漫剧助手X-2_v1.1.2_Setup.exe"),
        # 直接传给 urllib.request.Request → http.client.putrequest 内部
        # `request.encode('iso-8859-1')` 会爆 "UnicodeEncodeError: 'ascii'
        # codec can't encode characters in position X-Y"。
        # 防御:__init__ 阶段先 percent-encode 中文,urlopen 拿到的就是纯 ASCII。
        # safe 保留 scheme/path/query/fragment 关键符号,避免改语义。
        try:
            self._url = urllib.parse.quote(url, safe=":/?&=#%!$&'()*+,;=:@")
        except Exception:
            self._url = url
        self._dest = dest_path
        self._cancel = False

    def run(self) -> None:
        try:
            req = urllib.request.Request(
                self._url,
                headers={"User-Agent": "manju-x2-updater/1.1"},
            )
            with urllib.request.urlopen(req, timeout=300) as resp:
                total = int(resp.headers.get("Content-Length", 0) or 0)
                received = 0
                last_pct = -1
                os.makedirs(os.path.dirname(self._dest), exist_ok=True)
                with open(self._dest, "wb") as f:
                    while True:
                        if self._cancel:
                            f.close()
                            try:
                                os.remove(self._dest)
                            except OSError:
                                pass
                            self.error.emit("用户取消")
                            return
                        chunk = resp.read(self.CHUNK)
                        if not chunk:
                            break
                        f.write(chunk)
                        received += len(chunk)
                        if total > 0:
                            pct = int(received * 100 / total)
                            if pct != last_pct:
                                last_pct = pct
                                self.progress.emit(pct, received, total)
                        else:
                            # 不知道总大小时,按 1MB 一次发
                            if received % (1024 * 1024) < self.CHUNK:
                                self.progress.emit(-1, received, 0)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            self.error.emit(f"{type(e).__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            self.error.emit(f"{type(e).__name__}: {e}")
        else:
            self.progress.emit(100, received, total or received)
            self.finished.emit(self._dest)


class UpdateDownloader(QObject):
    """v1.1.0 一键更新：后台下载 Setup.exe。

    用法:
        dl = UpdateDownloader(parent=window)
        dl.start(asset_url, dest_path)
        # 监听 dl.progress / dl.finished / dl.error
    """
    progress = Signal(int, int, int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._thread: Optional[QThread] = None
        self._worker: Optional[_DownloadWorker] = None
        self._dest: str = ""

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def start(self, url: str, dest_path: str) -> bool:
        """启动后台下载。Returns: True 已启动, False 已在跑。"""
        if self.is_running():
            log.warning("updater.download: 已有下载任务在跑,忽略新启动")
            return False
        if not url or not dest_path:
            self.error.emit("url 或 dest_path 为空")
            return False
        self._dest = dest_path
        self._thread = QThread(self)
        self._worker = _DownloadWorker(url, dest_path)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.progress.emit)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._reset_thread_refs)
        self._thread.start()
        log.info("updater.download: 启动下载 %s → %s", url, dest_path)
        return True

    def cancel(self) -> None:
        """用户取消:设 worker._cancel,worker 下次循环检查会退出 + 删文件。"""
        if self._worker is not None:
            self._worker._cancel = True
            log.info("updater.download: 用户取消")

    def _on_finished(self, dest: str) -> None:
        log.info("updater.download: 下载完成 %s", dest)
        self.finished.emit(dest)

    def _on_error(self, msg: str) -> None:
        log.info("updater.download: 下载失败 %s", msg)
        self.error.emit(msg)
        # 清理半成品
        if self._dest and os.path.exists(self._dest):
            try:
                os.remove(self._dest)
            except OSError:
                pass

    def _reset_thread_refs(self) -> None:
        self._thread = None
        self._worker = None
