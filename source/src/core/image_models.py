"""v0.7.7：生图 API 模型动态列表（拉取 + 兜底）。

复刻自老 software D:\\剧本分镜助手\\server.py:1581-1603 `POST /api/list-models`：
- 端点：GET {base_url}/v1/models
- 头：Authorization: Bearer <api_key>
- 响应（OpenAI 兼容）：{"object": "list", "data": [{"id": "..."}, ...]}

复刻自老 software D:\\剧本分镜助手\\templates\\index.html:1837-1838
`refreshModelList` + `<select id="apiModel">`：
- 用户点 🔄 拉取，从生图 API base_url + api_key 拉模型列表
- 写入下拉框 + 已保存列表
- 失败时兜底 1 个 gpt-image-2-reverse（老 software 默认值，
  server.py:1803 default 模型）

跟 src/core/dreamina_models.py 的差异：
- FALLBACK 列表不同：生图 = ['gpt-image-2-reverse']（老 software 默认）
                       视频 = 4 个 seedance（生视频兜底）
- 复用 fetch_models 通用拉取逻辑
"""
from __future__ import annotations

import logging
from typing import List, Optional

log = logging.getLogger(__name__)


# v0.7.7：生图 model 兜底。复刻自老 software server.py:1803
# `_get_image_model` 默认值 'gpt-image-2-reverse'。
# 生图 model 跟视频 seedance 完全不同 —— 视频用 dreamina_models.FALLBACK_MODELS。
FALLBACK_IMAGE_MODELS: List[str] = [
    "gpt-image-2-reverse",
]


# 复用 dreamina_models.fetch_models —— 它是通用 OpenAI 兼容 /v1/models 拉取，
# 名字带 dreamina 是历史原因（最初给视频用），实际跟生图 API 端点格式一样。
from .dreamina_models import fetch_models as _fetch_models  # noqa: E402


def fetch_image_models(
    base_url: str,
    api_key: str,
    timeout: float = 15.0,
) -> List[str]:
    """v0.7.7：从生图 API 端点拉模型列表。

    直接复用 dreamina_models.fetch_models（通用 OpenAI 兼容 /v1/models 拉取）。
    """
    return _fetch_models(base_url, api_key, timeout=timeout)


def merge_with_image_fallback(
    fetched: Optional[List[str]] = None,
    saved: Optional[List[str]] = None,
) -> List[str]:
    """v0.7.7：合并「拉取 + 已保存 + 生图兜底」3 份去重。

    优先级：拉取的（最新） > 已保存的（用户保存过） > 兜底（gpt-image-2-reverse）
    跟 dreamina_models.merge_with_fallback 逻辑一样，只是兜底列表不同。
    """
    out: List[str] = []
    seen = set()
    for src in (fetched or [], saved or [], FALLBACK_IMAGE_MODELS):
        for m in src:
            if m and m not in seen:
                seen.add(m)
                out.append(m)
    return out
