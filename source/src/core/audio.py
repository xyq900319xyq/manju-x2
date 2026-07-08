"""v0.6.20：音频管理（探测 / 修剪 / 复制）。

复刻自原软件 D:\\剧本分镜助手\\server.py:
- `select-audio` / `clear-audio` (server.py:1703-1732) — 选 / 清音频 API
- `_get_audio_duration` (server.py:2110-2121) — ffprobe 取时长
- `_trim_audio_if_needed` (server.py:2124-2170) — ffmpeg 修剪到 2-15s 范围

依赖：
- ffmpeg（裁剪/拼接）
- ffprobe（取时长）

如果 ffmpeg/ffprobe 不可用，所有"修剪"步骤会 fallback 到直接复制。
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger(__name__)


# ---------- 探测 ----------
def is_ffprobe_available() -> bool:
    """探测 ffprobe 是否在 PATH 中。"""
    return shutil.which("ffprobe") is not None


def is_ffmpeg_available() -> bool:
    """探测 ffmpeg 是否在 PATH 中。"""
    return shutil.which("ffmpeg") is not None


# ---------- 时长 ----------
def get_audio_duration(audio_path: Path) -> float:
    """v0.6.20：获取音频时长（秒）。

    复刻自原软件 server.py:2110-2121 `_get_audio_duration`。
    ffprobe 不可用 / 文件不存在 / 解析失败 → 返回 0。
    """
    if not audio_path or not audio_path.exists():
        return 0.0
    if not is_ffprobe_available():
        log.warning("ffprobe 不可用，无法探测音频时长: %s", audio_path)
        return 0.0
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                str(audio_path),
            ],
            capture_output=True, text=True, timeout=10,
        )
        s = r.stdout.strip()
        return float(s) if s else 0.0
    except (subprocess.TimeoutExpired, ValueError, OSError) as e:
        log.warning("获取音频时长失败 %s: %s", audio_path, e)
        return 0.0


# ---------- 修剪 ----------
def trim_audio_if_needed(
    audio_path: Path,
    project_name: str,
    asset_name: str,
    target_min: float = 2.0,
    target_max: float = 15.0,
) -> Tuple[Path, bool]:
    """v0.6.20：检查并修剪音频到 [target_min, target_max] 范围。

    复刻自原软件 server.py:2124-2170 `_trim_audio_if_needed`：
    - 时长在 [2, 15] 秒 → 返回原路径，was_trimmed=False
    - 时长 < 2s → 循环拼接 + 裁剪至 2s
    - 时长 > 15s → 裁剪至 15s
    - 输出到 outputs/<项目>/assets/<资产>/.trimmed_audio/trimmed_<原名>

    Returns:
        (trimmed_path, was_trimmed) — trimmed_path 是原路径或新裁剪路径
    """
    if not audio_path or not audio_path.exists():
        return audio_path, False

    duration = get_audio_duration(audio_path)
    if target_min <= duration <= target_max:
        return audio_path, False

    if not is_ffmpeg_available():
        log.warning("ffmpeg 不可用，跳过修剪: %s", audio_path)
        return audio_path, False

    safe_asset = re.sub(r'[\\/*?:"<>|]', "_", asset_name)
    safe_proj = re.sub(r'[\\/*?:"<>|]', "_", project_name)
    base = audio_path.name
    trim_dir = audio_path.parent / ".trimmed_audio"
    trim_dir.mkdir(parents=True, exist_ok=True)
    trimmed_path = trim_dir / f"trimmed_{base}"

    try:
        if duration < target_min:
            # 循环拼接至 target_min 秒
            loop_count = max(1, int(target_min / max(duration, 0.1)) + 1)
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", str(loop_count),
                "-i", str(audio_path),
                "-t", str(target_min),
                "-ac", "1", "-ar", "16000",
                str(trimmed_path),
            ]
        else:
            # 裁剪至 target_max 秒
            cmd = [
                "ffmpeg", "-y",
                "-i", str(audio_path),
                "-t", str(target_max),
                "-ac", "1", "-ar", "16000",
                str(trimmed_path),
            ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if r.returncode != 0 or not trimmed_path.exists():
            log.warning("ffmpeg 修剪失败 rc=%s: %s", r.returncode, r.stderr[:200])
            return audio_path, False
        return trimmed_path, True
    except (subprocess.TimeoutExpired, OSError) as e:
        log.warning("ffmpeg 修剪异常 %s: %s", audio_path, e)
        return audio_path, False


# ---------- 复制 ----------
def safe_copy_audio(src: Path, dst: Path) -> Path:
    """v0.6.20：复制音频文件到目标位置（自动建目录）。

    复刻自原软件 server.py 中音频文件被复制到 outputs/<项目>/assets/<资产>/
    的行为。dst 一般是 outputs/<项目>/assets/<safe_asset>/<filename>
    """
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return dst


def pick_audio_file_from_outputs(
    project_outputs_dir: Path,
    asset_name: str,
) -> Optional[Path]:
    """v0.6.20：在 outputs/<项目>/assets/<资产>/ 找音频文件。

    复刻自原软件 /browse/<path> 端点 (server.py:1737) 列出 mp3/wav/ogg/m4a/aac。
    找不到返回 None。找到多个返回最新的（按 mtime）。
    """
    AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"}
    if not project_outputs_dir.exists():
        return None
    safe = re.sub(r'[\\/*?:"<>|]', "_", asset_name)
    asset_dir = project_outputs_dir / "assets" / safe
    if not asset_dir.exists():
        # 兜底：扫所有 assets 子目录里文件名前缀匹配的
        for sub in (project_outputs_dir / "assets").glob("*"):
            if sub.is_dir() and sub.name == safe:
                asset_dir = sub
                break
    if not asset_dir.exists():
        return None
    candidates = [
        f for f in asset_dir.iterdir()
        if f.is_file() and f.suffix.lower() in AUDIO_EXTS
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


# ---------- prompt 注入 ----------
def build_audio_injection(audio_files: list) -> str:
    """v0.6.20：把音频路径拼成 prompt 注入文本。

    格式：
        <audio file="C:/path/to/audio1.mp3" />
        <audio file="C:/path/to/audio2.mp3" />

    复刻自原软件 server.py:2369 `dreamina_multimodal2video(audio_files=...)`。
    空列表 → 空字符串。
    """
    if not audio_files:
        return ""
    lines = []
    for a in audio_files:
        p = str(a).replace("\\", "/")
        lines.append(f'<audio file="{p}" />')
    return "\n".join(lines)
