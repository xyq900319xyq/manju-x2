"""v0.6.21：dreamina 模型动态列表（拉取 + 兜底）。

复刻自原软件 D:\\剧本分镜助手\\server.py:
- `POST /api/list-models` (server.py:1581-1603) — 代理 OpenAI 兼容 `/v1/models` 端点
- `_get_model_version` (server.py:2091-2099) — 4 个 seedance 模型兜底映射

dreamina 实际是个 OpenAI 兼容 API，所以可以 POST `/v1/models` 拿模型列表
（Authorization: Bearer <key>）。不同 dreamina 端点支持的模型不一样，运行时拉
比硬编码 4 个 seedance 更准。

失败降级：4 个 seedance 兜底（v0.6.21 之前 manju 只有这 4 个 hardcode）。
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

log = logging.getLogger(__name__)


# v0.6.21：4 个 seedance 兜底（任何时候至少给用户这 4 个选）
# 复刻自原软件 server.py:2091-2099 `_get_model_version`
FALLBACK_MODELS: List[str] = [
    "seedance2.0",
    "seedance2.0fast",
    "seedance2.0_vip",
    "seedance2.0fast_vip",
]


class DreaminaModelsError(Exception):
    """v0.6.21：拉取模型列表失败（HTTP 错 / 解析错 / 超时）。"""


def fetch_models(
    base_url: str,
    api_key: str,
    timeout: float = 15.0,
) -> List[str]:
    """v0.6.21：从 dreamina 端点拉模型列表。

    复刻自原软件 server.py:1581-1603 `POST /api/list-models`：
    - 端点：`{base_url}/v1/models`
    - 头：`Authorization: Bearer <api_key>`、`Content-Type: application/json`
    - 响应格式（OpenAI 兼容）：`{"object": "list", "data": [{"id": "..."}, ...]}`
    - 也支持直接 `["model1", "model2"]` 列表格式

    Args:
        base_url: 例如 `https://dreamina.jianying.com`，会自动补 `/v1/models`
        api_key: Bearer token
        timeout: 秒（默认 15）

    Returns:
        模型 id 列表（已去重 / 保持原顺序）

    Raises:
        DreaminaModelsError: 网络错 / 解析错 / HTTP 4xx/5xx
    """
    if not base_url or not api_key:
        raise DreaminaModelsError("base_url 和 api_key 都不能为空")

    # 复刻自 server.py:1588：拼 /v1/models 之前先剥掉 base_url 末尾可能存在的
    # /v1 / /v1/images/generations / /v1/chat/completions（防止拼成 /v1/v1/models）。
    # 老 software 是这么处理的 —— 用户填的 base_url 可能带也可能不带 /v1，
    # 两种都要能正确拼成 {域名}/v1/models。
    base = (
        base_url.rstrip("/")
        .replace("/v1/images/generations", "")
        .replace("/v1/chat/completions", "")
        .replace("/v1", "")
    )
    url = base + "/v1/models"

    req = urlrequest.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", 200)
    except HTTPError as e:
        raise DreaminaModelsError(
            f"HTTP {e.code} {e.reason}：{e.read().decode('utf-8', errors='replace')[:200]}"
        ) from e
    except (URLError, TimeoutError, OSError) as e:
        raise DreaminaModelsError(f"网络错误: {e}") from e

    if status >= 400:
        raise DreaminaModelsError(f"HTTP {status} {raw[:200]}")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise DreaminaModelsError(f"JSON 解析失败: {e}\n{raw[:200]}") from e

    # 多种解析格式
    models: List[str] = []
    if isinstance(data, list):
        # 直接 list[str]
        for item in data:
            if isinstance(item, str):
                models.append(item)
            elif isinstance(item, dict) and "id" in item:
                models.append(str(item["id"]))
    elif isinstance(data, dict):
        # OpenAI 格式
        if "data" in data and isinstance(data["data"], list):
            for item in data["data"]:
                if isinstance(item, dict) and "id" in item:
                    models.append(str(item["id"]))
                elif isinstance(item, str):
                    models.append(item)
        # 备选：单层 dict
        elif "models" in data and isinstance(data["models"], list):
            for item in data["models"]:
                if isinstance(item, str):
                    models.append(item)
                elif isinstance(item, dict) and "id" in item:
                    models.append(str(item["id"]))
    if not models:
        raise DreaminaModelsError(f"响应里找不到模型列表: {raw[:200]}")
    # 去重保序
    seen = set()
    uniq = []
    for m in models:
        if m not in seen:
            seen.add(m)
            uniq.append(m)
    return uniq


def merge_with_fallback(
    fetched: Optional[List[str]] = None,
    saved: Optional[List[str]] = None,
) -> List[str]:
    """v0.6.21：合并「拉取 + 已保存 + 兜底」3 份去重。

    优先级：拉取的（最新） > 已保存的（用户保存过） > 兜底（4 个 seedance）

    让用户下拉能选到**所有出现过的**模型，不会因为换端点丢选项。
    """
    out: List[str] = []
    seen = set()
    for src in (fetched or [], saved or [], FALLBACK_MODELS):
        for m in src:
            if m and m not in seen:
                seen.add(m)
                out.append(m)
    return out
