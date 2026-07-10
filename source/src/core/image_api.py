"""v0.7.7：生图 API 调用器（OpenAI 兼容 /v1/images/generations）。

复刻自老 software D:\\剧本分镜助手\\server.py:1795-1946 `POST /api/generate-image`：
- 端点：POST {base_url}/v1/images/generations（OpenAI 兼容）
- 复用 active config 的 base_url + api_key（生图和 LLM 是同一个 provider）
- model：默认 gpt-image-2-reverse（复刻自 server.py:1803）
- 支持 resolution (1K/2K/4K) + ratio (1:1/16:9/9:16) + negative + reference images
- 响应处理（复刻自 server.py:1849-1946）：
  1. 二进制（image/* 或 PNG/JPG 头）→ 直接保存
  2. JSON `{"data": [{"b64_json": "..."}]}` → base64 解码保存
  3. JSON `{"data": [{"url": "..."}]}` → 下载 URL 保存
  4. data URI（data:image/png;base64,xxx）→ base64 解码保存
  5. 顶层 b64_json / image / url 字段同样处理

v0.7.8：参考图走图生图模式
- 有 ref_images：POST {base_url}/v1/images/edits + multipart/form-data
  （OpenAI edits 端点认 image[]，generations 不认 image 字段被忽略）
- 没 ref_images：保持 POST {base_url}/v1/images/generations + JSON
- ref_images: data URL 数组（"data:image/png;base64,xxx"），base64 解码后当文件上传
- 最多 16 张（跟老 software 限制一致）

约束：跟生图/生视频无关，不 import 也不调 D:\\剧本分镜助手\\ 任何代码；
     复刻自 server.py:1795-1946，逻辑手工翻译。
"""
from __future__ import annotations

import base64
import logging
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

log = logging.getLogger("manju.image_api")


@dataclass
class ImageApiResult:
    """v0.7.7：单次生图结果。"""
    exit_code: int           # 0=ok; -1=cancelled; -2=timeout; -3=error
    image_path: str          # 成功时 = 输出文件绝对路径
    error: str               # 失败原因
    log_text: str            # 调试日志（请求体/响应摘要）


class ImageApiRunner:
    """v0.7.7：调一次 /v1/images/generations 生图。

    用法：
        runner = ImageApiRunner(base_url, api_key, model="gpt-image-2-reverse")
        result = runner.run(
            prompt="...",
            output=Path("xxx.png"),
            negative="...",
            resolution="2K",
            ratio="1:1",
            cancel_check=lambda: False,
            timeout=600,
            on_output=lambda line: ...,
        )

    行为对齐老 software server.py:1795-1946：
    1. 算 size = "{w*scale}x{h*scale}"（resolution → 1024/2048/4096 base）
    2. 转换 prompt 里 `图N` / `参考图N` 引用 → `[imageN]`（server.py:1827-1828）
    3. POST /v1/images/generations with model/prompt/n/size/quality
    4. 处理响应：二进制 / b64_json / url / data URI
    5. 写到 output 路径
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str = "gpt-image-2-reverse",
    ) -> None:
        self._base_url = (base_url or "").rstrip("/")
        self._api_key = (api_key or "").strip()
        self._model = (model or "gpt-image-2-reverse").strip()

    @property
    def endpoint(self) -> str:
        """POST 端点（默认纯文生图）：{base_url}/v1/images/generations（自动剥掉 /v1 防止重复）。

        v0.7.8：有参考图时改用 endpoint_edits()（/v1/images/edits + multipart）。
        """
        return self._endpoint_for(generations=True)

    def _endpoint_for(self, generations: bool) -> str:
        """v0.7.8：算最终 endpoint。

        - generations=True  → /v1/images/generations（纯文生图，JSON body）
        - generations=False → /v1/images/edits（图生图，multipart body）
        老 software server.py:1822 行为复刻：剥掉 /v1 防重复。
        """
        if not self._base_url:
            return ""
        b = self._base_url
        for tail in (
            "/v1/images/generations",
            "/v1/images/edits",
            "/v1/images/variations",
            "/v1/chat/completions",
            "/v1",
        ):
            if b.endswith(tail):
                b = b[: -len(tail)]
                break
        tail_path = "/v1/images/generations" if generations else "/v1/images/edits"
        return b + tail_path

    def _calc_size(self, ratio: str, resolution: str) -> str:
        """复刻自 server.py:1811-1819：ratio + resolution → "WxH" 像素。"""
        parts = (ratio or "1:1").split(":")
        if len(parts) != 2:
            return "1024x1024"
        try:
            w, h = int(parts[0]), int(parts[1])
        except ValueError:
            return "1024x1024"
        base = {"1K": 1024, "2K": 2048, "4K": 4096}.get(resolution, 2048)
        m = max(w, h)
        scale = base / m
        return f"{int(w * scale)}x{int(h * scale)}"

    def _convert_prompt_refs(self, prompt: str) -> str:
        """复刻自 server.py:1827-1828：图1/参考图1 → [image1]（API 端识别）。"""
        if not prompt:
            return ""
        out = re.sub(r"图(\d+)", r"[image\1]", prompt)
        out = re.sub(r"参考图\s*(\d+)", r"[image\1]", out)
        return out

    def _build_body(self, prompt: str, negative: str, size: str, ref_images: Optional[List[str]] = None) -> dict:
        """构造请求体。"""
        body = {
            "model": self._model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": "high",
        }
        if negative:
            # OpenAI images API 没有 negative_prompt 字段；按老 software 行为
            # 也不传 negative，负向词已经写在主 prompt 的「负向提示词」段里
            # （asset_parser 抽出来的）。这里只是占位防止 IDE 警告。
            pass
        if ref_images:
            body["image"] = list(ref_images)[:16]
        return body

    # 复刻自老 software D:\剧本分镜助手\templates\index.html:1255
    # 硬编码的负向提示词，老 software 直接传，**没暴露给用户配置**：
    # `'blurry, low quality, watermark, text, cropped, 动漫风格, Q版, 抽象艺术, 油画厚涂'`
    # v0.7.7 第一次我做了 `image_default_negative` 字段让用户配 — user 纠正
    # 说"老软件有负向提示词吗?"，查实老 software 没暴露，是硬编码，复刻。
    DEFAULT_NEGATIVE = "blurry, low quality, watermark, text, cropped, 动漫风格, Q版, 抽象艺术, 油画厚涂"

    def _http_post(self, url: str, body: dict, timeout: float) -> tuple:
        """POST JSON，返回 (status, content_bytes, content_type, resp_text)。

        v0.7.7 重打 22 (user 反馈创维 524 + 复刻老 software server.py:1842)：
        老 software 用 `requests.post(..., verify=False)` 关闭 SSL 验证。
        我们之前用 urllib 默认 verify=True，创维 / 部分反代用的自签证书会被拒。
        用 `ssl._create_unverified_context()` 包一个 context 给 urlopen。
        """
        import ssl
        data = json_dumps(body).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        ctx = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read()
                return (resp.status, raw, resp.headers.get("Content-Type", ""), raw.decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            raw = e.read() if hasattr(e, "read") else b""
            return (e.code, raw, e.headers.get("Content-Type", "") if e.headers else "", raw.decode("utf-8", errors="replace"))
        except urllib.error.URLError as e:
            raise RuntimeError(f"生图 API 网络错误: {e.reason}") from e

    def _http_post_multipart(
        self,
        url: str,
        fields: dict,
        files: list,
        timeout: float,
    ) -> tuple:
        """v0.7.8：POST multipart/form-data（图生图 /v1/images/edits 用）。

        Args:
            url: POST URL（edits 端点）
            fields: 普通 form 字段 dict,例 {"model": "xxx", "prompt": "yyy", "n": "1", "size": "1024x1024"}
            files: [(field_name, filename, content_bytes, mime), ...]
                   例 [("image[]", "ref0.png", b"...", "image/png"), ...]
        Returns:
            (status, content_bytes, content_type, resp_text)
        """
        import ssl
        import uuid

        boundary = "----manju" + uuid.uuid4().hex
        body = bytearray()
        # 普通字段
        for k, v in (fields or {}).items():
            body += f"--{boundary}\r\n".encode("ascii")
            body += f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8")
            body += str(v).encode("utf-8")
            body += b"\r\n"
        # 文件字段
        for f in files or []:
            fname, ctype, fbody = f
            body += f"--{boundary}\r\n".encode("ascii")
            body += (
                f'Content-Disposition: form-data; name="image[]"; filename="{fname}"\r\n'
            ).encode("utf-8")
            body += f"Content-Type: {ctype}\r\n\r\n".encode("ascii")
            body += fbody
            body += b"\r\n"
        body += f"--{boundary}--\r\n".encode("ascii")

        req = urllib.request.Request(
            url,
            data=bytes(body),
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "Authorization": f"Bearer {self._api_key}",
            },
            method="POST",
        )
        ctx = ssl._create_unverified_context()
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                raw = resp.read()
                return (resp.status, raw, resp.headers.get("Content-Type", ""), raw.decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            raw = e.read() if hasattr(e, "read") else b""
            return (e.code, raw, e.headers.get("Content-Type", "") if e.headers else "", raw.decode("utf-8", errors="replace"))
        except urllib.error.URLError as e:
            raise RuntimeError(f"生图 API 网络错误: {e.reason}") from e

    @staticmethod
    def _data_url_to_mime_and_bytes(data_url: str) -> tuple:
        """v0.7.8：data URL → (filename, mime, bytes)。

        输入 "data:image/png;base64,xxxx" → ("ref0.png", "image/png", b"...")
        失败返回 ("", "application/octet-stream", b"")
        """
        mime = "image/png"
        b64 = data_url
        if data_url.startswith("data:"):
            head, _, b64 = data_url.partition(",")
            # data:image/png;base64
            if ";" in head:
                mime = head[5:].split(";", 1)[0] or "image/png"
            else:
                mime = head[5:] or "image/png"
        try:
            raw = base64.b64decode(b64, validate=False)
        except Exception:
            return ("", "application/octet-stream", b"")
        ext_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/webp": ".webp",
            "image/bmp": ".bmp",
            "image/gif": ".gif",
        }
        ext = ext_map.get(mime, ".png")
        return (f"ref{abs(hash(data_url)) % 100000}{ext}", mime, raw)

    def _save_response(self, resp_content: bytes, content_type: str, output: Path) -> bool:
        """处理 4 种响应格式（复刻自 server.py:1849-1946）。返回是否成功落盘。"""
        output.parent.mkdir(parents=True, exist_ok=True)
        ext = ".png"

        # 格式 1: 二进制图（image/* 或 PNG/JPG 头）→ 直接写
        if "image/" in content_type or (
            len(resp_content) > 500
            and resp_content[:4] in (b"\x89PNG", b"\xff\xd8", b"RIFF")
        ):
            if resp_content[:4] == b"\xff\xd8":
                ext = ".jpg"
            target = output.with_suffix(ext)
            target.write_bytes(resp_content)
            log.info("生图: 二进制保存 %s (%d bytes)", target, len(resp_content))
            return True

        # 格式 2/3/4: JSON 解析
        result = None
        try:
            result = json_loads(resp_content.decode("utf-8", errors="replace"))
        except Exception:
            result = None

        image_data: Optional[bytes] = None
        image_url: Optional[str] = None

        if isinstance(result, dict):
            data_list = result.get("data", [])
            if isinstance(data_list, list) and data_list:
                first = data_list[0]
                if isinstance(first, dict):
                    b64 = first.get("b64_json", "")
                    url = first.get("url", "")
                    if b64:
                        try:
                            image_data = base64.b64decode(b64)
                        except Exception as e:
                            log.warning("生图: b64_json 解码失败: %s", e)
                    elif url:
                        if url.startswith("data:"):
                            b64_part = url.split(",", 1)[-1] if "," in url else url
                            try:
                                image_data = base64.b64decode(b64_part)
                            except Exception as e:
                                log.warning("生图: data URI 解码失败: %s", e)
                        else:
                            image_url = url
            # 顶层 b64_json / image 兜底（某些 provider 不走 data[]）
            for k in ("b64_json", "image"):
                v = result.get(k, "")
                if v and not image_data:
                    try:
                        image_data = base64.b64decode(v)
                    except Exception as b64_e:
                        # v1.1.5【C10 修复】:之前静默吞,b64 decode 失败时
                        # user 看到的是"生图 API 返回 200 但图片空"且不知道为啥。
                        # 加 log.debug 留痕迹(不走 exception 避免主日志噪音)。
                        log.debug("base64.b64decode(%s) failed: %s", k, b64_e)
            if not image_url:
                image_url = result.get("url") or result.get("image_url") or ""

        # 格式 4 fallback: 整个响应体就是 base64 字符串
        if not image_data and not image_url:
            text = resp_content.decode("utf-8", errors="replace").strip()
            if len(text) > 100 and not text.startswith("{") and not text.startswith("<"):
                try:
                    image_data = base64.b64decode(text)
                except Exception as b64_e:
                    # v1.1.5【C10 修复】:同 above,留 log.debug
                    log.debug("format 4 base64 fallback failed: %s", b64_e)

        # 落盘
        if image_data and len(image_data) > 100:
            target = output.with_suffix(ext)
            target.write_bytes(image_data)
            log.info("生图: base64 保存 %s (%d bytes)", target, len(image_data))
            return True

        if image_url:
            try:
                with urllib.request.urlopen(image_url, timeout=120) as r:
                    content = r.read()
                if len(content) > 100:
                    target = output.with_suffix(ext)
                    target.write_bytes(content)
                    log.info("生图: URL 保存 %s (%d bytes)", target, len(content))
                    return True
            except Exception as e:
                log.warning("生图: URL 下载失败: %s", e)
                return False

        log.warning(
            "生图: 未能提取图片! result keys: %s",
            list(result.keys()) if isinstance(result, dict) else "not-dict",
        )
        return False

    def run(
        self,
        prompt: str,
        output: Path,
        negative: str = "",
        name: str = "asset",
        cancel_check: Callable[[], bool] = lambda: False,
        timeout: int = 600,
        on_output: Optional[Callable[[str], None]] = None,
        resolution: str = "2K",
        ratio: str = "1:1",
        ref_images: Optional[List[str]] = None,
    ) -> ImageApiResult:
        """v0.7.7：跑一次生图。

        Args:
            prompt: 完整 prompt（已含负向提示词段；v0.7.7 末段拼入 ImageApiRunner.DEFAULT_NEGATIVE）
            output: 输出文件路径（.png / .jpg 自动判断）
            negative: 已弃用（v0.7.7）；保留参数是为向后兼容调用方，但实际不再使用 DEFAULT_NEGATIVE
            name: 资产名（仅日志）
            cancel_check: callable() -> bool，外部取消
            timeout: 秒
            on_output: 日志回调
            resolution: 1K / 2K / 4K
            ratio: 1:1 / 16:9 / 9:16 / ...
            ref_images: 参考图 URL 列表
        """
        log_lines: List[str] = []

        def emit(line: str) -> None:
            log_lines.append(line)
            if on_output:
                try:
                    on_output(line)
                except Exception as emit_e:
                    # v1.1.5【C10 修复】:之前静默吞,on_output 抛错(比如 UI
                    # 已关闭)时 user 看不到生成进度。加 log.debug 留痕迹。
                    log.debug("on_output callback failed: %s", emit_e)
            log.info(line)

        # v0.7.7 重打 22 (user 反馈创维 524)：
        # 复刻老 software server.py:1821：`full_prompt = prompt`（不拼负向词）。
        # 之前我们拼了 `[负向提示词]\n...` 段，prompt 末尾多个英文 marker +
        # 中文 + 9 个英文负向词会改变 prompt 结构，可能让创维的 upstream
        # (OpenAI) 拒掉或判 invalid，导致创维返回 524 兜底超时。
        # 老 software 把负向词做成 modal 里的"负向提示词"textarea 单独让用户填
        # （templates/index.html），不在 client 端硬拼。
        # 我们的 _run_one_asset_image (generators.py:764) 拿到的 prompt
        # 已经是从 db 提取的"中文指令词"段，干净，照老 software 透传。
        full_prompt = self._convert_prompt_refs(prompt)
        # 屏蔽 caller 传的 negative（保持参数向后兼容，但实际不使用）
        _ = negative

        try:
            if not self._base_url:
                return ImageApiResult(
                    exit_code=-3,
                    image_path="",
                    error="image_base_url 为空（请在 🔑 API 配置 tab 配 active config 的 base_url）",
                    log_text="\n".join(log_lines),
                )
            if not self._api_key:
                return ImageApiResult(
                    exit_code=-3,
                    image_path="",
                    error="image_api_key 为空（请在 🔑 API 配置 tab 配 active config 的 api_key）",
                    log_text="\n".join(log_lines),
                )

            if cancel_check():
                return ImageApiResult(-1, "", "已取消", "\n".join(log_lines))

            full_prompt = self._convert_prompt_refs(prompt)
            size = self._calc_size(ratio, resolution)

            # v0.7.8：判断走哪条路径
            #   - 有 ref_images  → /v1/images/edits (multipart) 图生图
            #   - 无 ref_images  → /v1/images/generations (JSON) 纯文生图
            # 老 software 把 ref_images 塞到 generations 端点的 JSON body 里
            # (server.py:1837-1839 body["image"]=ref_images),generations 端点
            # 本来就不认 image 字段(它是纯文生图端点),创维/反代默默忽略,参考图
            # 完全没用 — user 反馈过这个问题。
            # 修法:切到 OpenAI 官方的 edits 端点(认 image[] 文件)。
            has_refs = bool(ref_images)
            url = self._endpoint_for(generations=not has_refs)
            mode = "图生图" if has_refs else "文生图"

            emit(f"[生图] {name} → {mode} POST {url}")
            emit(f"[生图] model={self._model} size={size} ratio={ratio} resolution={resolution} refs={len(ref_images) if ref_images else 0}")

            t0 = time.time()
            try:
                if has_refs:
                    # edits: multipart/form-data with image[] files
                    files = []
                    for ref in (ref_images or [])[:16]:
                        fname, mime, raw = self._data_url_to_mime_and_bytes(ref)
                        if not raw:
                            emit(f"[生图] 跳过空参考图: {fname}")
                            continue
                        files.append((fname, mime, raw))
                    if not files:
                        return ImageApiResult(
                            -3,
                            "",
                            "ref_images 全是空,没法图生图,请检查参考图数据",
                            "\n".join(log_lines),
                        )
                    fields = {
                        "model": self._model,
                        "prompt": full_prompt,
                        "n": "1",
                        "size": size,
                        "response_format": "b64_json",
                    }
                    status, content, ctype, text = self._http_post_multipart(
                        url, fields, files, timeout=float(timeout)
                    )
                else:
                    # generations: JSON
                    body = self._build_body(full_prompt, negative, size, ref_images)
                    status, content, ctype, text = self._http_post(url, body, timeout=float(timeout))
            except Exception as e:
                return ImageApiResult(-3, "", f"网络错误: {e}", "\n".join(log_lines))

            dt = time.time() - t0
            emit(f"[生图] HTTP {status} content-type={ctype} size={len(content)} dt={dt:.1f}s")

            if cancel_check():
                return ImageApiResult(-1, "", "已取消", "\n".join(log_lines))

            if status != 200:
                snippet = text[:500] if text else "<empty>"
                return ImageApiResult(
                    -3,
                    "",
                    f"API 返回 {status}: {snippet}",
                    "\n".join(log_lines),
                )

            ok = self._save_response(content, ctype, output)
            if not ok:
                return ImageApiResult(
                    -3,
                    "",
                    "响应里没找到图片数据（b64_json / url / data URI 都失败）",
                    "\n".join(log_lines),
                )

            # 落盘实际扩展名（_save_response 可能改成 .jpg）
            actual = output
            if output.with_suffix(".jpg").exists() and not output.exists():
                actual = output.with_suffix(".jpg")
            emit(f"[生图] ✓ {name} → {actual.name}")
            return ImageApiResult(0, str(actual), "", "\n".join(log_lines))

        except Exception as e:
            log.exception("ImageApiRunner.run failed")
            return ImageApiResult(-3, "", f"异常: {e}", "\n".join(log_lines))


# ---------- v0.7.7 小工具：json dumps/loads（不引第三方库） ----------

def json_dumps(obj) -> str:
    import json as _json
    return _json.dumps(obj, ensure_ascii=False)


def json_loads(text: str):
    import json as _json
    return _json.loads(text)
