"""v1.0.0 用户版：DPAPI 加密存储用户 API Key。

设计要点（v1.0.0 用户版）：
- Windows DPAPI (win32crypt) 加密用户填的 API key，存到 `config/secrets.bin`
- 加密粒度：单 blob 装一个 JSON dict：{llm: {<config_id>: api_key}, image: {...},
  video: {...}, image_host: api_key}
- DPAPI 绑定当前 Windows 用户，其他用户/机器无法解密 → 配置文件可安全分享
- 非 Windows / 缺 pywin32 平台：fallback cryptography.Fernet + 机器特征
  派生 key（仅 dev 模式用）。EXE 打包走 Windows，无此分支
- hermes_api.json 里 api_key 字段保持空字符串 ""，运行时由 Config._merge_secrets
  从 secrets.bin 取出后注入到 self._data，不改写 hermes_api.json
- 用户清空某个 key 时，wizard 把那个字段设为 ""，下次保存时 secrets.bin 里
  相应字段为空字符串（不是删 key），解密后还是空，覆盖回去效果相同

v1.0.0【硬约束】：
- 不写兜底：DPAPI 失败直接抛 RuntimeError 让 wizard 报错给用户
- 不污染 hermes_api.json：所有 key 走 secrets.bin
- 不保存到日志：encrypt/decrypt 失败原因只走 logging.warning，**不**写 api_key 明文
"""
from __future__ import annotations

import base64
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger("manju.secrets")

# 平台 / 依赖检测
_IS_WINDOWS = sys.platform == "win32"
_HAS_PYWIN32 = False
_HAS_CRYPTOGRAPHY = False

if _IS_WINDOWS:
    try:
        import win32crypt  # type: ignore
        _HAS_PYWIN32 = True
    except ImportError:
        _HAS_PYWIN32 = False

try:
    from cryptography.fernet import Fernet, InvalidToken  # type: ignore
    from cryptography.hazmat.primitives import hashes  # type: ignore
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC  # type: ignore
    _HAS_CRYPTOGRAPHY = True
except ImportError:
    _HAS_CRYPTOGRAPHY = False

# secrets.bin 格式标识（区分 DPAPI blob vs Fernet token）
_MARKER_DPAPI = b"DPAPI1:"        # 后面是 DPAPI CryptProtectData 原始 bytes（base64 编码）
_MARKER_FERNET = b"FERNET1:"      # 后面是 Fernet token（base64-url 编码字符串的 utf-8 bytes）


# ---------- 公开 API ----------

def secrets_path(project_root: Path) -> Path:
    """secrets.bin 默认路径：`<project_root>/config/secrets.bin`"""
    return Path(project_root) / "config" / "secrets.bin"


def has_secrets(project_root: Path) -> bool:
    """是否存在 secrets.bin（且非空）。"""
    p = secrets_path(project_root)
    return p.exists() and p.stat().st_size > 0


def load_secrets(project_root: Path) -> Dict[str, Any]:
    """解密 secrets.bin，返回明文 dict。失败抛 RuntimeError。

    Returns:
        dict 结构：
        {
            "llm": {"deepseek": "sk-...", "agnes": "sk-...", "chuangwei": "..."},
            "image": {"default": "sk-..."},
            "video": {"default": "sk-..."},
            "image_host": "imgbb-key",
        }
        不存在的字段返回空 dict。
    """
    p = secrets_path(project_root)
    if not p.exists():
        return {"llm": {}, "image": {}, "video": {}, "image_host": ""}
    blob = p.read_bytes()
    if not blob:
        return {"llm": {}, "image": {}, "video": {}, "image_host": ""}
    plaintext = _decrypt(blob)
    try:
        data = json.loads(plaintext.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise RuntimeError(f"secrets.bin 内容不是合法 JSON: {e}") from e
    if not isinstance(data, dict):
        raise RuntimeError("secrets.bin 顶层必须是 dict")
    # 字段归一化（防旧版本结构不一致）
    return {
        "llm": dict(data.get("llm") or {}),
        "image": dict(data.get("image") or {}),
        "video": dict(data.get("video") or {}),
        "image_host": str(data.get("image_host") or ""),
    }


def save_secrets(project_root: Path, secrets: Dict[str, Any]) -> None:
    """加密并写 secrets.bin。失败抛 RuntimeError。

    原子写：先写 secrets.bin.tmp，再 os.replace 覆盖 secrets.bin。
    """
    p = secrets_path(project_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    # 归一化输入
    norm = {
        "llm": dict(secrets.get("llm") or {}),
        "image": dict(secrets.get("image") or {}),
        "video": dict(secrets.get("video") or {}),
        "image_host": str(secrets.get("image_host") or ""),
    }
    plaintext = json.dumps(norm, ensure_ascii=False, indent=2).encode("utf-8")
    blob = _encrypt(plaintext)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_bytes(blob)
    os.replace(tmp, p)
    log.info("save_secrets: 已写入 %s (%d 字节密文)", p, len(blob))


def clear_secrets(project_root: Path) -> None:
    """删除 secrets.bin（用户主动重置或卸载）。不存在不报错。"""
    p = secrets_path(project_root)
    if p.exists():
        p.unlink()
        log.info("clear_secrets: 已删除 %s", p)


# ---------- 内部加解密 ----------

def _encrypt(plaintext: bytes) -> bytes:
    """根据平台选择加密方式，返回带 marker 的密文 bytes。"""
    if _IS_WINDOWS and _HAS_PYWIN32:
        from win32crypt import CryptProtectData  # type: ignore
        import pywintypes  # type: ignore
        try:
            protected = CryptProtectData(
                plaintext,
                None,           # description
                None,           # optional entropy
                None,           # reserved
                None,           # prompt struct
                0,              # flags (0 = default: bind to current user)
            )
        except pywintypes.error as e:
            raise RuntimeError(f"DPAPI CryptProtectData 失败: {e}") from e
        return _MARKER_DPAPI + base64.b64encode(protected)
    # 非 Windows / 无 pywin32：fallback 到 Fernet（机器特征派生 key，仅 dev 用）
    if not _HAS_CRYPTOGRAPHY:
        raise RuntimeError(
            "无 DPAPI 也无 cryptography 库：无法加密 secrets.bin。"
            "请安装 pywin32 (Windows) 或 cryptography (跨平台)。"
        )
    key = _fernet_key()
    token = Fernet(key).encrypt(plaintext)
    return _MARKER_FERNET + token


def _decrypt(blob: bytes) -> bytes:
    """解密带 marker 的密文 bytes。"""
    if blob.startswith(_MARKER_DPAPI):
        return _decrypt_dpapi(blob[len(_MARKER_DPAPI):])
    if blob.startswith(_MARKER_FERNET):
        return _decrypt_fernet(blob[len(_MARKER_FERNET):])
    raise RuntimeError("secrets.bin 格式未知（既不是 DPAPI1 也不是 FERNET1）")


def _decrypt_dpapi(b64_payload: bytes) -> bytes:
    if not (_IS_WINDOWS and _HAS_PYWIN32):
        raise RuntimeError("secrets.bin 是 DPAPI 加密，但当前环境无 pywin32")
    from win32crypt import CryptUnprotectData  # type: ignore
    import pywintypes  # type: ignore
    try:
        protected = base64.b64decode(b64_payload)
    except Exception as e:
        raise RuntimeError(f"secrets.bin DPAPI base64 解码失败: {e}") from e
    try:
        # CryptUnprotectData(data, entropy, reserved, prompt_struct, flags) - 5 args
        # description 是返回值 (plaintext, description) tuple 的一部分
        result = CryptUnprotectData(protected, None, None, None, 0)
    except pywintypes.error as e:
        raise RuntimeError(
            f"DPAPI CryptUnprotectData 失败: {e}。"
            "常见原因：secrets.bin 在别的 Windows 账号下加密，"
            "或在别的机器上生成。"
        ) from e
    # 返回值是 (description_str, plaintext_bytes) tuple
    # pywin32 实测：description 在前，plaintext 在后（与文档描述相反）
    if isinstance(result, tuple):
        plaintext = result[1]
    else:
        plaintext = result
    if not isinstance(plaintext, bytes):
        raise RuntimeError("DPAPI 解密返回非 bytes")
    return plaintext


def _decrypt_fernet(token: bytes) -> bytes:
    if not _HAS_CRYPTOGRAPHY:
        raise RuntimeError("secrets.bin 是 Fernet 加密，但 cryptography 未安装")
    key = _fernet_key()
    try:
        return Fernet(key).decrypt(token)
    except InvalidToken as e:
        raise RuntimeError(
            f"Fernet 解密失败: {e}（机器特征已变？旧 secrets.bin 不可读）"
        ) from e


def _fernet_key() -> bytes:
    """v1.0.0 用户版 dev fallback：从机器特征派生 Fernet key。

    注意：这不是真"跨用户"安全，只是"避免明文落盘"。EXE 打包走 Windows DPAPI。
    """
    # 收集机器特征（hostname + cpus + mac 拼接后 SHA256 → base64-url 32 字节）
    import hashlib
    import uuid
    parts: list[str] = []
    try:
        parts.append(os.uname().nodename)
    except Exception:
        try:
            import socket
            parts.append(socket.gethostname())
        except Exception:
            pass
    try:
        parts.append(str(uuid.getnode()))  # MAC 地址 int
    except Exception:
        pass
    if not parts:
        parts.append("manju-fallback-static-salt")
    raw = "|".join(parts).encode("utf-8")
    digest = hashlib.sha256(raw).digest()
    # Fernet key = base64-url(32 bytes)
    return base64.urlsafe_b64encode(digest)


# ---------- 配置注入 ----------

def merge_secrets_into_config(config_data: Dict[str, Any], secrets: Dict[str, Any]) -> int:
    """v1.0.0 用户版：把 secrets.bin 解密后的 key 合并到 Config._data 里。

    字段映射：
    - secrets["llm"][<config_id>] → config_data["configs"][i].api_key（按 id 匹配）
    - secrets["image"][<config_id>] → config_data["image_configs"][i].api_key
    - secrets["video"][<config_id>] → config_data["video_api_configs"][i].api_key
    - secrets["image_host"] → config_data["image_host_api_key"]

    Returns:
        实际注入的非空 key 数量（仅统计 api_key 字段）。
    """
    n = 0
    llm_map = dict(secrets.get("llm") or {})
    for c in config_data.get("configs", []) or []:
        cid = c.get("id")
        if not cid:
            continue
        v = llm_map.get(cid)
        if v:  # 仅注入非空 key
            c["api_key"] = str(v).strip()
            n += 1
    image_map = dict(secrets.get("image") or {})
    for c in config_data.get("image_configs", []) or []:
        cid = c.get("id")
        if not cid:
            continue
        v = image_map.get(cid)
        if v:
            c["api_key"] = str(v).strip()
            n += 1
    video_map = dict(secrets.get("video") or {})
    for c in config_data.get("video_api_configs", []) or []:
        cid = c.get("id")
        if not cid:
            continue
        v = video_map.get(cid)
        if v:
            c["api_key"] = str(v).strip()
            n += 1
    img_host = str(secrets.get("image_host") or "").strip()
    if img_host:
        config_data["image_host_api_key"] = img_host
        n += 1
    return n
