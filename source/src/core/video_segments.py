"""v0.6.19：剧集视频分段管理。

复刻自原软件 D:\\剧本分镜助手\\server.py:1185-1207 的
`GET/POST /api/episodes/<id>/video-segments` API — 把整段 prompt 切成多个
segments，每个段独立生成视频。

数据格式（JSON 字符串存在 `ep.video_segments` 字段）：
    {
        "ep_num": 1,
        "ep_title": "第1集：xxx",
        "segments": [
            {
                "id": "seg_001",
                "title": "开场 - 山门",
                "text": "导演: ...\\n画面: ...",
                "assets": [
                    {"name": "林天", "kind": "character", "image_path": "..."}
                ],
                "duration": 4,
                "model": "seedance2.0fast",
                "ratio": "16:9",
                "quality": "720p",
                "video_path": "D:\\\\...\\\\video_ep01_seg01_xxx.mp4",
                "video_status": "ready",   # pending / generating / ready / failed
                "audio_path": "",          # v0.6.20 音频管理用
                "created_at": "2026-06-28T10:00:00"
            }
        ]
    }

向后兼容：旧版（v0.6.18 之前）`video_segments` 字段是换行分隔的纯文本路径
列表（每行一个 mp4 路径）。`parse_video_segments()` 检测到非 JSON 字符串时
自动按换行切，每行包成 1 个 segment。
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict


# ---------- 常量 ----------
VIDEO_STATUS_PENDING = "pending"        # 未生成
VIDEO_STATUS_GENERATING = "generating"  # 生成中
VIDEO_STATUS_READY = "ready"            # 已生成
VIDEO_STATUS_FAILED = "failed"          # 失败


# ---------- dataclass ----------
@dataclass
class VideoSegment:
    """单个视频段。

    字段语义复刻自原软件 server.py:2179-2188 的 `segments.push({...})`，
    扩展了 `video_path` / `video_status` / `audio_path` / `created_at`。
    """
    id: str
    title: str = ""
    text: str = ""                                # 段的 prompt 文本
    assets: List[Dict[str, str]] = field(default_factory=list)  # [{name, kind, image_path}]
    duration: int = 4
    model: str = "seedance2.0fast"
    ratio: str = "16:9"
    quality: str = "720p"
    video_path: str = ""                          # 生成的 mp4 路径
    video_status: str = VIDEO_STATUS_PENDING
    audio_path: str = ""                          # v0.6.20 音频
    created_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "VideoSegment":
        """从 dict 构造，缺字段用默认值。"""
        return cls(
            id=d.get("id") or f"seg_{uuid.uuid4().hex[:8]}",
            title=d.get("title", ""),
            text=d.get("text", ""),
            assets=list(d.get("assets", [])),
            duration=int(d.get("duration", 4)),
            model=d.get("model", "seedance2.0fast"),
            ratio=d.get("ratio", "16:9"),
            quality=d.get("quality", "720p"),
            video_path=d.get("video_path", ""),
            video_status=d.get("video_status", VIDEO_STATUS_PENDING),
            audio_path=d.get("audio_path", ""),
            created_at=d.get("created_at", ""),
        )

    def is_ready(self) -> bool:
        return self.video_status == VIDEO_STATUS_READY and bool(self.video_path)

    def has_audio(self) -> bool:
        return bool(self.audio_path)


# ---------- 解析 / 序列化 ----------
def _new_seg_id() -> str:
    return f"seg_{uuid.uuid4().hex[:8]}"


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def empty_envelope(ep_num: int = 0, ep_title: str = "") -> dict:
    """v0.6.19：造一个空的 envelopes（无段）。"""
    return {
        "ep_num": ep_num,
        "ep_title": ep_title,
        "segments": [],
    }


def parse_video_segments(raw: str, ep_num: int = 0, ep_title: str = "") -> dict:
    """v0.6.19：解析 `ep.video_segments` 字段。

    行为：
    1. 空字符串 → 空 envelopes
    2. 合法 JSON → 返回反序列化后的 dict（保证有 ep_num / ep_title / segments 三个 key）
    3. 旧版纯文本（v0.6.18 之前的换行分隔路径列表）→ 按行切，每行包成 1 个 segment
       （video_status=ready、video_path=<该行>）

    复刻自原软件 server.py:1185-1196 `get_video_segments` 的 JSON 解析行为，
    并加了**向后兼容**分支。
    """
    if not raw or not raw.strip():
        return empty_envelope(ep_num, ep_title)

    s = raw.strip()

    # 1. 尝试 JSON
    if s.startswith("{") or s.startswith("["):
        try:
            data = json.loads(s)
            if isinstance(data, list):
                # 兼容：旧版直接是 segments list（极端情况）
                data = {"ep_num": ep_num, "ep_title": ep_title, "segments": data}
            elif isinstance(data, dict):
                # 缺 key 补上
                data.setdefault("ep_num", ep_num)
                data.setdefault("ep_title", ep_title)
                data.setdefault("segments", [])
            else:
                return empty_envelope(ep_num, ep_title)
            # segments 元素强转为 VideoSegment（用 from_dict 容错）
            data["segments"] = [
                VideoSegment.from_dict(s).to_dict()
                for s in data["segments"]
                if isinstance(s, dict)
            ]
            return data
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # 2. 旧版纯文本：每行一个路径
    segments: list = []
    for line in s.splitlines():
        line = line.strip()
        if not line:
            continue
        seg = VideoSegment(
            id=_new_seg_id(),
            title=Path(line).stem,  # 默认用文件名做 title
            text="",                 # 旧版没存 prompt 文本
            video_path=line,
            video_status=VIDEO_STATUS_READY,
            created_at=_now_iso(),
        )
        segments.append(seg.to_dict())
    return {
        "ep_num": ep_num,
        "ep_title": ep_title,
        "segments": segments,
    }


def dump_video_segments(envelope: dict) -> str:
    """v0.6.19：把 envelope 序列化成 JSON 字符串（写回 db）。"""
    # 强制 ep_num / ep_title / segments 三个 key 存在
    envelope = {
        "ep_num": int(envelope.get("ep_num", 0) or 0),
        "ep_title": str(envelope.get("ep_title", "") or ""),
        "segments": list(envelope.get("segments", []) or []),
    }
    return json.dumps(envelope, ensure_ascii=False)


# ---------- 段操作 ----------
def add_segment(
    envelope: dict,
    title: str = "",
    text: str = "",
    duration: int = 4,
    model: str = "seedance2.0fast",
    ratio: str = "16:9",
    quality: str = "720p",
) -> dict:
    """v0.6.19：往 envelope 加一个新段（默认在末尾）。

    返回新 envelope（**不修改原对象**，方便 UI 层 setattr）。
    """
    seg = VideoSegment(
        id=_new_seg_id(),
        title=title or f"段 {len(envelope.get('segments', [])) + 1}",
        text=text,
        duration=duration,
        model=model,
        ratio=ratio,
        quality=quality,
        video_status=VIDEO_STATUS_PENDING,
        created_at=_now_iso(),
    )
    new_env = dict(envelope)
    segs = list(new_env.get("segments", []))
    segs.append(seg.to_dict())
    new_env["segments"] = segs
    return new_env


def remove_segment(envelope: dict, seg_id: str) -> dict:
    """v0.6.19：删指定 id 的段。"""
    new_env = dict(envelope)
    segs = [s for s in new_env.get("segments", []) if s.get("id") != seg_id]
    new_env["segments"] = segs
    return new_env


def reorder_segment(envelope: dict, seg_id: str, new_index: int) -> dict:
    """v0.6.19：把段移到 new_index 位置（夹到 [0, n-1] 范围）。"""
    new_env = dict(envelope)
    segs = list(new_env.get("segments", []))
    idx = next((i for i, s in enumerate(segs) if s.get("id") == seg_id), -1)
    if idx < 0:
        return new_env
    seg = segs.pop(idx)
    new_index = max(0, min(int(new_index), len(segs)))
    segs.insert(new_index, seg)
    new_env["segments"] = segs
    return new_env


def merge_segments(envelope: dict, seg_ids: List[str]) -> dict:
    """v0.6.19：合并多个段为 1 个段（按原顺序拼接 text，清空其他段）。

    合并后：
    - 第一个段的 text = 所有选中段 text 拼接（双换行分隔）
    - 第一个段的 assets = 所有选中段 assets 去并
    - 其他段被删
    - 视频字段（video_path / video_status / audio_path）**清空** —
      合并后必须重新生成（不能简单拼视频）
    """
    new_env = dict(envelope)
    segs = list(new_env.get("segments", []))
    selected = [s for s in segs if s.get("id") in set(seg_ids)]
    if len(selected) < 2:
        return new_env  # < 2 段不合并
    selected.sort(
        key=lambda s: next((i for i, x in enumerate(segs) if x.get("id") == s.get("id")), 0)
    )
    first = dict(selected[0])
    # 拼接 text
    merged_text = "\n\n".join(s.get("text", "") for s in selected if s.get("text"))
    first["text"] = merged_text
    # 合并 assets（按 name 去重）
    seen = set()
    merged_assets = []
    for s in selected:
        for a in s.get("assets", []):
            n = a.get("name", "")
            if n and n not in seen:
                seen.add(n)
                merged_assets.append(a)
    first["assets"] = merged_assets
    # 清视频字段
    first["video_path"] = ""
    first["video_status"] = VIDEO_STATUS_PENDING
    first["audio_path"] = ""
    # 替换原列表
    selected_ids = set(seg_ids)
    new_segs = [first] + [s for s in segs if s.get("id") not in selected_ids]
    new_env["segments"] = new_segs
    return new_env


def split_segment_by_marker(
    envelope: dict,
    seg_id: str,
    marker_pattern: str = r"\n##\s+分镜\d+",
) -> dict:
    """v0.6.19：把 1 段按 marker 正则切分成多段。

    默认按"\\n## 分镜N"切（与原软件 server.py:2179 段切分一致）。
    第一段保留原 id，其他段新生成 id。
    """
    new_env = dict(envelope)
    segs = list(new_env.get("segments", []))
    target = next((s for s in segs if s.get("id") == seg_id), None)
    if not target:
        return new_env
    text = target.get("text", "")
    if not text:
        return new_env
    parts = re.split(marker_pattern, text)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) < 2:
        return new_env
    # 第一段保留原 id 和元数据
    first = dict(target)
    first["text"] = parts[0]
    first["video_path"] = ""
    first["video_status"] = VIDEO_STATUS_PENDING
    # 后续段新 id
    new_segs = [first]
    idx = target_idx = next(
        (i for i, s in enumerate(segs) if s.get("id") == seg_id), -1
    )
    for p in parts[1:]:
        new_segs.append(VideoSegment(
            id=_new_seg_id(),
            title=f"分镜{len(new_segs) + 1}",
            text=p,
            duration=target.get("duration", 4),
            model=target.get("model", "seedance2.0fast"),
            ratio=target.get("ratio", "16:9"),
            quality=target.get("quality", "720p"),
            video_status=VIDEO_STATUS_PENDING,
            created_at=_now_iso(),
        ).to_dict())
    # 替换原段
    new_segs_full = segs[:idx] + new_segs + segs[idx + 1:]
    new_env["segments"] = new_segs_full
    return new_env


def update_segment_video(
    envelope: dict,
    seg_id: str,
    video_path: str,
    status: str = VIDEO_STATUS_READY,
) -> dict:
    """v0.6.19：更新指定段的 video_path / video_status。"""
    new_env = dict(envelope)
    segs = list(new_env.get("segments", []))
    for s in segs:
        if s.get("id") == seg_id:
            s["video_path"] = video_path
            s["video_status"] = status
            break
    new_env["segments"] = segs
    return new_env


# ---------- 统计 / 工具 ----------
def count_ready(envelope: dict) -> int:
    return sum(1 for s in envelope.get("segments", []) if s.get("video_status") == VIDEO_STATUS_READY)


def get_segment(envelope: dict, seg_id: str) -> Optional[dict]:
    for s in envelope.get("segments", []):
        if s.get("id") == seg_id:
            return s
    return None


def total_duration(envelope: dict) -> int:
    return sum(int(s.get("duration", 0)) for s in envelope.get("segments", []))
