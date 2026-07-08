"""v0.6.23：资产历史文件浏览（图片 + 音频）。

复刻自原软件 D:\\剧本分镜助手\\server.py:1737-1793 `GET /browse/<path>`：
扫描 `outputs/<项目>/assets/<safe_asset_name>/` 下所有图片 + 音频，列出文件名 +
路径 + 类型，让用户"⭐ 选择此图"作为当前资产图 / "🎵 选为音频"作为当前资产音频。

设计：
- 纯函数扫描 + 选为当前逻辑（无 Qt 依赖，单独测）
- UI 在 `ui/asset_browser_dialog.py` 调这里
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List

log = logging.getLogger(__name__)


# 支持的文件后缀（与原软件 server.py:1743 列表一致）
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
AUDIO_EXTS = (".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac")
ALL_EXTS = IMAGE_EXTS + AUDIO_EXTS


@dataclass
class AssetFile:
    """v0.6.23：单条历史文件（图片 or 音频）。"""
    name: str                # 文件名（含后缀）
    path: str                # 绝对路径
    kind: str                # "image" | "audio"
    size: int = 0            # 字节数
    mtime: float = 0.0       # 修改时间戳（按 mtime 倒序用）


def list_asset_files(asset_dir: Path) -> List[AssetFile]:
    """v0.6.23：扫描 asset_dir 下所有图片 + 音频，按 mtime 倒序（最新在前）。

    复刻原软件 server.py:1742-1743 `os.listdir + 过滤 .png/.jpg/...`，
    manju 用 mtime 倒序而不是字母序（更直观，AI 刚生成的在最前）。
    """
    if not asset_dir or not asset_dir.exists() or not asset_dir.is_dir():
        return []
    result: List[AssetFile] = []
    for p in asset_dir.iterdir():
        if not p.is_file():
            continue
        ext = p.suffix.lower()
        if ext in IMAGE_EXTS:
            kind = "image"
        elif ext in AUDIO_EXTS:
            kind = "audio"
        else:
            continue
        try:
            st = p.stat()
            result.append(AssetFile(
                name=p.name, path=str(p.resolve()), kind=kind,
                size=st.st_size, mtime=st.st_mtime,
            ))
        except OSError as e:
            log.warning("stat failed for %s: %s", p, e)
            continue
    # 按 mtime 倒序（最新在前）
    result.sort(key=lambda f: f.mtime, reverse=True)
    return result


def safe_asset_dir_name(asset_name: str) -> str:
    """v0.6.23：资产名 → 文件夹名（与原软件 server.py:1688 `_safe_asset` 一致）。

    把 `\\ / * ? : " < > |` 全替换成 `_`，空字符串退化成 `asset`。
    """
    safe = re.sub(r'[\\/*?:"<>|]', "_", asset_name or "").strip()
    return safe or "asset"


def find_asset_dir(project_outputs_dir: Path, project_name: str, asset_name: str) -> Path:
    """v0.6.23：计算 outputs/<项目>/assets/<safe_asset>/ 完整路径。

    复刻原软件 server.py:1689 `os.path.join(OUTPUT_DIR, project, "assets", safe_asset)`。
    """
    safe_proj = re.sub(r'[\\/*?:"<>|]', "_", project_name or "").strip() or "default"
    safe_asset = safe_asset_dir_name(asset_name)
    return Path(project_outputs_dir) / safe_proj / "assets" / safe_asset


def pick_image_as_current(
    db,
    project_id: str,
    asset_name: str,
    image_path: str,
) -> None:
    """v0.6.23：把选中的图片写入 db 作为当前资产图（image_path + image_status=ready）。

    复刻原软件 `localStorage.setItem("selected_...")` + reload 行为。
    manju 不存 localStorage（Qt 没有浏览器），改成直接写 db。
    """
    # 查 asset_id（按 name + project_id 找第一个匹配的）
    assets = db.list_assets(project_id)
    asset = next((a for a in assets if a.name == asset_name), None)
    if asset is None:
        log.warning("pick_image_as_current: asset not found: project=%s name=%s", project_id, asset_name)
        return
    # v0.7.7 重打 20：update_asset_image 移除了 image_prompt 参数，不再传
    # "(从历史图选择)" marker（违规用 image_prompt 字段当图片来源）。
    db.update_asset_image(
        asset_id=asset.id,
        image_path=image_path,
        image_status="ready",
    )


def pick_audio_as_current(
    db,
    project_id: str,
    asset_name: str,
    audio_path: str,
) -> None:
    """v0.6.23：把选中的音频写入 db 作为当前资产音频（audio_selections 表）。

    复刻原软件 `selectAssetFile()` 的 `POST /api/select-audio` 端点 server.py:1763。
    """
    db.set_audio_selection(project_id, asset_name, audio_path)
