"""配置加载：读 D:\\漫剧助手\\config\\hermes_api.json。

约束：与 D:\\剧本分镜助手\\ 无**运行时**依赖（不 import 也不调它的代码）；
     允许读它的代码作为参考并手工翻译逻辑到本目录，所有复刻必须标
     "复刻自 server.py:XXX"或"复刻自 templates/index.html:XXX"。
     所有配置复制到本目录，原软件配置文件不修改。
hermes.exe 是外部黑盒工具，仅通过 subprocess 调，路径在 config 里可改。
"""
import json
import logging
import os
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List

log = logging.getLogger("manju.config")


def _strip_v1_suffix(base_url: str) -> str:
    """v0.7.8.2:base_url 规范化——剥掉可能的 /v1/... 后缀,防止 hermes / image_api 拼出
    /v1/v1/chat/completions 这种重复 v1 的 URL。

    复刻老 software D:\\剧本分镜助手\\server.py:1588 + server.py:1822 + image_api.py:101-110
    的去重逻辑（"API URL 拼接前必须移除现有 /v1 后缀" hard constraint）。
    """
    if not base_url:
        return base_url
    b = base_url.rstrip("/")
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
    return b


def _ensure_v1_suffix(base_url: str) -> str:
    """v0.7.8.23:确保 base_url 以 /v1 结尾,给 hermes profile 用。

    hermes v0.17 内部 proxy (hermes_cli/proxy/server.py:238) 路由是
    `/v1/{tail:.*}`,tail 是 `chat/completions`(不含 /v1)。
    拼装 (server.py:136) `upstream_url = f"{base_url.rstrip('/')}{rel_path}"`,
    要求 base_url 以 /v1 结尾才能拼对。
    配套:先用 `_strip_v1_suffix` 剥掉所有 /v1* 尾巴(防止用户写
    `https://x.com/v1/v1/chat` 这种重复),再 `_ensure_v1_suffix` 补一个 /v1。
    """
    if not base_url:
        return base_url
    b = base_url.rstrip("/")
    if b.endswith("/v1"):
        return b
    return b + "/v1"


DEFAULT_CONFIG_PATH = Path("config/hermes_api.json")


class ConfigError(Exception):
    pass


class Config:
    """应用配置（线程安全单例）。"""

    _instance: Optional["Config"] = None
    _lock = threading.Lock()

    def __init__(self, data: Dict[str, Any], path: Path, project_root: Optional[Path] = None) -> None:
        self._data = data
        self._path = path
        # 默认：相对 PyInstaller _internal → 会算到 EXE 目录
        # 显式传 project_root：相对真正的项目根（D:\漫剧助手\）
        self._project_root = project_root or Path(__file__).resolve().parent.parent.parent
        # v0.7.7：生图 API 多 config 模式（仿 LLM `configs/active` 结构）
        # 检测到老结构（顶层 image_api_url 有 + image_configs 没有）自动迁移
        # 成单条 image_configs + active_image_config。
        self._migrate_legacy_image_config()
        # v0.7.8.38：视频 API 多 config 模式（仿生图 API + LLM）。
        # 老结构（顶层 video_api_url 等字段）→ 迁移到 video_configs[0]。
        self._migrate_legacy_video_api_config()

    @property
    def project_root(self) -> Path:
        """项目根目录（D:\\漫剧助手\\）。**v0.6.15** AssetExtractTask 用
        这个写 hermes 临时输出文件（不让 LLM 写到 hermes profile 领域，
        写到 manju 自己的 data 目录）。
        """
        return self._project_root

    # ---------- 单例 ----------
    @classmethod
    def get(cls, config_path: Optional[Path] = None, project_root: Optional[Path] = None) -> "Config":
        """获取（或加载）配置单例。

        v0.7.7 重打 10：加 project_root 参数，让 main.py 把"真正的项目根"
        （D:\\漫剧助手）显式传进来，避免 EXE 模式下从 __file__ 算成
        `D:\\漫剧助手\\dist\\漫剧助手X-1`（PyInstaller 把 .py 复制到
        _internal/core/，.parent.parent.parent 回到 dist/漫剧助手X-1，
        不是 _internal/），导致 outputs 写到 `dist\\漫剧助手X-1\\outputs`
        而不是 `D:\\漫剧助手\\outputs`。
        修法：EXE 启动时 main.py 已经用 _find_project_root() 找到
        `D:\\漫剧助手`（因为 config/hermes_api.json 在 D 盘根），传进来
        就跟源码模式一致了。
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls.load(config_path, project_root=project_root)
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """测试用：重置单例。"""
        with cls._lock:
            cls._instance = None

    @classmethod
    def reload(cls, config_path: Optional[Path] = None, project_root: Optional[Path] = None) -> "Config":
        """测试 / 设置面板用：重新读盘。

        v0.7.8.26【关键修复】原地更新现有 instance 的内部状态，**不**创建
        新对象替换 `cls._instance`。
        根因：StoryboardTask / VideoPromptTask 等 Task 在 __init__ 时
        `self._config = Config.get()` 把当前单例引用存到实例字段。旧 reload
        替换 `cls._instance` 时,这些 self._config 字段还指向**旧对象**,
        self._data["active"] 仍是改动前的值(用户改完 active 看起来"没生效")。
        原地更新 `_data` / `_path` 后,所有 self._config 引用看到的都是
        最新的 active/model/base_url/api_key。
        """
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls.load(config_path, project_root=project_root)
                return cls._instance
            if project_root is None:
                project_root = cls._instance._project_root
            # 走 load 拿一份新 data,但不替换 instance 本身
            new_instance = cls.load(config_path, project_root=project_root)
            cls._instance._data = new_instance._data
            cls._instance._path = new_instance._path
            cls._instance._project_root = new_instance._project_root
            # 重新跑 image / video 老结构迁移(新 json 可能改了字段)
            cls._instance._migrate_legacy_image_config()
            cls._instance._migrate_legacy_video_api_config()
            return cls._instance

    # ---------- 加载 ----------
    @classmethod
    def load(cls, config_path: Optional[Path] = None, project_root: Optional[Path] = None) -> "Config":
        path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        if not path.is_absolute():
            # 相对路径：相对项目根
            path = Path(__file__).resolve().parent.parent.parent / path
        if not path.exists():
            raise ConfigError(f"配置文件不存在: {path}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ConfigError(f"配置文件 JSON 解析失败: {e}") from e
        # 必填字段校验
        for key in ("hermes_exe", "configs", "active", "profiles"):
            if key not in data:
                raise ConfigError(f"配置文件缺少必填字段: {key}")
        hermes_exe = Path(data["hermes_exe"])
        if not hermes_exe.exists():
            # 不抛错，启动后再提示
            pass
        # v1.0.0 用户版：合并 secrets.bin 里的 API key 到运行时 _data
        # —— 不修改 hermes_api.json，只在内存里覆盖 api_key 字段
        inst = cls(data, path, project_root=project_root)
        try:
            from core import secret_store
            # 自动从 path 推 project_root（兼容 Config.get() 不传 project_root 的场景）
            effective_root = project_root if project_root is not None else path.parent.parent
            if secret_store.has_secrets(effective_root):
                secrets = secret_store.load_secrets(effective_root)
                n = secret_store.merge_secrets_into_config(data, secrets)
                if n:
                    log.info("Config: 从 secrets.bin 合并了 %d 个 api_key（不写回 hermes_api.json）", n)
        except Exception as e:  # noqa: BLE001
            log.warning("Config: 合并 secrets.bin 失败: %s", e)
        return inst

    # ---------- 访问 ----------
    @property
    def path(self) -> Path:
        return self._path

    @property
    def hermes_exe(self) -> str:
        return self._data["hermes_exe"]

    @property
    def hermes_exe_path(self) -> Path:
        return Path(self._data["hermes_exe"])

    @property
    def dreamina_exe(self) -> str:
        return self._data.get("dreamina_exe", "")

    @property
    def dreamina_exe_path(self) -> Optional[Path]:
        s = self.dreamina_exe
        return Path(s) if s else None

    @property
    def web_video(self) -> Dict[str, Any]:
        """v0.6.22：web 视频生成配置（用户配的命令模板）。

        Returns:
            dict: {"cmd_template": str, "timeout_seconds": int}

        复刻原软件 D:\\剧本分镜助手\\server.py:1983-1986 从 settings 读
        `videoApiUrl`。manju 改成更通用的命令模板（用户可接任何 videoApiUrl
        / agent-browser / 自定义 python 脚本）。
        """
        return self._data.get("web_video", {}) or {}

    @property
    def web_video_cmd_template(self) -> str:
        return str(self.web_video.get("cmd_template", "") or "").strip()

    @property
    def web_video_timeout(self) -> int:
        return int(self.web_video.get("timeout_seconds", 600) or 600)

    @property
    def dreamina_image_args(self) -> list:
        return list(self._data.get("dreamina_image_args", []))

    @property
    def dreamina_image_poll_seconds(self) -> float:
        return float(self._data.get("dreamina_image_poll_seconds", 2))

    @property
    def dreamina_image_max_wait(self) -> int:
        return int(self._data.get("dreamina_image_max_wait", 600))

    @property
    def dreamina_default_negative(self) -> str:
        return self._data.get(
            "dreamina_default_negative",
            "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, jpeg artifacts, signature, watermark, username, blurry",
        )

    # ---------- 视频生成（dreamina video 模式）----------

    @property
    def dreamina_video_args(self) -> list:
        """视频生成的命令模板；空列表表示尚未在 config 里配视频模板。"""
        return list(self._data.get("dreamina_video_args", []))

    @property
    def dreamina_video_poll_seconds(self) -> float:
        return float(self._data.get("dreamina_video_poll_seconds", 2))

    @property
    def dreamina_video_max_wait(self) -> int:
        return int(self._data.get("dreamina_video_max_wait", 1800))

    @property
    def dreamina_default_video_negative(self) -> str:
        return self._data.get(
            "dreamina_default_video_negative",
            "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, jpeg artifacts, signature, watermark, username, blurry, flicker, jitter",
        )

    @property
    def video_output_extension(self) -> str:
        return self._data.get("video_output_extension", ".mp4")

    # ---------- v0.7.8.41【dreamina 模型列表】----------
    # 复刻自老 software D:\剧本分镜助手\templates\index.html:1761-1789
    # dreamina_model_options。v0.7.8.39 在 main_window.py 用了这个属性但
    # Config 没暴露 → 报 "'Config' object has no attribute 'dreamina_models'"。
    # 无兜底：缺则空 list，**不**塞任何默认模型。
    @property
    def dreamina_models(self) -> list:
        v = self._data.get("dreamina_models", []) or []
        return list(v)

    @property
    def dreamina_models_active(self) -> str:
        """v0.7.8.41：当前选中的 dreamina 模型（无兜底，缺则空字符串）。"""
        return str(self._data.get("dreamina_models_active", "") or "").strip()

    # ---------- v0.7.7 生图 API（OpenAI 兼容 /v1/images/generations） ----------
    # 多 config 模式（仿 LLM `configs/active`）：image_configs: [{id, name, base_url,
    # api_key, model, resolution, ratio, timeout, saved_models}, ...] + active_image_config
    # 复刻自老 software D:\剧本分镜助手\templates\index.html:1824-1855
    # showApiSettingsModal 5 字段 form（apiKey/apiUrl/model/resolution/ratio），但用
    # 列表 + 切激活按钮升级成多 config，跟 LLM 一样支持多 provider 快速切换。
    # 复刻 server.py:1795-1946 `/api/generate-image` POST {base_url}/v1/images/generations
    # + server.py:1803 model 默认值 `gpt-image-2-reverse`。

    @property
    def image_configs(self) -> List[Dict[str, Any]]:
        """生图 API 多 config 列表（仿 LLM `configs` 字段结构）。

        每条：{id, name, base_url, api_key, model, resolution, ratio, timeout, saved_models}
        """
        return list(self._data.get("image_configs", []) or [])

    @property
    def active_image_config_id(self) -> str:
        return str(self._data.get("active_image_config", "") or "")

    def _active_image_config_field(self, key: str, default: Any) -> Any:
        """从活跃 image_config 读字段；找不到则回退到顶层旧字段（兼容过渡）。

        逻辑：
        1) 在 image_configs 里找 active 指向的那条 → 读字段
        2) active 命中但字段为空 → 不再做 fallback hack（避免 v0.7.7 重打 11
           那种"base_url 不在 LLM configs 列表里就 fallback"自作主张逻辑）
        3) 找不到 active 或 image_configs 空 → 回退到顶层 image_api_url 等旧字段
        """
        for c in self.image_configs:
            if c.get("id") == self.active_image_config_id:
                v = c.get(key)
                if v not in (None, ""):
                    return v
                break
        # 兜底：顶层旧字段
        legacy_map = {
            "base_url": "image_api_url",
            "api_key": "image_api_key",
            "model": "image_model",
            "resolution": "image_resolution",
            "ratio": "image_ratio",
            "timeout": "image_timeout",
        }
        legacy_key = legacy_map.get(key, "")
        if legacy_key:
            v = self._data.get(legacy_key)
            if v not in (None, ""):
                return v
        return default

    def _migrate_legacy_image_config(self) -> None:
        """v0.7.7：把顶层 image_api_url 等老字段迁移到 image_configs[0]。

        老结构：
            image_api_url / image_api_key / image_model / image_resolution /
            image_ratio / image_timeout / image_saved_models
        新结构：
            image_configs: [{id, name, base_url, api_key, model, ...}]
            active_image_config: "id"
        """
        if self._data.get("image_configs"):
            return  # 已是新结构
        legacy_url = self._data.get("image_api_url", "")
        if not legacy_url:
            return  # 老结构也没填，不创建空 config
        legacy_key = self._data.get("image_api_key", "")
        if not legacy_key:
            return  # 没 key 就不迁移（避免空 config 进列表）
        cid = "default"
        cfg_obj = {
            "id": cid,
            "name": "默认生图 API",
            "base_url": str(legacy_url).rstrip("/"),
            "api_key": str(legacy_key),
            "model": str(self._data.get("image_model", "gpt-image-2-reverse") or "gpt-image-2-reverse"),
            "resolution": str(self._data.get("image_resolution", "2K") or "2K"),
            "ratio": str(self._data.get("image_ratio", "1:1") or "1:1"),
            "timeout": int(self._data.get("image_timeout", 600) or 600),
            "saved_models": list(self._data.get("image_saved_models", []) or []),
        }
        self._data["image_configs"] = [cfg_obj]
        self._data["active_image_config"] = cid
        log.info("Config: 迁移老 image_api_url → image_configs[0] (id=%s)", cid)

    @property
    def image_base_url(self) -> str:
        """从活跃 image_config 读 base_url，兜底顶层 image_api_url。"""
        return str(self._active_image_config_field("base_url", "") or "").rstrip("/")

    @property
    def image_api_key(self) -> str:
        """从活跃 image_config 读 api_key，兜底顶层 image_api_key。"""
        return str(self._active_image_config_field("api_key", "") or "").strip()

    @property
    def image_host_api_key(self) -> str:
        """v0.7.8.46：图床 API key（imgbb），用于把本地资产图上传成公网 URL
        给 agnes 等只接受 URL 的视频 API 用作 image 字段。缺则空字符串。
        配置位置：config/hermes_api.json 顶层 image_host_api_key 字段。
        """
        return str(self._data.get("image_host_api_key", "") or "").strip()

    @property
    def image_model(self) -> str:
        """默认 gpt-image-2-reverse 复刻 server.py:1803。"""
        return str(self._active_image_config_field("model", "gpt-image-2-reverse") or "gpt-image-2-reverse").strip()

    @property
    def image_resolution(self) -> str:
        """1K / 2K / 4K。复刻自 server.py:1804。"""
        return str(self._active_image_config_field("resolution", "2K") or "2K").strip()

    @property
    def image_ratio(self) -> str:
        """宽:高 比，如 1:1 / 16:9 / 9:16。复刻自 server.py:1805。"""
        return str(self._active_image_config_field("ratio", "1:1") or "1:1").strip()

    @property
    def image_timeout(self) -> int:
        try:
            return int(self._active_image_config_field("timeout", 600) or 600)
        except (TypeError, ValueError):
            return 600

    # ---------- v0.7.8.38 视频 API（OpenAI 兼容 /v1/videos/generations 或类似） ----------
    # 多 config 模式（仿 image_configs + LLM `configs/active`）。
    # 视频生成有两条路：
    # A) Web 生成（dreamina.exe，OAuth 登录）—— 走 dreamina_exe 路径 + dreamina_video_args 命令模板
    # B) API 生成（中转 API，OpenAI 兼容）—— 走 video_api_configs[active] 的
    #    base_url + api_key + model + ratio + duration + resolution + timeout
    # 复刻自老 software D:\剧本分镜助手\templates\index.html:1824-1905 showApiSettingsModal
    # 思路（5 字段 form 升级成多 config，跟 LLM / 生图完全一致）。

    @property
    def video_api_configs(self) -> List[Dict[str, Any]]:
        """视频 API 多 config 列表（仿 image_configs / LLM `configs`）。

        每条：{id, name, base_url, api_key, model, ratio, duration, resolution, timeout, saved_models}
        """
        return list(self._data.get("video_api_configs", []) or [])

    @property
    def active_video_api_config_id(self) -> str:
        return str(self._data.get("active_video_api_config", "") or "")

    def _active_video_api_config_field(self, key: str, default: Any) -> Any:
        """从活跃 video_api_config 读字段；找不到则回退到顶层旧字段（兼容过渡）。

        逻辑（与 _active_image_config_field 完全对称）：
        1) 在 video_api_configs 里找 active 指向的那条 → 读字段
        2) active 命中但字段为空 → 不再 fallback hack（避免"用户配了
           base_url 却被旧字段覆盖"的"自作主张"行为）
        3) 找不到 active 或 video_api_configs 空 → 回退到顶层旧字段

        v0.7.8.38.2【下放硬约束】：ratio/duration/resolution **不**做 legacy 兜底
        —— 这三个字段完全由"生视频界面"决定，settings 永远不读不写它们。
        """
        for c in self.video_api_configs:
            if c.get("id") == self.active_video_api_config_id:
                v = c.get(key)
                if v not in (None, ""):
                    return v
                break
        # 兜底：顶层旧字段
        # v0.7.8.38.2：删掉 ratio / duration / resolution（已下放到生视频界面）
        legacy_map = {
            "base_url": "video_api_url",
            "api_key": "video_api_key",
            "model": "video_api_model",
            "timeout": "video_api_timeout",
        }
        legacy_key = legacy_map.get(key, "")
        if legacy_key:
            v = self._data.get(legacy_key)
            if v not in (None, ""):
                return v
        return default

    def _migrate_legacy_video_api_config(self) -> None:
        """v0.7.8.38：把顶层 video_api_url 等老字段迁移到 video_api_configs[0]。

        老结构（如果有的话）：
            video_api_url / video_api_key / video_api_model / video_api_timeout
        新结构：
            video_api_configs: [{id, name, base_url, api_key, model, timeout, saved_models}]
            active_video_api_config: "id"

        v0.7.8.38.1【无兜底硬约束】：model/timeout 字段直接透传用户保存的旧值
        （可能是空字符串），**不**塞"doubao-seedance-2.0-fast-face"/1800 这种
        系统默认值。用户配什么用什么。
        v0.7.8.38.2【下放硬约束】：ratio/duration/resolution **不**迁移到
        video_api_configs（也不在新结构里保留），这三个字段完全由"生视频界面"
        决定，每次生成时按用户当时选的来。settings 页面只配 API 基础信息。
        """
        if self._data.get("video_api_configs"):
            return  # 已是新结构
        legacy_url = self._data.get("video_api_url", "")
        if not legacy_url:
            return  # 老结构也没填，不创建空 config
        legacy_key = self._data.get("video_api_key", "")
        if not legacy_key:
            return  # 没 key 就不迁移（避免空 config 进列表）
        cid = "default"
        cfg_obj = {
            "id": cid,
            "name": "",  # 无兜底：老结构没 name 字段，留空让用户自己填
            "base_url": str(legacy_url).rstrip("/"),
            "api_key": str(legacy_key),
            # v0.7.8.38.1【无兜底】：model/timeout 从老字段直读，缺啥就空字符串/0
            "model": str(self._data.get("video_api_model", "") or ""),
            "timeout": int(self._data.get("video_api_timeout", 0) or 0),
            "saved_models": list(self._data.get("video_api_saved_models", []) or []),
            # v0.7.8.38.2【下放硬约束】：ratio/duration/resolution **不**进 video_api_configs
        }
        self._data["video_api_configs"] = [cfg_obj]
        self._data["active_video_api_config"] = cid
        log.info("Config: 迁移老 video_api_url → video_api_configs[0] (id=%s)", cid)

    @property
    def video_api_base_url(self) -> str:
        """v0.7.8.38.1【无兜底】：从活跃 video_api_config 读 base_url，缺则空字符串。"""
        v = self._active_video_api_config_field("base_url", None)
        if v in (None, ""):
            return ""
        return str(v).rstrip("/")

    @property
    def video_api_key(self) -> str:
        """v0.7.8.38.1【无兜底】：从活跃 video_api_config 读 api_key，缺则空字符串。"""
        v = self._active_video_api_config_field("api_key", None)
        if v in (None, ""):
            return ""
        return str(v).strip()

    @property
    def video_api_model(self) -> str:
        """v0.7.8.38.1【无兜底硬约束】：用户填什么用什么，缺则空字符串。
        **不**用 "doubao-seedance-2.0-fast-face" 或其它系统默认值。
        """
        v = self._active_video_api_config_field("model", None)
        if v in (None, ""):
            return ""
        return str(v).strip()

    @property
    def video_api_timeout(self) -> int:
        """v0.7.8.38.1【无兜底】：用户填什么用什么，缺则 0。
        **不**用 1800 默认值。"""
        v = self._active_video_api_config_field("timeout", None)
        if v in (None, ""):
            return 0
        try:
            return int(v)
        except (TypeError, ValueError):
            return 0

    # ---------- v0.7.8.38 dreamina.exe 路径 setter ----------
    def set_dreamina_exe(self, path: str) -> None:
        """v0.7.8.38：设置 dreamina.exe 路径（绝对路径字符串）。空字符串允许（用户主动清空）。"""
        self._data["dreamina_exe"] = str(path or "").strip()
        self._save()

    # ---------- v0.7.8.38 视频 API 多 config 增删改 ----------
    def upsert_video_api_config(self, cfg: Dict[str, Any]) -> None:
        """v0.7.8.38：新增或更新一个 video_api_config 项（按 id 匹配）。
        仿 image_configs / LLM `upsert_config` 行为。
        """
        import uuid as _uuid
        if not cfg.get("id"):
            cfg["id"] = _uuid.uuid4().hex[:8]
        for i, c in enumerate(self._data.get("video_api_configs", [])):
            if c.get("id") == cfg["id"]:
                self._data["video_api_configs"][i] = cfg
                self._save()
                return
        cfgs = list(self._data.get("video_api_configs", []) or [])
        cfgs.append(cfg)
        self._data["video_api_configs"] = cfgs
        self._save()

    def delete_video_api_config(self, config_id: str) -> None:
        """v0.7.8.38：删除一个 video_api_config 项（按 id）。"""
        new_cfgs = [c for c in self._data.get("video_api_configs", []) if c.get("id") != config_id]
        if len(new_cfgs) == len(self._data.get("video_api_configs", []) or []):
            raise ConfigError(f"视频 API 配置项不存在: {config_id}")
        self._data["video_api_configs"] = new_cfgs
        if self._data.get("active_video_api_config") == config_id:
            self._data["active_video_api_config"] = new_cfgs[0]["id"] if new_cfgs else ""
        self._save()

    def duplicate_video_api_config(self, config_id: str) -> str:
        """v0.7.8.38：复制一个 video_api_config 项，追加到末尾，返回新 id。"""
        import copy as _copy
        import uuid as _uuid
        for c in self._data.get("video_api_configs", []):
            if c.get("id") == config_id:
                new_cfg = _copy.deepcopy(c)
                new_cfg["id"] = _uuid.uuid4().hex[:8]
                base_name = new_cfg.get("name", "未命名")
                if "副本" not in base_name:
                    new_cfg["name"] = f"{base_name} (副本)"
                cfgs = list(self._data.get("video_api_configs", []) or [])
                cfgs.append(new_cfg)
                self._data["video_api_configs"] = cfgs
                self._save()
                return new_cfg["id"]
        raise ConfigError(f"视频 API 配置项不存在: {config_id}")

    def set_active_video_api_config(self, config_id: str) -> None:
        """v0.7.8.38：切换 active 视频 API config。"""
        for c in self._data.get("video_api_configs", []):
            if c.get("id") == config_id:
                self._data["active_video_api_config"] = config_id
                self._save()
                return
        raise ConfigError(f"视频 API 配置项不存在: {config_id}")

    @property
    def outputs_dir(self) -> Path:
        p = self._data.get("outputs_dir", "outputs")
        if not Path(p).is_absolute():
            p = self._project_root / p
        return p

    @property
    def hermes_home(self) -> Path:
        """HERMES_HOME 目录：hermes 找 profiles/<name>/ 的根。

        v0.7.6 修：manju 用**自己**的 HERMES_HOME（resources/hermes），不再用
        C 盘 ~/.hermes。链路对齐老 software D:\\剧本分镜助手\\launcher.py:306
        `env["HERMES_HOME"]=D:\hermes\profiles` 的做法——老 software 调 hermes
        用 D 盘 profile 里的 SOUL.md + script-asset-designer/SKILL.md v2.2.0
        完整版（240 行，定义所有 `### 人物N：角色名` 字段格式 + 12 条规则），
        LLM 主动 `skill_view` 加载完整 SKILL.md → 输出 manju parser 能解析的
        格式（`### 人物1：陈戈` + `- 中文指令词:`）。

        manju 之前设 `HERMES_HOME = ~/.hermes`（C 盘），但 C 盘 SKILL.md 是
        v2.3.0 精简版（38 行，只有大型剧本提取注意事项，没有字段格式定义），
        LLM 即便 skill_view 也看不到完整格式 → 输出 `### 1. 陈戈` + `**指令词**:`，
        manju parser 0 解析。

        修法：
        - manju 用 `resources/hermes`（项目内，D:\\漫剧助手\\resources\\hermes）
        - 首次启动时从 D:\\hermes\\profiles\\asset-designer\\ 复制完整的
          SOUL.md + script-asset-designer/SKILL.md v2.2.0 + asset-designer-core/SKILL.md
        - 启动 hermes 前 inject_api_to_profile() 把 active model 注入 config.yaml
        - 这样 manju 跟老 software 调 hermes 时加载的资源完全一致
        - 不污染 C 盘 ~/.hermes 也不依赖 D 盘

        探测顺序：
        1. config 显式配的 hermes_home（用户主动改时优先）
        2. <project_root>/resources/hermes（manju 自带, v0.7.6 新增）
        3. ~/.hermes/（如果存在 — 兼容旧部署）
        4. <hermes.exe 父目录>/../（如果存在 profiles/ 子目录）
        5. 环境变量 HERMES_HOME（兜底）
        6. 兜底：<hermes.exe 父目录>/../（profiles/ 可能不存在）
        """
        explicit = self._data.get("hermes_home", "")
        if explicit:
            p = Path(explicit)
            if not p.is_absolute():
                p = self._project_root / p
            return p
        # v0.7.6：manju 自带的 resources/hermes（项目内, 不污染系统）
        local = self._project_root / "resources" / "hermes"
        if local.is_dir():
            return local
        home = Path.home() / ".hermes"
        if home.is_dir():
            return home
        # hermes.exe 旁边找 profiles/ 目录（用户最常见的安装方式）
        candidates = [
            self.hermes_exe_path.parent.parent,  # <venv_root>/
            self.hermes_exe_path.parent.parent.parent,  # <hermes_root>/
        ]
        for cand in candidates:
            if (cand / "profiles").is_dir():
                return cand
        # 环境变量（用户可能误设，但仍尊重 — hermes 自己也会看 env）
        env_h = os.environ.get("HERMES_HOME")
        if env_h:
            return Path(env_h)
        # 最后兜底
        return candidates[0]

    @property
    def timeout_seconds(self) -> int:
        return int(self._data.get("timeout_seconds", 7200))

    @property
    def profiles(self) -> Dict[str, str]:
        return dict(self._data["profiles"])

    def profile_for(self, key: str) -> str:
        """根据业务 key 查 hermes profile 名。"""
        profs = self._data.get("profiles", {})
        if key not in profs:
            raise ConfigError(f"未配置 profile: {key}")
        return profs[key]

    @property
    def active_config(self) -> Dict[str, Any]:
        active_id = self._data["active"]
        for c in self._data["configs"]:
            if c["id"] == active_id:
                return c
        raise ConfigError(f"active 配置项不存在: {active_id}")

    @property
    def all_configs(self) -> List[Dict[str, Any]]:
        return list(self._data["configs"])

    def set_active(self, config_id: str) -> None:
        for c in self._data["configs"]:
            if c["id"] == config_id:
                self._data["active"] = config_id
                self._save()
                return
        raise ConfigError(f"配置项不存在: {config_id}")

    # ---------- v0.6.24 agent-configs 完整管理 ----------
    def upsert_config(self, cfg: Dict[str, Any]) -> None:
        """v0.6.24：新增或更新一个 config 项（按 id 匹配）。

        复刻原软件 server.py:3390-3413 `POST /api/settings/agent-configs`：
        - 如果 cfg.id 已存在 → 覆盖该条
        - 否则 → 追加到末尾
        - 自动保存到 json
        - 字段标准化：id 留空则生成 uuid4-hex[8]
        """
        import uuid as _uuid
        if not cfg.get("id"):
            cfg["id"] = _uuid.uuid4().hex[:8]
        for i, c in enumerate(self._data["configs"]):
            if c.get("id") == cfg["id"]:
                self._data["configs"][i] = cfg
                self._save()
                return
        self._data["configs"].append(cfg)
        self._save()

    def delete_config(self, config_id: str) -> None:
        """v0.6.24：删除一个 config 项（按 id）。

        复刻原软件 server.py:3416-3424 `DELETE /api/settings/agent-configs/<id>`：
        - 如果删的是 active → active fallback 到第一个剩余 config
        - 如果删后没有 config → 允许（active 清空，用户自己再设）
        - 自动保存到 json
        """
        new_configs = [c for c in self._data["configs"] if c.get("id") != config_id]
        if len(new_configs) == len(self._data["configs"]):
            raise ConfigError(f"配置项不存在: {config_id}")
        self._data["configs"] = new_configs
        if self._data["active"] == config_id:
            self._data["active"] = new_configs[0]["id"] if new_configs else ""
        self._save()

    def duplicate_config(self, config_id: str) -> str:
        """v0.6.24：复制一个 config 项，追加到末尾，返回新 id。

        复刻原软件没有"复制"功能（只有 save/delete），manju 加上方便用户
        在"deepseek"基础上加"deepseek-副本"测试新 base_url。
        """
        import copy as _copy
        import uuid as _uuid
        for c in self._data["configs"]:
            if c.get("id") == config_id:
                new_cfg = _copy.deepcopy(c)
                new_cfg["id"] = _uuid.uuid4().hex[:8]
                # name 加 "(副本)" 后缀
                base_name = new_cfg.get("name", "未命名")
                if "副本" not in base_name:
                    new_cfg["name"] = f"{base_name} (副本)"
                self._data["configs"].append(new_cfg)
                self._save()
                return new_cfg["id"]
        raise ConfigError(f"配置项不存在: {config_id}")

    # ---------- v0.6.25 hermes-config 顶层字段编辑 ----------
    def set_hermes_exe(self, path: str) -> None:
        """v0.6.25：设置 hermes.exe 路径（绝对路径字符串）。空字符串允许（用户主动清空）。"""
        self._data["hermes_exe"] = str(path or "").strip()
        self._save()

    def set_outputs_dir(self, path: str) -> None:
        """v0.6.25：设置 outputs 目录。"""
        self._data["outputs_dir"] = str(path or "").strip() or "outputs"
        self._save()

    def set_timeout(self, seconds: int) -> None:
        """v0.6.25：设置 hermes 调用超时（秒）。范围 [60, 86400]。"""
        seconds = max(60, min(int(seconds or 7200), 86400))
        self._data["timeout_seconds"] = seconds
        self._save()

    def set_hermes_home(self, path: str) -> None:
        """v0.6.25：设置 HERMES_HOME 路径（复刻原软件 server.py:3047 读 os.environ 优先）。

        manju 改用持久化字段存（写到 hermes_api.json），**不要**写全局环境变量
        （subprocess 子进程会继承，写到全局 env 会污染其它 app）。
        空字符串允许（未设置时让 detector 自动探）。
        """
        self._data["hermes_home"] = str(path or "").strip()
        self._save()

    def set_profile_name(self, key: str, value: str) -> None:
        """v0.6.25：设置 profiles dict 单个 key（按业务方实际 key 允许）。

        业务方 key 形如 {"storyboard", "asset", "video_prompt"}（取决于
        `core.generators` 里 `profile_for("xxx")` 的字面量）。
        不再硬编码 3 个值，避免改错。
        """
        if not key or not isinstance(key, str):
            raise ConfigError(f"profile key 非法: {key!r}")
        profiles = self._data.get("profiles") or {}
        profiles[key] = str(value or "").strip()
        self._data["profiles"] = profiles
        self._save()

    def _save(self) -> None:
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ---------- 注入 API 配置到 hermes profile ----------
    def inject_api_to_profile(self, profile_name: str) -> None:
        """把 active 配置（model/api_key/base_url/provider）写到
        `<HERMES_HOME>/profiles/<profile_name>/config.yaml`。

        旧 server.py 里的 _inject_api_to_profile：每次调 hermes 之前必须做，
        不然 hermes 用 profile 自带硬编码的 model/key，**完全不看你设置面板
        里 active 是哪个**（这就是为啥你 active=agnes，但 hermes 在调 deepseek）。

        行为：
        - 读 profiles/<name>/config.yaml
        - d.model.api_key / base_url / default / provider = active 配置
        - provider=custom：d.providers[<key>] 也写一份 base_url + api_key
        - 写回 config.yaml（覆盖）
        """
        import logging
        log = logging.getLogger("manju.config")

        active = self.active_config  # {"id", "name", "provider", "model", "base_url", "api_key"}
        profile_dir = self.hermes_home / "profiles" / profile_name
        cfg_path = profile_dir / "config.yaml"

        if not cfg_path.exists():
            log.warning("inject_api: config.yaml 不存在: %s，跳过", cfg_path)
            return

        # 算 provider key：custom 用 name/id，普通用 provider
        prov = active.get("provider", "deepseek")
        if prov == "custom":
            prov_key = (active.get("name") or active.get("id") or "custom").strip()
        else:
            prov_key = prov

        try:
            import yaml  # PyYAML
            with open(cfg_path, "r", encoding="utf-8") as f:
                d = yaml.safe_load(f) or {}
        except Exception as e:
            log.warning("inject_api: 读 config.yaml 失败 %s: %s", cfg_path, e)
            return

        # v0.7.8 修：profile 模板里 `model: deepseek-v4-pro` 是字符串（不是 dict）
        # d.setdefault("model", {}) 不覆盖已存在的 str，会让 m 是 str
        # m["api_key"] = ... 就 'str' object does not support item assignment
        # 改成:model 不是 dict 就强制用空 dict 覆盖
        m = d.get("model")
        if not isinstance(m, dict):
            m = {}
        d["model"] = m
        # v0.7.8.23:base_url 规范化——**确保以 /v1 结尾**(如不在就补上)。
        # 复刻老 software D:\剧本分镜助手\server.py:1588 + server.py:1822 + image_api.py:101-110。
        # 原因(2026-07-03 排查):hermes v0.17 内部 proxy (hermes_cli/proxy/server.py:238)
        # 路由是 `/v1/{tail:.*}`,tail 是 `chat/completions`(不含 /v1)。拼装 URL
        # (server.py:136) `upstream_url = f"{base_url.rstrip('/')}{rel_path}"` —— base_url
        # 必须在末尾带 `/v1`,最终才能拼出 `<root>/v1/chat/completions`。
        # 之前 v0.7.8.2 的 `_strip_v1_suffix` **剥掉** /v1,导致 hermes 拼成
        # `https://apihub.agnes-ai.com/chat/completions`(没 /v1) → URL 不存在 →
        # Cloudflare 403,现象跟"被 WAF 拦"完全一样但根因是 URL 拼错。
        # manju 自己直连用 `_strip_v1_suffix` 是对的(自己会补 /v1);但 inject
        # 给 hermes 时**反向**——必须保留 /v1。
        norm_base_url = _ensure_v1_suffix(_strip_v1_suffix(active.get("base_url", "")))
        m["api_key"] = active.get("api_key", "")
        m["base_url"] = norm_base_url
        # v0.7.8.26:不再 fallback "deepseek-v4-pro"。如果用户保存的 active config
        # 缺 model 字段,直接 KeyError 让用户知道(硬约束:用户选什么模型就用什么
        # 模型,禁止任何系统兜底)。SettingsDialog._on_save 强制校验 model 必填,
        # 正常路径下 active["model"] 一定有值。
        m["default"] = active["model"]

        # v0.7.8.4:model.provider **总是** 设成 "custom" + 总是写 providers dict。
        #
        # 复现根因(本用户 2026-07-02 反馈的"分镜生成一直 401/403 Cloudflare"现象):
        # 1) hermes 的 model dispatch 链路 (hermes_cli/runtime_provider.py:1075):
        #    `effective_provider = "custom" if requested_norm == "custom" else "openrouter"`
        #    + runtime_provider.py:999-1007 的 `use_config_base_url` 只在
        #    `requested_norm == "auto"` 或 `requested_norm == "custom"` 时为 True。
        # 2) 老代码 `m["provider"] = prov_key`("deepseek") → `requested_norm="deepseek"`
        #    → 既不是 "auto" 也不是 "custom" → use_config_base_url=False →
        #    base_url 被置空,hermes 走 "openrouter" 分支但没 base_url,fallback 到
        #    `providers` 段里**老**的 custom provider(残留的 Agnes AI Flash)
        #    + auth.json 的 exhausted apihub key 调 apihub.agnes-ai.com → 403 Cloudflare。
        # 3) 即便 use_config_base_url=True,hermes 调 custom pool 时
        #    (agent/credential_pool.py:2249) 只在 `model_provider == "custom"`
        #    时 seed `model.api_key` 进池,其它 provider 不 seed,池里没 deepseek key。
        #    修法:model.provider 强制 "custom",让 hermes 走 custom pool + seed model.api_key。
        m["provider"] = "custom"
        m["provider_key"] = prov_key  # 人读标识("deepseek" / "Agnes AI Flash"),不影响 dispatch

        # v0.7.8.4:总是写 `providers` dict,**不**只在 `prov == "custom"` 时写。
        # 否则 hermes 调 LLM 时 `_get_custom_provider_config(pool_key)` 找不到
        # deepseek 这个 custom provider entry (`_iter_custom_providers` 读 providers
        # dict 转换来的 list 是空的),custom pool seed 不进 model.api_key。
        # 复刻 hermes_cli/config.py:4436-4447 `providers_dict_to_custom_providers` 格式:
        # 至少需要 `name` + `base_url` + `api_key` 才能被 `_normalize_custom_provider_entry`
        # 接受(config.py:4260+)。
        d.setdefault("providers", {})[prov_key] = {
            "name": active.get("name", prov_key) or prov_key,
            "base_url": norm_base_url,
            "api_key": active.get("api_key", ""),
        }

        # 顶层 provider 字段(老格式 `provider: custom:deepseek`): hermes 启动时
        # `resolve_requested_provider` (runtime_provider.py:482-485) 会先读
        # `model.provider`(已经是 "custom"),顶层这个只是给老 hermes 兼容。
        d["provider"] = f"custom:{prov_key}"

        # v0.7.8.6:同步更新 `custom_providers` 段(老 list 格式)。
        # 复现根因(本用户 2026-07-02 反馈"换 key 后软件还是用 b223"):
        # hermes 启动时 `_seed_custom_pool` (agent/credential_pool.py:2214) 调
        # `_get_custom_provider_config(pool_key)`,该函数读 `custom_providers`
        # **list 段**(不是 `providers` dict 段,行 360-377 `_iter_custom_providers`)。
        # 老 software / 老 manju 版本写 yaml 时在 `custom_providers` 段直接塞
        # `{name, api_key, base_url, model}` list,manju v0.7.8.4 inject **只**
        # 改 `model.api_key` + `providers[name]`,**完全没动** `custom_providers` 段,
        # hermes 走 `custom_providers` 路径读到的还是**老 key**(`****b223 is invalid`),
        # 无论用户在 settings 怎么换 key、点几次保存,hermes 调的还是 b223。
        # 修法:按 name 匹配更新 custom_providers 对应 entry 的 api_key / base_url /
        # model;name 不存在则**追加**一条新 entry(用 active.name)。
        # 注意:绝对不能简单清空 `custom_providers` 段——老 hermes 完全依赖这个段做
        # `_get_custom_provider_config` 查找,清空会导致 hermes 找不到 custom
        # provider entry → pool 空 → 没法调 LLM。
        cp_list = d.get("custom_providers")
        if not isinstance(cp_list, list):
            cp_list = []
        # 找同 name 的 entry 覆盖,没找到则追加
        cp_found = False
        for entry in cp_list:
            if isinstance(entry, dict) and entry.get("name") == prov_key:
                entry["api_key"] = active.get("api_key", "")
                entry["base_url"] = norm_base_url
                entry["model"] = active.get("model", "deepseek-v4-pro")
                entry.setdefault("api_mode", "chat_completions")
                cp_found = True
                break
        if not cp_found:
            cp_list.append({
                "name": prov_key,
                "api_key": active.get("api_key", ""),
                "base_url": norm_base_url,
                "model": active.get("model", "deepseek-v4-pro"),
                "api_mode": "chat_completions",
            })
        d["custom_providers"] = cp_list

        try:
            import yaml
            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.dump(d, f, allow_unicode=True, default_flow_style=False)
            log.info(
                "inject_api: %s 注入完成 (active=%s, provider=%s, model=%s, "
                "custom_providers 更新=%s)",
                profile_name, active.get("id"), prov_key, m["default"], "yes",
            )
        except Exception as e:
            log.warning("inject_api: 写 config.yaml 失败 %s: %s", cfg_path, e)
            return

        # v0.7.8.3:同步清空 auth.json 的 credential_pool。
        # 复现根因:hermes 实际不读 config.yaml 的 model.api_key,而是从
        # `<HERMES_HOME>/profiles/<name>/auth.json` 的 `credential_pool.<provider>[]`
        # 池子里取 key(由 D:\hermes\hermes-agent\agent\credential_pool.py
        # 维护,exhausted 后冷却 5 分钟才重试,401 错误被持久化在 auth.json)。
        # inject_api 只改 config.yaml,完全不碰 auth.json,hermes 每次启动都拿
        # 之前 exhausted 的老 key 继续撞 401,用户截图 13:25:46 失败就是这原因。
        # 修法:inject 完成后清空 credential_pool,hermes 下次启动时
        # load_pool() 看到池子空,会从 config.yaml 重新 import 新 key。
        self._reset_hermes_auth_pool(profile_dir, prov_key, active, log)

    def _reset_hermes_auth_pool(
        self, profile_dir: Path, prov_key: str, active: Dict[str, Any],
        log: "logging.Logger",
    ) -> None:
        """v0.7.8.3:把 `<profile>/auth.json` 的 `credential_pool` 段清空,
        让 hermes 下次启动时重新从 config.yaml 加载新 key。

        只清空对应 provider 的池子条目(保留其他 provider 的 exhausted 状态不动),
        不动 auth.json 其他段(version / providers / updated_at)。
        """
        auth_path = profile_dir / "auth.json"
        if not auth_path.exists():
            log.debug(
                "inject_api: auth.json 不存在 %s,跳过 reset", auth_path
            )
            return
        try:
            with open(auth_path, "r", encoding="utf-8") as f:
                auth = json.load(f)
        except Exception as e:
            log.warning(
                "inject_api: 读 auth.json 失败 %s: %s,跳过 reset",
                auth_path, e,
            )
            return

        pool = auth.get("credential_pool") or {}
        if not pool:
            log.debug(
                "inject_api: auth.json credential_pool 已空 %s,无需 reset",
                auth_path,
            )
            return

        # 只清空对应 provider 的池子条目(custom:agnes / custom:deepseek 等),
        # 保留其他 provider 的 exhausted 状态不动(用户可能配置了多个 active,
        # 一次性全清会冲掉其他 provider 的冷却记录)。
        #
        # v0.7.8.9:同时清 `custom:<name>` 和 `custom:<id>` 两种格式。
        # 复现根因(本用户 2026-07-02 反馈"换 key 后分镜仍报 401,池子 exhausted 没清掉"):
        # inject 时 `prov_key = active.get("name") or active.get("id")` 优先用 name
        # (eg. "Agnes AI Flash"),但 hermes `_seed_custom_pool` 把 model.api_key seed
        # 进 credential_pool 时的 key 是 `custom:<id>` 格式 (eg. "custom:agnes")。
        # 之前的 `_reset_hermes_auth_pool` 只算 `custom:<prov_key>` ("custom:Agnes AI Flash"),
        # 跟实际 pool key ("custom:agnes") **不匹配 → del 不进去 → exhausted 没清掉**。
        # 修法:把 name 和 id 两个都试一遍,任一命中就 del。两个 key 都不命中说明
        # 这个 provider 还没 seed 进池子,自然不用清。
        #
        # v0.7.8.15:hermes 实际 pool key 格式是 `_normalize_custom_pool_name(name)`,
        # 即 `name.strip().lower().replace(" ", "-")` —— "Agnes AI Flash" → "agnes-ai-flash",
        # pool key = "custom:agnes-ai-flash"(slug)。之前的 raw name "custom:Agnes AI
        # Flash" 跟真实 pool key 永远不匹配 → 403 Cloudflare exhausted entry 永远
        # 清不掉。现在加 slug 版,3 个 key 一起清。
        def _slugify(s: str) -> str:
            return (s or "").strip().lower().replace(" ", "-")

        custom_key_by_name = f"custom:{active.get('name', '') or ''}"
        custom_key_by_name_slug = f"custom:{_slugify(active.get('name', '') or '')}"
        custom_key_by_id = f"custom:{active.get('id', '') or ''}"
        cleared = 0
        seen_keys: set[str] = set()
        for custom_key in (
            custom_key_by_name,
            custom_key_by_name_slug,
            custom_key_by_id,
        ):
            if not custom_key or custom_key == "custom:" or custom_key in seen_keys:
                continue
            seen_keys.add(custom_key)
            if custom_key in pool:
                del pool[custom_key]
                cleared += 1
        # 兜底:也清掉顶层 provider 字段(某些 hermes 版本可能用 "agnes" 作 key)
        if prov_key in pool:
            del pool[prov_key]
            cleared += 1
        if active.get("id") and active["id"] in pool:
            del pool[active["id"]]
            cleared += 1
        if prov_key and prov_key != "custom:":
            prov_slug = f"custom:{_slugify(prov_key)}"
            if prov_slug in pool and prov_slug not in seen_keys:
                del pool[prov_slug]
                cleared += 1
        auth["credential_pool"] = pool

        try:
            with open(auth_path, "w", encoding="utf-8") as f:
                json.dump(auth, f, ensure_ascii=False, indent=2)
            log.info(
                "inject_api: auth.json credential_pool 已清空 (cleared=%d, key=%s)",
                cleared, custom_key,
            )
        except Exception as e:
            log.warning(
                "inject_api: 写 auth.json 失败 %s: %s", auth_path, e
            )

    # ---------- v0.7.6 本地 hermes profile 初始化 ----------
    # 老 software D:\剧本分镜助手\launcher.py:306 设 HERMES_HOME=D:\hermes\profiles,
    # 跑 hermes 用 D 盘 profile 里的 SOUL.md + script-asset-designer/SKILL.md v2.2.0
    # 完整版（240 行，定义所有 `### 人物N：角色名` 字段格式 + 12 条规则）。
    # manju v0.7.5 之前设 HERMES_HOME=C:\Users\Administrator\.hermes，C 盘 SKILL.md
    # 是 v2.3.0 精简版（38 行，没有字段格式定义）→ LLM 输出 manju parser 不认的格式
    # （`### 1. 陈戈` + `**指令词**:`），parse_asset_markdown 0 解析。
    #
    # v0.7.6 修：manju 启动时把 D 盘 profile 资源**复制到自己项目目录**
    # `resources/hermes/profiles/<name>/`（不复刻，全部"复刻自 launcher.py:306 思路"
    # ——只复制资源文件，不 import 也不调 D 盘任何代码），然后 manju 用自己的
    # HERMES_HOME 跑 hermes，行为跟老 software 完全一致。

    # v0.7.8.X 用户版:移除 D 盘老 software 资源回退。用户电脑没 D:\hermes\,
    # ensure_local_hermes_profile 改为只从 manju 自带 resources/hermes/_seed 复制。
    # dev 端才保留 D 盘回退(老 software 还在)。
    # 在 dev 端打开 manju-x2 时,这个值会被 dev.py 改成 "D:/hermes/profiles"(如果文件存在)。
    _D_HERMES_PROFILES = Path("")

    # 必复制的资源（v0.7.6 链路核心）：
    # - SOUL.md: 中文输出 + 严格结构化铁律
    # - script-asset-designer/SKILL.md: v2.2.0 完整版（240 行，定义字段格式）
    # - asset-designer-core/SKILL.md: 核心 identity
    # - config.yaml: D 盘完整 14KB（含 _config_version=23 + agent 段 + 全部 schema）
    _LOCAL_PROFILE_FILES = (
        ("SOUL.md", "SOUL.md"),
        ("skills/script-asset-designer/SKILL.md", "skills/script-asset-designer/SKILL.md"),
        ("skills/asset-designer-core/SKILL.md", "skills/asset-designer-core/SKILL.md"),
        ("config.yaml", "config.yaml"),
    )

    # v0.7.8.8:**整个** D 盘 profile 的 `skills/` 目录都同步到 manju profile
    # (改成整目录 copytree,不再白名单几个固定子目录)。
    # 复现根因(本用户 2026-07-02 反馈"分镜 agent 更新了一下"):
    # v0.7.8.7 的 `_LOCAL_PROFILE_SKILLS_DIRS` 硬编码了 3 个子目录
    # (storyboard-script / asset-designer-core / script-asset-designer),
    # 用户在 D 盘新增了 `storyboard-self-check` v1.0.0(SOUL.md v3.1.0 引用),
    # manju 启动时**不会**自动同步这个新目录,需要用户手动 xcopy。
    # 修法:改用整目录 copytree(`shutil.copytree(src, dst, dirs_exist_ok=True)`),
    # D 盘有什么 manju 同步什么,**未来再加新 skill 也不需要改代码**。
    # 保留旧的 `_LOCAL_PROFILE_SKILLS_DIRS` 作为白名单(已存在但不再使用),
    # 防 v0.7.8.7 旧代码引用挂掉。
    _LOCAL_PROFILE_SKILLS_DIRS = (
        ("skills", "skills"),
    )

    def ensure_local_hermes_profile(self, profile_name: str) -> Path:
        """v0.7.6：确保 manju 自带 profile 资源就绪。返回 profile_dir 路径。

        行为：
        1. 路径 = `<project_root>/resources/hermes/profiles/<profile_name>/`
        2. 如果 config.yaml 不存在：
           a. 优先从 D:\\hermes\\profiles\\<profile_name>\\ 复制 D 盘完整资源
              （SOUL.md + SKILL.md + config.yaml, 老 software launcher.py:306
              用的就是 D 盘这套资源）
           b. 如果 D 盘不存在（用户没装老 software）→ 用 manju 自带的
              `resources/hermes/_seed/` 目录里的 hardcoded minimal 资源
              （如果连 _seed 都没有，就用 inject_api_to_profile 能接受的
              最简 config.yaml）
        3. 如果 config.yaml 存在：不动（保留用户/上次启动时 inject 的 model）
        4. 返回 profile_dir（让调用方继续 inject_api_to_profile）

        为什么不放在 hermes_home property 里做：避免每次读 hermes_home 时
        都做文件系统 IO（hermes 启动时会被读多次）。
        """
        import logging as _log
        import shutil as _shutil
        log = _log.getLogger("manju.config")

        profile_dir = self._project_root / "resources" / "hermes" / "profiles" / profile_name
        cfg_path = profile_dir / "config.yaml"

        # v0.7.8.7:同步 skills 子目录——**必须在 early return 之前**,否则首次启动后
        # config.yaml 存在 → 直接 return,skills 同步永远不跑,部署 D 盘资源丢了
        # 就找不回来(用户实测:"删了 storyboard-script 目录后跑 ensure 不会恢复")。
        self._sync_hermes_profile_skills(profile_name, log)

        if cfg_path.exists():
            # 已经初始化过（首次启动后留下的），啥都不做
            log.debug("ensure_local_hermes_profile: %s 已就绪", profile_dir)
            return profile_dir

        # 第一次启动：从 D 盘复制（或 fallback 到 manju 自带 _seed）
        profile_dir.mkdir(parents=True, exist_ok=True)
        d_src = self._D_HERMES_PROFILES / profile_name

        copied = 0
        if d_src.is_dir():
            # 老 software D 盘资源存在 → 复制（只复制必要的 4 个文件）
            for rel_dst, rel_src in self._LOCAL_PROFILE_FILES:
                src = d_src / rel_src
                dst = profile_dir / rel_dst
                if src.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    _shutil.copy2(src, dst)
                    copied += 1
            log.info(
                "ensure_local_hermes_profile: 从 D 盘 %s 复制 %d 个文件到 %s",
                d_src, copied, profile_dir,
            )
        else:
            # D 盘没装老 software → 用 manju 自带 _seed（如果有）
            seed = self._project_root / "resources" / "hermes" / "_seed" / profile_name
            if seed.is_dir():
                for rel_dst, rel_src in self._LOCAL_PROFILE_FILES:
                    src = seed / rel_src
                    dst = profile_dir / rel_dst
                    if src.is_file():
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        _shutil.copy2(src, dst)
                        copied += 1
                log.info(
                    "ensure_local_hermes_profile: 从 _seed 复制 %d 个文件到 %s",
                    copied, profile_dir,
                )
            else:
                # 兜底：写一个最小 config.yaml（让 hermes 至少能起来）
                log.warning(
                    "ensure_local_hermes_profile: D 盘 + _seed 都没找到 %s，"
                    "写最小 config.yaml", profile_name,
                )
                cfg_path.write_text(
                    "_config_version: 23\nmodel: {}\nproviders: {}\n",
                    encoding="utf-8",
                )

        return profile_dir

    def _sync_hermes_profile_skills(
        self, profile_name: str, log: "logging.Logger"
    ) -> None:
        """v0.7.8.7:把 D 盘 profile 的 skills 子目录整体 copytree 到 manju profile。

        D 盘是源(只读,不动),manju `<hermes_home>/profiles/<name>/` 是 dst。
        每次启动都跑,缺哪个文件补哪个,已有文件覆盖(`dirs_exist_ok=True`)。
        这样 manju 的 profile 跟 D 盘老 software 用的 profile 资源**完全一致**,
        LLM 调 `skill_view <skill-name>` 能拿到完整的 SKILL.md + references,
        而不是 SOUL.md 里的几行摘要。

        复现根因(本用户 2026-07-02):之前 `ensure_local_hermes_profile` 只复制
        `_LOCAL_PROFILE_FILES` 列的 4 个**单文件**,没复制整个 skills 子目录,
        导致 `skills/creative/storyboard-script/` 整目录缺失 → 分镜输出只有
        51 行摘要,不是 500+ 行完整导演手册。
        """
        import shutil as _shutil

        profile_dir = self._project_root / "resources" / "hermes" / "profiles" / profile_name
        d_src = self._D_HERMES_PROFILES / profile_name

        for rel_dst, rel_src in self._LOCAL_PROFILE_SKILLS_DIRS:
            src = d_src / rel_src
            dst = profile_dir / rel_dst
            if not src.is_dir():
                # D 盘没这个 skill,跳过(用户没装老 software 或老 software 版本老)
                continue
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                _shutil.copytree(src, dst, dirs_exist_ok=True)
                n = sum(1 for _ in dst.rglob("*") if _.is_file())
                log.info(
                    "ensure_local_hermes_profile: 同步 skills %s → %s (%d files)",
                    src, dst, n,
                )
            except Exception as e:
                log.warning(
                    "ensure_local_hermes_profile: 同步 skills %s 失败: %s",
                    src, e,
                )
