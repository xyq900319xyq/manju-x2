"""数据模型。"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Project:
    id: str
    name: str
    description: str = ""
    style_id: str = ""
    render_type: str = ""
    created_at: str = ""
    updated_at: Optional[str] = None
    episode_count: int = 0  # 非 db 字段，列表展示用


@dataclass
class Episode:
    id: str
    project_id: str
    episode_num: int
    title: str = ""
    script: str = ""
    storyboard: str = ""
    status: str = "pending"
    prompt: str = ""
    prompt_status: str = ""
    video_segments: str = ""   # 视频文件路径列表（换行分隔），由 VideoTask 写入
    asset_status: str = ""
    # v0.6.18：剧集级 render_type（可空 — 空时用项目的 render_type）
    # 复刻自原软件 D:\剧本分镜助手\server.py（PATCH /api/episodes/<eid> 接受 render_type）
    render_type: str = ""
    created_at: str = ""
    updated_at: Optional[str] = None
    mode: str = "storyboard"


# 资产类型（中文 / DB 值 / 中文标签）
ASSET_KIND_CHARACTER = "character"
ASSET_KIND_SCENE = "scene"
ASSET_KIND_PROP = "prop"
ASSET_KINDS = [ASSET_KIND_CHARACTER, ASSET_KIND_SCENE, ASSET_KIND_PROP]
ASSET_KIND_LABELS = {
    "character": "人物",
    "scene": "场景",
    "prop": "物品",
}

# 资产生图状态
ASSET_STATUS_PENDING = "pending"      # 未生成
ASSET_STATUS_GENERATING = "generating"  # 生成中（任务在跑）
ASSET_STATUS_READY = "ready"          # 已生成图片
ASSET_STATUS_FAILED = "failed"        # 生成失败


@dataclass
class Asset:
    id: str
    project_id: str
    name: str
    kind: str = ASSET_KIND_CHARACTER
    description: str = ""
    image_path: str = ""
    image_status: str = ASSET_STATUS_PENDING
    image_prompt: str = ""
    image_updated: Optional[str] = None
    created_at: str = ""
    updated_at: Optional[str] = None
    # v0.7.8：参考图列表（base64 data URL,JSON 存 db）
    # 复刻自老 software D:\剧本分镜助手\templates\index.html:1101-1173
    # 生图时只要有参考图就在 body 加 "image" 字段（图生图），
    # 没参考图就是纯文生图。最大 16 张。
    ref_images: List[str] = field(default_factory=list)
