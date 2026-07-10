"""业务 Task 实现。

- StoryboardTask：调用 hermes.exe（profile=storyboard）生成分镜
- VideoPromptTask：调用 hermes.exe（profile=video_prompt）生成视频 prompt
- AssetExtractTask：调用 hermes.exe（profile=asset）提取资产清单
- AssetImageTask：调用 /v1/images/generations HTTP API 生资产参考图（单张，v0.7.7 改用 HTTP API 替代 dreamina.exe——dreamina 是生视频的）
- BatchAssetImageTask：复刻自原软件 POST /convert-assets，给项目下所有资产批量跑生图

均继承自 task_queue.Task。run() 内部只用 emit_progress / emit_output
发中间状态；终态由 _QueueWorker 统一发。
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from .asset_parser import (
    format_asset_list_text,
    list_file_path,
    parse_asset_markdown,
)
from .config import Config, ConfigError
from .dreamina import DreaminaRunner
from .hermes import HermesCancelledError, HermesTimeoutError, ManjuTask, RunResult
from .image_api import ImageApiRunner
from .prompts import (
    RENDER_TYPES,
    STYLES,
    _filter_storyboard_output,
    build_asset_image_prompt,
    build_project_asset_prompt,  # v0.7.3 新增
    build_seedance_prompt,
    build_storyboard_prompt,
    convert_to_standard_format,
)
from .task_queue import Task


# ---------- 请求数据类 ----------

@dataclass
class StoryboardRequest:
    """分镜生成请求参数。

    v0.6.17 扩字段对齐原软件 D:\\剧本分镜助手\\server.py:267
    `build_storyboard_prompt(script, previous_summaries, style_id, render_type)`。
    """

    episode_id: int
    episode_title: str
    synopsis: str  # 完整剧本
    user_prompt: Optional[str] = None  # 用户附加指示
    # v0.6.17：续集上下文（list of {episode_num, title, summary}）
    previous_summaries: Optional[list] = None
    # v0.6.17：风格 / 渲染类型注入（STYLES / RENDER_TYPES key）
    style_id: Optional[str] = None
    render_type: Optional[str] = None


@dataclass
class VideoPromptRequest:
    """视频 prompt 生成请求参数。

    v0.6.17：扩字段对齐原软件 D:\\剧本分镜助手\\server.py:1291
    `run_seedance_agent(task_id, storyboard, asset_cache, episode_id, episode_title,
    style_id, render_type)`。
    """

    episode_id: int
    episode_title: str
    storyboard_text: str  # 上一步生成的分镜内容
    # v0.6.17：资产名列表（人/场/物三段纯文本）— 来自 v0.6.16 的
    # AssetExtractTask.result_asset_list
    asset_names: str = ""
    # v0.6.17：风格 / 渲染类型
    style_id: Optional[str] = None
    render_type: Optional[str] = None
    # 兼容旧字段（保留）
    user_prompt: Optional[str] = None


@dataclass
class AssetExtractRequest:
    """资产抽取请求参数。"""

    episode_id: int
    storyboard_text: str  # 用分镜内容做资产抽取
    user_prompt: Optional[str] = None


@dataclass
class AssetImageRequest:
    """资产配图请求参数。"""

    episode_id: int
    asset_kind: str   # "character" / "scene" / "prop"
    asset_name: str
    description: str
    reference_image: Optional[Path] = None  # character 类可能已有参考图


@dataclass
class VideoRequest:
    """视频生成请求参数。

    视频生成依赖：
    - 必须先有 ep.prompt（VideoPromptTask 的输出）
    - 可选参考图：来自 ep 对应镜头的资产图
    - v0.6.20：可选音频文件（asset 级或段级），自动 append 到 prompt 末尾

    v0.7.8.39【链路选择硬约束】：
    - link_mode="web"（默认）：调 dreamina.exe（seedance 模型，走 web 视频生成）
    - link_mode="api"：调 video_api_configs[active] 的 base_url + api_key
      （OpenAI 兼容 HTTP /v1/videos/generations 或类似接口）
    两者**二选一**，互斥：UI 上用 RadioButton 强制。
    """

    episode_id: int
    episode_title: str
    prompt_text: str          # 来自 ep.prompt（整段 / 单镜头）
    segment_index: Optional[int] = None   # None = 整集
    reference_image: Optional[Path] = None
    # v0.6.20：音频文件列表（绝对路径字符串）
    audio_files: List[str] = field(default_factory=list)
    # v0.7.8.39：链路选择（"web" / "api"）+ 链路相关参数
    # web 模式：params 不用，dreamina_video_args / dreamina_models 在 config
    # api 模式：params 含 model / ratio / duration / resolution（用户在卡片里选）
    link_mode: str = "web"
    link_params: Dict[str, Any] = field(default_factory=dict)


# ---------- 结果数据类 ----------

@dataclass
class StoryboardResult:
    output_file: Path
    content: str


@dataclass
class VideoPromptResult:
    output_file: Path
    content: str


@dataclass
class AssetExtractResult:
    output_file: Path
    assets: List[dict]  # 解析后的资产列表
    content: str
    # v0.6.16：资产名列表（人/场/物三段），给下游 video prompt agent / UI 复制
    asset_list: str = ""
    asset_list_file: Optional[Path] = None


@dataclass
class AssetImageResult:
    output_file: Path
    prompt_used: str


@dataclass
class VideoResult:
    output_file: Path
    prompt_used: str


# ---------- 通用 helper ----------

def _safe_output_dir(config: Config, override: Optional[Path]) -> Path:
    """决定产物落盘目录：override > config.outputs_dir > 'outputs'。"""
    if override is not None:
        return override
    if config.outputs_dir is not None:
        return config.outputs_dir
    return Path("outputs")


# hermes.exe 是 PyInstaller 打包的 C 层程序，-q argv 传 > 20000 字节
# 会触发 STATUS_ACCESS_VIOLATION (0xC0000005) 段错误。
# 来源：D:\剧本分镜助手\server.py:541
# 旧软件用 len(prompt) > 20000 比较（即字符数）—— 短但能容纳大量 ASCII
# 的情况也能安全走 -q；只有核心数据（分镜/剧本）超长时才走文件方式。
HERMES_ARGV_LIMIT_CHARS = 20000


def _call_llm_via_urllib(
    config: Config,
    user_content: str,
    *,
    system_content: str = "",
    user_agent: str = "manju/0.7.8.22",
) -> str:
    """v0.7.8.21:manju 端直接调 LLM HTTP API(/v1/chat/completions),绕开 hermes。

    根因:hermes 内部 aiohttp 走 libssl 的 TLS fingerprint 被 Cloudflare WAF 拦了
    (独立启 hermes 报 HTTP 403 Cloudflare,diag_ua.py 用 Python urllib 200 OK)。
    之前 deepseek 跑通是因为 deepseek 国内 API 不走 Cloudflare,换 agnes 海外
    API 撞 Cloudflare WAF,只有绕开 hermes 才能调通。

    Args:
        config: Config 实例(读 active_config / timeout_seconds)。
        user_content: user 消息内容(剧本/分镜/描述等)。
        system_content: 可选 system 消息(prompt 模板),如不传则拼到 user 前面。
        user_agent: HTTP User-Agent 头。

    Returns:
        LLM 返回的 content 字符串。

    Raises:
        RuntimeError: 网络/HTTP/JSON 错误时统一抛 RuntimeError,
                      跟之前 hermes subprocess 的 returncode != 0 行为对齐。
    """
    import json
    import ssl
    import urllib.request
    import urllib.error
    from core.config import ConfigError

    # 1. 拿 active LLM config
    try:
        cfg = config.active_config
    except (ConfigError, KeyError) as e:
        raise RuntimeError(f"未配置 active LLM config: {e}") from e
    base_url = (cfg.get("base_url") or "").rstrip("/")
    api_key = (cfg.get("api_key") or "").strip()
    model = (cfg.get("model") or "agnes-2.0-flash").strip()
    if not base_url or not api_key:
        raise RuntimeError("active LLM config 缺 base_url 或 api_key")

    # 2. 算 endpoint(剥掉 /v1 防重复)
    b = base_url
    for tail in ("/v1/chat/completions", "/v1"):
        if b.endswith(tail):
            b = b[: -len(tail)]
            break
    endpoint = b + "/v1/chat/completions"
    logging.getLogger("manju.generators").info("调 LLM: POST %s (model=%s)", endpoint, model)

    # 3. 构造 OpenAI 风格 chat body
    # 把 system_content 拼到 user 前面(复刻 hermes -q 模式)
    final_user = user_content if not system_content else (system_content + "\n\n" + user_content)
    body = {
        "model": model,
        "messages": [
            {"role": "user", "content": final_user},
        ],
        "stream": False,
        "temperature": 0.7,
    }
    body_bytes = json.dumps(body, ensure_ascii=False).encode("utf-8")

    # 4. 发送请求(走 env proxy,v0.7.8.11 已修 urllib 读 https_proxy 小写)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(
        endpoint,
        data=body_bytes,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": user_agent,
        },
        method="POST",
    )
    timeout = float(config.timeout_seconds)
    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
    except urllib.error.HTTPError as e:
        err_body = e.read()[:500].decode("utf-8", errors="replace")
        raise RuntimeError(
            f"LLM API HTTPError code={e.code}: {err_body}"
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"LLM API URLError: {e.reason}(检查代理/网络)"
        ) from e
    # 5. 解析响应
    resp_bytes = resp.read()
    try:
        resp_json = json.loads(resp_bytes.decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"LLM 响应非 JSON: {e}; 头 200 字节: {resp_bytes[:200]!r}") from e
    try:
        content = resp_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(
            f"LLM 响应格式不对: keys={list(resp_json.keys())}; err={e}"
        ) from e
    return content


def _build_hermes_call(
    config: Config,
    profile: str,
    data: str,
    instruction: str,
) -> "tuple[List[str], dict, Optional[Path]]":
    """构造 hermes CLI 调用参数 + env。

    协议: hermes.exe -p <profile> chat -q <prompt> --quiet
    崩溃防御: data > 20000 字符时把 data 写到临时文件，prompt 用 instruction
              + "请读取 <file>" 引用，hermes 用 read_file 工具自己读。
    关键: 临时文件**只写 data**（核心输入），不写 instruction（任务说明），
          这样 hermes 读文件时不会陷入"读到自己 prompt"的死循环。

    Returns:
        (args, env, tmp_file_or_None)
        - args: 传给 subprocess 的参数列表
        - env: 注入到子进程的环境变量
        - tmp_file: 超长时创建的临时文件，调用方负责删除
    """
    # v0.7.8.7:hermes 调用**始终**带 `-p <profile>`,让 hermes 走
    # `resolve_profile_env` 标准路径(`profiles.py:1896`)→ `get_default_hermes_root`
    # (`hermes_constants.py:113-150`)→ 读 env HERMES_HOME → 正确解析到
    # `<hermes_root>/profiles/<profile>`。
    #
    # 之前 v0.7.8.3 注释里"不传 -p"是误解:当时的理解是 hermes 走 -p 路径会
    # 硬编码用 C 盘 `~/.hermes`,忽略 manju 的 HERMES_HOME。**实际**现在的
    # `get_default_hermes_root()` 行 131-140 + 142-150 显式读 `os.environ["HERMES_HOME"]`,
    # 且当 HERMES_HOME 是 custom deployment(`<root>`,不是 `<root>/profiles/<name>`)
    # 时直接返回 HERMES_HOME 自己。
    # manju 的 `config.hermes_home` = `D:\漫剧助手\resources\hermes` (hermes root),
    # 走 `get_default_hermes_root()` → 返回 `D:\漫剧助手\resources\hermes` →
    # `_get_profiles_root()` = `<hermes_root>/profiles` →
    # `get_profile_dir("storyboard")` = `<hermes_root>/profiles/storyboard` ✓
    # (即 `config.hermes_home / "profiles" / profile`)
    #
    # 链路 = 标准 hermes 调用协议,不再依赖"HERMES_HOME 设成 profile_dir 让
    # parent.name=='profiles' 触发 main.py:444-456 信任分支"的 hack。
    base = [str(config.hermes_exe_path), "-p", profile, "chat"]
    # v0.7.8.17:用 PYTHONPATH 注入 sitecustomize,hook hermes 内部 aiohttp 让
    # ClientSession 默认 trust_env=True → hermes 调 LLM 时走 MANJU_PROXY。
    # 链路: manju → hermes.exe (PyInstaller) → embedded Python import
    # sitecustomize (PyInstaller 启动时 import sys.path 上的 sitecustomize.py)
    # → patch aiohttp.ClientSession.__init__ → hermes 调 LLM 时 aiohttp 读 env。
    # _hijack_dir 放 EXE 同目录(打包后 dist/漫剧助手X-1/hermes_hijack/)。
    # 源码运行也用 sys.executable.parent(就是 python 所在目录),所以从
    # main.py 把 ROOT 同步到 sys._manju_root 传过来更稳。
    import sys as _sys
    _root_dir = getattr(_sys, "_manju_root", None) or Path(_sys.executable).resolve().parent
    _hijack_dir = _root_dir / "hermes_hijack"
    env = {
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        # HERMES_HOME = hermes root (D:\漫剧助手\resources\hermes),不是 profile dir。
        # hermes 走 resolve_profile_env 路径会自己拼 `<root>/profiles/<profile>`。
        "HERMES_HOME": str(config.hermes_home),
        "PYTHONPATH": str(_hijack_dir),
    }
    # v0.7.8.15【诊断模式】:设 MANJU_PROXY=http://127.0.0.1:8888 时强制 hermes 走本地
    # logging proxy (diag_proxy.py),截获实际请求看 Cloudflare 403 怎么发生。
    # 关键:Python urllib 内部走 `urllib.request.getproxies()` 读**小写**
    # `http_proxy` / `https_proxy`,大写 `HTTPS_PROXY` 不会生效。
    # httpx 读 `HTTP_PROXY`/`HTTPS_PROXY`(大小写都看,小写优先)。
    # 浏览器/系统组件读大写。所以**大小写都设**。
    import os as _os
    _proxy_env = _os.environ.get("MANJU_PROXY")
    if _proxy_env:
        env["HTTPS_PROXY"] = _proxy_env
        env["HTTP_PROXY"] = _proxy_env
        env["HTTPX_PROXY"] = _proxy_env
        env["https_proxy"] = _proxy_env
        env["http_proxy"] = _proxy_env
        env["all_proxy"] = _proxy_env
        env["ALL_PROXY"] = _proxy_env
        _proxy_log = logging.getLogger("manju.generators")
        _proxy_log.info("hermes 通过代理 %s 调 LLM", _proxy_env)

    # v0.7.8.7:每次调 hermes 之前强制 inject 一次,确保 hermes 实际读到的
    # `<hermes_root>/profiles/<profile>/config.yaml` 必然是当前 active 配置。
    # inject 同步写 `model.*` / `providers[name]` / `custom_providers[name]` 三段
    # (v0.7.8.6 修的 custom_providers 段是 hermes `_seed_custom_pool` 实际
    # 读 key 的来源,见 `agent/credential_pool.py:2214` `_get_custom_provider_config`)。
    try:
        config.inject_api_to_profile(profile)
    except Exception as _inj_err:
        _log = logging.getLogger("manju.generators")
        _log.warning(
            "调 hermes 前 inject 失败 %s: %s（继续,hermes 会用 profile 自带配置）",
            profile, _inj_err,
        )

    if len(data) <= HERMES_ARGV_LIMIT_CHARS:
        # 短：直接拼
        if data:
            full_prompt = f"{instruction}\n\n{data}" if instruction else data
        else:
            full_prompt = instruction
        return base + ["-q", full_prompt, "--quiet"], env, None

    # 长：临时文件 + 短 prompt
    import tempfile
    tmp = Path(tempfile.gettempdir()) / (
        f"_manju_{profile}_{os.getpid()}.md"
    )
    tmp.write_text(data, encoding="utf-8")
    short_prompt = (
        f"{instruction}\n\n"
        f"请先完整读取文件 {tmp} 的内容（这是核心输入），然后按规范处理。"
    )
    return base + ["-q", short_prompt, "--quiet"], env, tmp


# ---------- StoryboardTask ----------

class StoryboardTask(Task):
    """调用 hermes.exe 生成剧集分镜。

    v0.6.17：完全复刻原软件 D:\\剧本分镜助手\\server.py:267 `build_storyboard_prompt`：
    - 接收 previous_summaries（续集上下文）、style_id、render_type
    - 输出固定以 "## 🎬 导演核算报告" 开头
    - 全中文输出，禁用 write_file 工具
    - 完成后用 `_filter_storyboard_output` 过滤推理块

    v0.6.28：移除 render_type 入参，直接从 `self._project.render_type` 读。
    style_id 同理统一从 project 读。

    构造签名跟 main_window 调用一致：(episode, project, config, parent=None,
        previous_summaries=None)
    """

    def __init__(
        self,
        episode,
        project,
        config: Config,
        parent: Any = None,
        output_dir: Optional[Path] = None,
        # v0.6.17 新参数
        previous_summaries: Optional[list] = None,
    ) -> None:
        super().__init__(name=f"分镜生成 #{episode.episode_num}", parent=parent)
        self._episode = episode
        self._project = project
        self._config = config
        self._output_dir = _safe_output_dir(config, output_dir)
        # v0.6.28：style_id / render_type 直接从项目级读
        style_id = getattr(project, "style_id", None) or None
        render_type = getattr(project, "render_type", None) or None
        # 内部转成 Request（run() 用到）
        self._request = StoryboardRequest(
            episode_id=episode.episode_num,
            episode_title=episode.title,
            synopsis=episode.script or "",  # 完整剧本，复刻原软件
            user_prompt="",
            previous_summaries=previous_summaries,
            style_id=style_id,
            render_type=render_type,
        )
        # run() 完后由 _persist_task_result 读这两个字段
        self.result_content: str = ""
        self._result_output_file: Optional[Path] = None
        # 内部 ManjuTask 引用，cancel 时用来调 mt.cancel() 把 SIGTERM 发给 hermes
        self._mt: Optional["ManjuTask"] = None

    def cancel(self) -> None:
        """v1.1.5【B5 修复】:覆写 base cancel,把 cancel 传给内部 ManjuTask。

        之前 v1.1.4 之前**漏了**这个 override → base Task.cancel() 只设
        _cancel_event(generators.py:104),mt.run() 是阻塞调用根本看不到,
        hermes 子进程永远不退出,user 点"取消"等满 7200s(2 小时)超时。

        对比 AssetExtractTask.cancel() (line 1135-1146) / VideoPromptTask
        .cancel() (line 661-670) 都有这个 override,只有 StoryboardTask 漏。
        """
        super().cancel()  # 仍设 _cancel_event(给业务层检查用)
        if self._mt is not None:
            try:
                self._mt.cancel()
            except Exception:
                pass

    def run(self) -> StoryboardResult:
        # v0.7.8.25:改回调 hermes storyboard profile(复刻老软件
        # D:\剧本分镜助手\server.py:267 run_storyboard_agent)。
        # v0.7.8.18 改 urllib 直连是错的——绕开 hermes 也绕开了
        # storyboard profile 的 SOUL.md + storyboard-script skill 的
        # 10 个 Phase 方法论/情绪节拍拆解/关键帧提取法,2 分钟出结果
        # 但分镜质量差很多(无方法论约束,user 报"看结果没调 agent")。
        # v0.7.8.23 已修 base_url /v1 后缀问题(hermes proxy 拼 URL 不会
        # 再 404),hermes storyboard profile 应该能跑通。失败时不兜底,
        # 直接抛 RuntimeError 给 UI。
        if self.is_cancelled:
            raise RuntimeError("cancelled before start")
        self.emit_progress("调用 hermes.exe（storyboard profile）生成分镜…")
        output_file = self._output_dir / f"storyboard_{self._request.episode_id}.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            raw_content = self._call_hermes_storyboard()
        except HermesCancelledError:
            raise
        except HermesTimeoutError:
            raise RuntimeError("分镜生成超时（超过配置秒数）")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"分镜生成失败：{e}") from e

        # hermes 走 stdout，自己写盘
        raw_content = raw_content or ""
        self.emit_output(raw_content[:200] + ("..." if len(raw_content) > 200 else ""))
        # v0.6.17：用 _filter_storyboard_output 过滤推理块，
        # 找 "## 🎬 导演核算报告" 行为起点（复刻自 server.py:338）
        content = _filter_storyboard_output(raw_content)
        output_file.write_text(content, encoding="utf-8")

        # 暴露给 _persist_task_result 读
        self.result_content = content
        self._result_output_file = output_file
        return StoryboardResult(output_file=output_file, content=content)

    def _call_hermes_storyboard(self) -> str:
        """调 hermes storyboard profile，复刻老软件 server.py:1360-1377
        的 0xC0000005 段错误自动重试。

        跟 VideoPromptTask._call_hermes_with_retry 结构完全一样，
        profile 改 "storyboard"、user_agent 改 "manju/0.7.8.25"。
        失败时不兜底——直接抛 RuntimeError，UI 弹错误对话框告诉用户
        具体原因（403 / 段错误 / 其他）。
        """
        import time as _time
        mt: Optional[ManjuTask] = None
        self._mt = None  # 给 cancel() 引用
        try:
            profile = self._config.profile_for("storyboard")
        except (KeyError, ConfigError) as e:
            raise RuntimeError("未注册 storyboard profile") from e

        # data=完整剧本,instruction=整个 build_storyboard_prompt
        # 复刻自 server.py:267-312
        r = self._request
        data = r.synopsis
        instruction = self._build_prompt()

        args, env, _ = _build_hermes_call(
            self._config, profile, data, instruction,
        )
        cwd = Path.home()
        timeout = float(self._config.timeout_seconds)
        MAX_RETRIES = 2
        last_err: Optional[str] = None
        result: Optional[RunResult] = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                mt = ManjuTask(args=args, cwd=cwd, env=env, timeout=timeout)
                self._mt = mt  # cancel 透传
                result = mt.run(on_output=lambda line: self.emit_output(line))
                if result.returncode not in (3221225477, 0xC0000005):
                    break
                last_err = (
                    f"hermes.exe 段错误 (returncode={result.returncode},"
                    f" attempt={attempt}/{MAX_RETRIES})"
                )
                logging.getLogger("manju.generators").warning(
                    "%s,等待 3s 后重试", last_err,
                )
                _time.sleep(3)
            except HermesCancelledError:
                raise
            except HermesTimeoutError:
                raise
            except Exception as e:
                raise RuntimeError(f"启动 hermes 失败：{e}") from e
            finally:
                self._mt = None
        if result is None:
            raise RuntimeError(f"hermes 未返回结果：{last_err or '未知'}")
        if result.returncode in (3221225477, 0xC0000005):
            extra = (result.output or "").strip()[:500]
            raise RuntimeError(
                f"hermes.exe 段错误 (returncode=0xC0000005)，{MAX_RETRIES} 次后仍失败；"
                f"stderr/output: {extra}"
            )
        if result.returncode != 0:
            extra = (result.output or "").strip()[:500]
            raise RuntimeError(
                f"hermes.exe exit {result.returncode}：{extra}"
            )
        return result.output or ""

    # ---------- 内部 ----------

    def _build_prompt(self) -> str:
        """v0.6.17：完全用原软件 build_storyboard_prompt 复刻。"""
        r = self._request
        return build_storyboard_prompt(
            script=r.synopsis,
            previous_summaries=r.previous_summaries,
            style_id=r.style_id,
            render_type=r.render_type,
        )

    def _build_manju_task(self, output_file: Path) -> "tuple[ManjuTask, Optional[Path]]":
        try:
            profile = self._config.profile_for("storyboard")
        except (KeyError, ConfigError) as e:
            raise RuntimeError("未注册 storyboard profile") from e

        r = self._request
        # v0.6.17：data = 完整剧本（不是简介）；instruction = 整个 build_storyboard_prompt
        # 复刻自 server.py:267-312
        data = r.synopsis  # 完整剧本
        instruction = self._build_prompt()  # 整个 prompt（含 style/render/前序摘要/中文强制）

        args, env, tmp_file = _build_hermes_call(
            self._config, profile, data, instruction
        )
        mt = ManjuTask(
            args=args,
            cwd=Path.home(),
            env=env,
            timeout=float(self._config.timeout_seconds),
        )
        return mt, tmp_file


# ---------- VideoPromptTask ----------

class VideoPromptTask(Task):
    """调用 hermes.exe（seedance-prompt）生成分镜对应的视频 prompt。

    v0.6.17：完全复刻原软件 D:\\剧本分镜助手\\server.py:1291 `run_seedance_agent`
    的 prompt 构造部分（**不**含 subprocess.run / 队列，那些走 manju 自己的
    TaskQueue）：
    - 注入【项目资产】块（来自 v0.6.16 的 AssetExtractTask.result_asset_list）
    - 注入 style_id / render_type
    - 全中文输出，运镜术语保留英文
    - 严格 Director Angel 编译格式（导演核算报告 + Segment 矩阵）
    - 长 storyboard（>20000 字符）走临时文件，hermes 用 read_file 工具读

    v0.6.28：移除 style_id / render_type 入参，统一从 project 读。

    构造签名跟 main_window 调用一致：
    (episode, project, config, parent=None, asset_names="", output_dir=None)
    """

    def __init__(
        self,
        episode,
        project,
        config: Config,
        parent: Any = None,
        output_dir: Optional[Path] = None,
        # v0.6.17 新参数
        asset_names: str = "",
    ) -> None:
        super().__init__(name=f"视频 Prompt #{episode.episode_num}", parent=parent)
        self._episode = episode
        self._project = project
        # v0.6.28：style_id / render_type 直接从项目级读
        style_id = getattr(project, "style_id", None) or None
        render_type = getattr(project, "render_type", None) or None
        self._request = VideoPromptRequest(
            episode_id=episode.episode_num,
            episode_title=episode.title or f"第{episode.episode_num}集",
            storyboard_text=episode.storyboard or "",
            asset_names=asset_names,
            style_id=style_id,
            render_type=render_type,
            user_prompt="",
        )
        self._config = config
        self._output_dir = _safe_output_dir(config, output_dir)
        # v0.6.17：长 storyboard 临时文件句柄（run 完后清理）
        self._seedance_tmp_file: Optional[Path] = None
        # 内部 ManjuTask 引用，cancel 时用来调 mt.cancel() 把 SIGTERM 发给 hermes
        # v0.7.8.22 恢复 hermes 调用,需要这个引用做 cancel 透传
        self._mt: Optional[ManjuTask] = None
        # _persist_task_result 读 result_content
        self.result_content: str = ""
        self._result_output_file: Optional[Path] = None

    def cancel(self) -> None:
        """覆写 base cancel:把 cancel 信号传给内部 ManjuTask,让 hermes 子进程被 SIGTERM。

        复刻 AssetExtractTask.cancel() 范式(server.py 1307 hermes 子进程也走这套)。
        """
        super().cancel()
        if self._mt is not None:
            try:
                self._mt.cancel()
            except Exception:
                pass


    def run(self) -> VideoPromptResult:
        # v0.7.8.22:恢复调 hermes seedance-prompt profile,复刻老软件 D:\剧本分镜助手\server.py:1291
        # `run_seedance_agent`。v0.7.8.18 改成 manju urllib 直连是错的,user 明确要求
        # 走 hermes 子进程。
        if self.is_cancelled:
            raise RuntimeError("cancelled before start")
        self.emit_progress("调用 hermes.exe 生成视频 prompt…")
        output_file = self._output_dir / f"video_prompt_{self._request.episode_id}.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # 构造 prompt(完整 seedance prompt 模板,复刻原软件 build_seedance_prompt)
        prompt, sb_tmp_path = self._build_prompt()
        if sb_tmp_path:
            self._seedance_tmp_file = Path(sb_tmp_path)

        try:
            # 复刻老软件 server.py:1363-1377 0xC0000005 段错误自动重试
            content = self._call_hermes_with_retry(prompt)
        finally:
            # 清理长 storyboard 临时文件
            if self._seedance_tmp_file and self._seedance_tmp_file.exists():
                try:
                    self._seedance_tmp_file.unlink()
                except OSError:
                    pass
                self._seedance_tmp_file = None

        # hermes 走 stdout，自己写盘
        self.emit_output(content[:200] + ("..." if len(content) > 200 else ""))
        output_file.write_text(content, encoding="utf-8")

        self.result_content = content
        self._result_output_file = output_file
        return VideoPromptResult(output_file=output_file, content=content)

    def _call_hermes_with_retry(self, prompt: str) -> str:
        """复刻老软件 server.py:1360-1377 的 0xC0000005 段错误自动重试。

        hermes.exe 跑长文本可能撞 STATUS_ACCESS_VIOLATION (0xC0000005),
        Python 抓不到,只能从 returncode 判断 → 自动重试一次。

        v0.7.8.73 新增【对话式收尾自动续接】:SKILL v2.10.0 升级后
        LLM 走 16+ API call,在 context 接近极限时 LLM 走"对话式收尾",
        用 776 chars 英文"how would you like to proceed"收尾,而不是
        输出完整 23 段中文提示词。检测到这种收尾后,自动用
        `hermes chat --resume <session_id> -q "<续接 prompt>" --quiet`
        续接,要求 LLM 重写完整 23 段。

        v0.7.8.74 扩成 2 种收尾:对话式收尾 + inline tool call 收尾。

        v0.7.8.76 新增【诚实截断自动续接】:SKILL v2.10.1 line 562 写明
        长剧本会超 agent.max_tokens(默认 16000)被截断。23:50 session
        实际产物:11309 chars 30 段拆得对但 LLM 诚实声明"因单次输出受限,
        本次完整输出前 12 个核心 Segment",后 18 段没出。manju 端
        检测到这种"诚实截断"后,自动 --resume 续接,prompt 自适应
        写出"从第 N+1 段开始,补完剩余 M-N 段,前 N 段不要重复"。

        流程层修复,不约束 agent 行为(没告诉 LLM 怎么拆段 / 5 镜限制
        / 违规词替代等),只是 manju 调 hermes 时多一层检测 + 续接。
        """
        import re as _re
        try:
            profile = self._config.profile_for("video_prompt")
        except (KeyError, ConfigError) as e:
            raise RuntimeError("未注册 video_prompt profile") from e

        args, env, _ = _build_hermes_call(self._config, profile, prompt, "")
        cwd = Path.home()
        timeout = float(self._config.timeout_seconds)
        MAX_RETRIES = 2
        MAX_RESUME_ROUNDS = 3  # 续接最多 3 次,防止无限循环

        # 第一次跑 hermes(可能撞段错误,内部已自动重试)
        output = self._run_hermes_once(args, cwd, env, timeout, MAX_RETRIES)
        session_id = self._extract_session_id(output)

        # 收尾检测循环:对话式 / inline tool call / 诚实截断,3 种都走 --resume 续接
        for round_idx in range(1, MAX_RESUME_ROUNDS + 1):
            kind, info = self._classify_ending(output)
            if kind == "complete":
                break
            if not session_id:
                logging.getLogger("manju.generators").warning(
                    "hermes 似乎 %s 收尾但没拿到 session_id,放弃续接", kind,
                )
                break

            if kind == "dialogue":
                # v0.7.8.73 原 prompt:重写完整 23 段
                resume_prompt = (
                    "请把完整 23 段中文提示词重新写一次,从第 1 段开始,直到 "
                    "Segment 23。每段必须包含完整结构:Asset Definitions、"
                    "Global Style、Base Compiled Prompt、Director's Shot "
                    "Matrix、Native Audio。"
                    "**不要调任何工具(包括 read_file / terminal / "
                    "execute_code),不要在回复正文中用 ```python 或 ```text "
                    "code block,直接在文字里输出完整 23 段。**"
                    "不要分多轮,不要再次询问我,不要重新读文件。"
                )
            else:  # truncation
                # v0.7.8.76 自适应 prompt:从已输出段的下一段开始,补完剩余
                total = info["total"]
                done = info["done"]
                next_start = info["next_start"]
                remaining = info["remaining"]
                resume_prompt = (
                    f"你刚才输出了前 {done} 段(总共需要 {total} 段),"
                    f"还有 {remaining} 段没出(从 Segment {next_start} 到 "
                    f"Segment {total})。"
                    f"请从 Segment {next_start} 开始,把剩余 {remaining} 段 "
                    f"完整输出。每个 Segment 包含完整结构:Asset Definitions、"
                    f"Global Style、Base Compiled Prompt、Director's Shot "
                    f"Matrix、Native Audio。"
                    f"**不要重新输出前 {done} 段的内容,不要调任何工具(包括 "
                    f"read_file / terminal / execute_code),不要在回复正文中用 "
                    f"```python 或 ```text code block,直接在文字里输出剩余 "
                    f"{remaining} 段。**"
                    f"不要分多轮,不要再次询问我,不要重新读文件。"
                )

            resume_args = [
                str(self._config.hermes_exe_path),
                "-p", profile,
                "chat",
                "--resume", session_id,
                "-q", resume_prompt,
                "--quiet",
            ]
            log_extra = ""
            if kind == "truncation":
                log_extra = (
                    f",已输 {info['done']}/{info['total']} 段"
                    f"(还剩 {info['remaining']} 段)"
                )
            logging.getLogger("manju.generators").info(
                "检测到 hermes %s 收尾(round=%d, sid=%s%s),自动 --resume 续接",
                kind, round_idx, session_id, log_extra,
            )
            output = self._run_hermes_once(resume_args, cwd, env, timeout, MAX_RETRIES)
            # 续接后 session_id 还是同一个(hermes --resume 复用 id),
            # 但保险起见重新解析
            new_sid = self._extract_session_id(output)
            if new_sid:
                session_id = new_sid

        return output

    @staticmethod
    def _classify_ending(output: str) -> "tuple[str, dict]":
        """v0.7.8.76:统一分类 hermes 收尾类型。

        Returns:
            ("complete", {}) — response 完整,不需要续接
            ("dialogue", {}) — 对话式收尾 / inline tool call 收尾(v0.7.8.73/74)
            ("truncation", {"total": N, "done": K, "next_start": K+1, "remaining": N-K})
                          — 诚实截断收尾(v0.7.8.76,LLM 声明已输 K/共 N 段)
        """
        if VideoPromptTask._is_dialogue_ending(output):
            return "dialogue", {}
        is_trunc, info = VideoPromptTask._is_truncation_ending(output)
        if is_trunc:
            return "truncation", info
        return "complete", {}

    @staticmethod
    def _extract_session_id(output: str) -> Optional[str]:
        """从 hermes stdout 解析 session_id 行(hermes -q --quiet 退出时
        会写 `\nsession_id: <id>` 到 stderr,合并到 stdout 后是同一行)。"""
        import re as _re
        if not output:
            return None
        m = _re.search(r"session_id:\s*(\S+)", output)
        return m.group(1).strip() if m else None

    @staticmethod
    def _is_dialogue_ending(output: str) -> bool:
        """判断 hermes response 是不是"对话式收尾"或"inline tool call 收尾"。

        21:38 session 实际产物:776 chars 英文 "I have successfully
        received... how would you like to proceed with this data—should
        we continue reading the rest of the file...?"  → 对话式收尾

        22:30 session 实际产物:882 chars 4 个 inline code block
        ```python?code_reference&code_event_index=2 ... ``` +
        ```text?code_stdout&code_event_index=2 File does not exist ```
        → LLM 把 final_response 当 inline tool call 用,hermes 不解析
        当工具调用,只 dump 给 manju,**0 chars 23 段中文**

        判定条件(任一命中即视为收尾):
        1. response 短(< 4000 chars,完整 23 段通常 6000-10000 chars)
        2. 不含 SKILL 输出关键字("Segment" / "🎞️" / "Asset Definitions" /
           "Global Style" / "Director's Shot Matrix" / "Native Audio" /
           "Base Compiled Prompt")
        3. 含对话式收尾语(英文/中文) **OR** 含 hermes inline code block
           标记("code_reference" / "code_stdout",LLM 在文本里塞了
           inline tool call 块)
        """
        import re as _re
        if not output:
            return False
        # 去掉 session_id 行,只判 response 文本
        text = _re.sub(r"\n*session_id:\s*\S+", "", output).strip()
        if len(text) > 4000:
            return False
        # SKILL 期望的 23 段结构关键字(任何一个出现就说明 LLM 出了真内容)
        skill_keywords = [
            "Segment",
            "🎞️",
            "Asset Definitions",
            "Global Style",
            "Director's Shot Matrix",
            "Native Audio",
            "Base Compiled Prompt",
        ]
        if any(kw in text for kw in skill_keywords):
            return False
        # 对话式收尾语(英文/中文)
        dialogue_patterns = [
            r"how would you like",
            r"would you like me",
            r"do you want me",
            r"shall I continue",
            r"should I continue",
            r"want me to",
            r"想要我继续|要不要继续|是否继续|你想|要我继续",
        ]
        for pat in dialogue_patterns:
            if _re.search(pat, text, _re.IGNORECASE):
                return True
        # Inline tool call 收尾(LLM 用 final_response 调 terminal 工具,
        # hermes 端不解析为工具调用,只 dump 文本)
        # 标志:含 hermes-internal code block 标记
        inline_tool_patterns = [
            r"```python\?code_reference",
            r"```python\?code_event_index",
            r"```text\?code_stdout",
            r"```text\?code_event_index",
        ]
        for pat in inline_tool_patterns:
            if _re.search(pat, text):
                return True
        return False

    @staticmethod
    def _is_truncation_ending(output: str) -> "tuple[bool, dict]":
        """v0.7.8.76:检测 hermes response 是不是"诚实截断"收尾。

        SKILL v2.10.1 line 562 写明:长剧本会超 agent.max_tokens(默认
        16000)被截断。23:50 session 实际产物:11309 chars 30 段拆得对
        但 LLM 诚实声明"因单次输出受限,本次完整输出前 12 个核心 Segment"
        + 审查里写"对话全部到位(含后续段落预留)"。后 18 段没出。

        manju 端**不**改 hermes 配置(不调 max_tokens),改在流程层:
        检测到截断后自动 --resume 续接,prompt 自适应写"从第 N+1 段
        开始,补完剩余 M-N 段,前 N 段不要重复"。

        判定条件(全部命中才视为截断):
        1. response 长度 ≤ 25000 chars(超过说明 LLM 真的输完了)
        2. 含 SKILL 关键字("Segment"/"🎞️"/"Asset Definitions"/
           "Director's Shot Matrix"),说明 LLM 出了真内容
        3. 含 "拆分为 N 个 Segment"/"拆成 N 个 Segment"/"分为 N 个
           Segment"(LLM 声明总段数)
        4. 含 "完整输出前 K 个"/"输出前 K 个核心 Segment"(LLM 声明
           已输出数)
        5. K < N(确实还有剩余)

        Returns:
            (True, {"total": N, "done": K, "next_start": K+1,
                    "remaining": N-K}) — 截断,需续接
            (False, {}) — 不算截断
        """
        import re as _re
        if not output:
            return False, {}
        text = _re.sub(r"\n*session_id:\s*\S+", "", output).strip()
        # 1. 太长说明 LLM 真的输完了(完整 30 段约 25000+ chars)
        if len(text) > 25000:
            return False, {}
        # 2. 必须含 SKILL 关键字,说明 LLM 出了真内容(否则该走 dialogue 分支)
        skill_keywords = [
            "Segment", "🎞️", "Asset Definitions", "Director's Shot Matrix",
        ]
        if not any(kw in text for kw in skill_keywords):
            return False, {}
        # 3. 提取总段数
        total_patterns = [
            r"拆分为\s*(\d+)\s*个\s*Segment",
            r"拆成\s*(\d+)\s*个\s*Segment",
            r"分为\s*(\d+)\s*个\s*Segment",
            r"(\d+)\s*个\s*Segment",
        ]
        total = None
        for pat in total_patterns:
            m = _re.search(pat, text)
            if m:
                try:
                    total = int(m.group(1))
                    break
                except (ValueError, IndexError):
                    continue
        if total is None or total <= 0:
            return False, {}
        # 4. 提取已输出数
        done_patterns = [
            r"完整输出前\s*(\d+)\s*个",
            r"输出前\s*(\d+)\s*个",
            r"本次.{0,8}前\s*(\d+)\s*个",
            r"前\s*(\d+)\s*个.{0,4}Segment",
        ]
        done = None
        for pat in done_patterns:
            m = _re.search(pat, text)
            if m:
                try:
                    done = int(m.group(1))
                    break
                except (ValueError, IndexError):
                    continue
        if done is None or done <= 0:
            return False, {}
        # 5. 必须 done < total
        if done >= total:
            return False, {}
        return True, {
            "total": total,
            "done": done,
            "next_start": done + 1,
            "remaining": total - done,
        }

    def _run_hermes_once(
        self,
        args: list,
        cwd: "Path",
        env: dict,
        timeout: float,
        max_retries: int,
    ) -> str:
        """单次跑 hermes(可能内部自动重试 0xC0000005 段错误)。

        返回 hermes stdout 完整内容(已经 rstrip 末尾空白)。
        """
        import time as _time
        last_err: Optional[str] = None
        result: Optional[RunResult] = None
        for attempt in range(1, max_retries + 1):
            try:
                mt = ManjuTask(args=args, cwd=cwd, env=env, timeout=timeout)
                self._mt = mt  # cancel 透传
                result = mt.run(on_output=lambda line: self.emit_output(line))
                if result.returncode not in (3221225477, 0xC0000005):
                    break
                last_err = (
                    f"hermes.exe 段错误 (returncode={result.returncode},"
                    f" attempt={attempt}/{max_retries})"
                )
                logging.getLogger("manju.generators").warning(
                    "%s,等待 3s 后重试", last_err,
                )
                _time.sleep(3)
            except HermesCancelledError:
                raise
            except HermesTimeoutError:
                raise RuntimeError("提示词生成超时(超过配置秒数)")
            except Exception as e:
                raise RuntimeError(f"启动 hermes 失败:{e}") from e
            finally:
                self._mt = None
        if result is None:
            raise RuntimeError(f"hermes 未返回结果:{last_err or '未知'}")
        if result.returncode in (3221225477, 0xC0000005):
            extra = (result.output or "").strip()[:500]
            raise RuntimeError(
                f"hermes.exe 段错误 (returncode=0xC0000005),{max_retries} 次后仍失败;stderr/output: {extra}"
            )
        if result.returncode != 0:
            extra = (result.output or "").strip()[:500]
            raise RuntimeError(
                f"hermes.exe exit {result.returncode}: {extra}"
            )
        return result.output or ""

    # ---------- 内部 ----------

    def _build_prompt(self) -> Tuple[str, Optional[Path]]:
        """v0.6.17：完全用原软件 build_seedance_prompt 复刻。

        Returns:
            (prompt_text, tmp_sb_file_path_or_None)
        """
        r = self._request
        return build_seedance_prompt(
            episode_title=r.episode_title,
            storyboard=r.storyboard_text,
            asset_names=r.asset_names,
            style_id=r.style_id,
            render_type=r.render_type,
        )

    def _build_manju_task(
        self, output_file: Path,
    ) -> "tuple[ManjuTask, Optional[Path], Optional[Path]]":
        try:
            profile = self._config.profile_for("video_prompt")
        except (KeyError, ConfigError) as e:
            raise RuntimeError("未注册 video_prompt profile") from e

        # v0.6.17：直接拿 build_seedance_prompt 返回的 prompt + 临时文件
        prompt, sb_tmp_path = self._build_prompt()
        if sb_tmp_path:
            self._seedance_tmp_file = Path(sb_tmp_path)

        # 把 prompt 直接喂 hermes（不再用 _build_hermes_call 的"data + instruction"双段）
        args, env, tmp_file = _build_hermes_call(self._config, profile, prompt, "")
        mt = ManjuTask(
            args=args,
            cwd=Path.home(),
            env=env,
            timeout=float(self._config.timeout_seconds),
        )
        return mt, tmp_file, self._seedance_tmp_file


# ---------- AssetExtractTask ----------

class AssetExtractTask(Task):
    """调用 hermes.exe（asset-designer）从项目下所有剧集的分镜抽取资产清单。

    构造签名跟 asset_panel 调用一致：(project, episodes, config, parent=None)
    """

    def __init__(
        self,
        project,
        episodes: List,
        config: Config,
        parent: Any = None,
        output_dir: Optional[Path] = None,
    ) -> None:
        super().__init__(name=f"资产抽取 · {project.name}", parent=parent)
        self._project = project
        self._episodes = list(episodes)
        self._config = config
        self._output_dir = _safe_output_dir(config, output_dir)
        # 内部 request（run() 用到 episode_id + storyboard_text；项目级就取第一个有分镜的）
        self._request = AssetExtractRequest(
            episode_id=project.id,
            storyboard_text="\n\n".join(
                f"## {ep.title}\n{ep.storyboard or ''}"
                for ep in self._episodes if ep.storyboard
            ),
            user_prompt="",
        )
        # _persist_task_result 读：[(kind, name, desc), ...]
        self.result_assets: List[Any] = []
        # v0.6.16：资产名列表（人/场/物三段纯文本）
        self.result_asset_list: str = ""
        self._result_output_file: Optional[Path] = None
        # 内部 ManjuTask 引用，cancel 时用来调 mt.cancel() 把 SIGTERM 发给 hermes
        self._mt: Optional["ManjuTask"] = None

    def cancel(self) -> None:
        """覆写 base cancel：把 cancel 信号传给内部 ManjuTask，让 hermes 子进程被 SIGTERM。

        **之前 v0.6.8 漏了** → base Task.cancel() 只设 _cancel_event，mt.run() 是
        阻塞调用根本看不到，hermes 子进程永远不退出，用户点取消"没反应"。
        """
        super().cancel()  # 仍设 _cancel_event（给业务层检查用）
        if self._mt is not None:
            try:
                self._mt.cancel()
            except Exception:
                pass

    def run(self) -> AssetExtractResult:
        # 先看用户有没有在构造到执行这段窗口里点取消
        if self.is_cancelled:
            raise RuntimeError("cancelled before start")
        self.emit_progress("调用 hermes.exe 抽取资产…")
        output_file = self._output_dir / f"assets_{self._project.id}.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # v0.7.3：完全走 hermes stdout 复刻原软件行为，删 v0.6.15 救回机制
        # 老软件没让 hermes 写盘；manju 也不再写 hermes_output_path
        mt, tmp_file = self._build_manju_task(output_file)

        self._mt = mt  # 存引用，cancel() 要用
        content = ""
        try:
            result = mt.run(on_output=lambda line: self.emit_output(line))
            content = result.output or ""
        finally:
            self._mt = None
            if tmp_file and tmp_file.exists():
                try:
                    tmp_file.unlink()
                except OSError:
                    pass

        # 写最终结果
        output_file.write_text(content, encoding="utf-8")

        # 解析 hermes 输出的 markdown → 资产清单
        # parser 返回 [(kind, name, desc), ...]，见 core/asset_parser.py
        parsed = parse_asset_markdown(content)
        self._result_output_file = output_file
        self.result_assets = list(parsed)

        # v0.6.17：把 LLM 输出的中文 8 段 bullet 用 convert_to_standard_format
        # 转成英文 dot-separated 格式，复刻自 server.py:883-912
        # 生图时直接用转换后的英文版本（dreamina 调通的格式）
        converted_content = convert_to_standard_format(content)
        # 同时写一份 converted 版本到 output_file（覆盖原 LLM 输出）
        # 这样 outputs/<project_id>_extracted_assets.md 就是英文 dot-separated
        # 格式，AssetImageTask 直接读
        converted_output_file = self._output_dir / f"assets_{self._project.id}_standard.md"
        try:
            converted_output_file.write_text(converted_content, encoding="utf-8")
            logging.getLogger("manju.asset_extract").info(
                "convert_to_standard_format 已写到 %s", converted_output_file,
            )
        except OSError as e:
            logging.getLogger("manju.asset_extract").warning(
                "写 standard 文件失败 %s: %s", converted_output_file, e,
            )

        # **v0.6.16**：从同一份 content 抽资产名列表（人/场/物三段），
        # 写到 outputs/<project_id>_asset_list.txt 供下游 video prompt agent
        # 使用。原软件 D:\剧本分镜助手\server.py:1307-1310 把这列表注入
        # seedance prompt 上下文；本软件先在 UI "📋 复制资产列表" 按钮暴露。
        asset_list_text = format_asset_list_text(content)
        self.result_asset_list = asset_list_text
        list_file: Optional[Path] = None
        if asset_list_text:
            list_file = list_file_path(self._output_dir, self._project.id)
            try:
                list_file.parent.mkdir(parents=True, exist_ok=True)
                list_file.write_text(asset_list_text, encoding="utf-8")
                logging.getLogger("manju.asset_extract").info(
                    "资产列表已写到 %s (len=%d)", list_file, len(asset_list_text)
                )
            except OSError as e:
                logging.getLogger("manju.asset_extract").warning(
                    "写资产列表文件失败 %s: %s", list_file, e
                )
                list_file = None
        else:
            logging.getLogger("manju.asset_extract").warning(
                "asset_cache 没解析到任何资产名，资产列表为空"
            )

        return AssetExtractResult(
            output_file=output_file,
            content=content,
            assets=parsed,
            asset_list=asset_list_text,
            asset_list_file=list_file,
        )

    def _build_manju_task(
        self, output_file: Path
    ) -> "tuple[ManjuTask, Optional[Path]]":
        try:
            profile = self._config.profile_for("asset")
        except (KeyError, ConfigError) as e:
            raise RuntimeError("未注册 asset profile") from e

        # v0.7.3：完全复刻原软件 D:\剧本分镜助手\server.py:359-378 `build_project_asset_prompt`。
        # 关键点：
        # - 标题行："请提取以下剧本的全局资产清单..."
        # - 【渲染类型指定】用 RENDER_TYPES 字典 name+category+"指令词中的渲染标签必须匹配此类型"
        # - 【视觉风格指定】用 STYLES 字典 name+en+guidance（v0.7.3 新增，老软件没注入）
        # - 【重要规则】3 条
        # - 完整剧本内容直接拼（< 20000 字符时）；> 20000 字符时写 temp 文件 + "请读取"
        # - 末尾 "请严格按照 script-asset-designer skill 的格式输出。"
        # - **不**加 manju 之前自己写的硬约束（中文 8 段 bullet 模板、write_file 硬约束、严格遵守）

        # v0.7.3：data 改用完整剧本（script 字段），不是分镜。复刻原软件
        # 老软件 server.py 把"剧本"(episodes.script)拼一起
        # script 字段在 ep.script 已有,可能为空字符串
        data = "\n\n".join(
            f"【第{ep.episode_num}集「{ep.title}」】\n第{ep.episode_num}集：{ep.title or ''}\n{ep.script or ''}"
            for ep in self._episodes
        )

        # v0.7.3：v0.6.15 救回机制已废弃 — 老软件走 stdout 直接返回
        # 救回逻辑改在 main_window 层(检测 task 是否异常后查 db)
        # 不再需要 hermes_output_path 写盘硬约束

        # 用 build_project_asset_prompt 拼完整 prompt（含 style/render/规则/剧本/末尾）
        # 绕开 _build_hermes_call 的 data+instruction 二次拼接
        full_prompt, tmp_script_file = build_project_asset_prompt(
            script_text=data,
            style_id=getattr(self._project, "style_id", "") or None,
            render_type=getattr(self._project, "render_type", "") or None,
            project_name=self._project.name or "",
        )

        # 直接构造 hermes args（不复用 _build_hermes_call，因为它会把 data 拼到 instruction 后）
        base = [str(self._config.hermes_exe_path), "-p", profile, "chat"]
        # v0.7.6：同 _build_hermes_call 链路，manju 调 hermes 前 inject active
        # model/api_key 到 manju 自带 profile config.yaml（不然 hermes 用 D 盘
        # 复制过来的 config.yaml 默认 model，跑出来跟用户 active 不一致）。
        try:
            self._config.ensure_local_hermes_profile(profile)
            self._config.inject_api_to_profile(profile)
        except Exception as _e:
            import logging
            logging.getLogger("manju.gen").warning(
                "AssetExtractTask v0.7.6 启动前 inject_api 失败: %s", _e,
            )
        env = {
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            # v0.7.6：HERMES_HOME 现在指向 manju 自带 resources/hermes
            # （D 盘资源已在启动时同步进来）。manju 跟老 software 跑 hermes
            # 时加载的 SKILL.md / SOUL.md / config.yaml 完全一致 → LLM 输出
            # manju parser 能解析的格式。
            "HERMES_HOME": str(self._config.hermes_home),
        }
        args = base + ["-q", full_prompt, "--quiet"]
        tmp_file = Path(tmp_script_file) if tmp_script_file else None

        mt = ManjuTask(
            args=args,
            cwd=Path.home(),
            env=env,
            timeout=float(self._config.timeout_seconds),
        )
        # v0.7.3：返回 2-tuple（mt, tmp_file），去掉 hermes_output_path
        # 老软件走 stdout，manju 也不再用 write_file 救回
        return mt, tmp_file

    def _build_prompt(self) -> str:
        r = self._request
        lines: List[str] = [
            "【分镜内容】",
            r.storyboard_text,
            "",
        ]
        if r.user_prompt:
            lines.append(f"【附加要求】{r.user_prompt}")
        lines.extend([
            "请抽取本集中出现的人物 / 场景 / 道具，输出 markdown：",
            "1. 标题用 ## 角色 / ## 场景 / ## 道具",
            "2. 每条资产给：名称、外观/特征描述、出现镜头编号",
            "3. 末尾附 ```json 围栏，结构：",
            "   {",
            '     "characters": [{"name": "...", "desc": "...", "shots": [1,2]}],',
            '     "scenes":     [{"name": "...", "desc": "...", "shots": [1,2]}],',
            '     "props":      [{"name": "...", "desc": "...", "shots": [1,2]}]',
            "   }",
        ])
        return "\n".join(lines)


# ---------- AssetImageTask ----------

def _run_one_asset_image(
    asset,
    project,
    config: "Config",
    output_dir: Path,
    cancel_check,
    on_output,
) -> tuple:
    """v0.6.26：单张资产生图的实际工作（提取出来给 AssetImageTask 和 BatchAssetImageTask 共用）。
    v0.7.7：改用 ImageApiRunner（HTTP /v1/images/generations，OpenAI 兼容）替代 dreamina.exe subprocess。

    Args:
        asset: Asset dataclass
        project: Project dataclass
        config: Config 单例
        output_dir: 输出根目录（_safe_output_dir 已算好的）
        cancel_check: callable() -> bool，外部 cancel 时返回 True
        on_output: callable(str)，透传生图 API 调试日志

    Returns:
        (image_path: str, prompt: str)

    Raises:
        RuntimeError: 生图 API 失败（HTTP 非 200 / 响应里没图片 / 异常）
    """
    # v0.7.7：保存路径对齐老 software server.py:1856-1857：
    # `outputs/<safe_proj>/assets/<safe_asset>/<safe_asset>_<ts>.png`
    # — 每个资产一个子文件夹，允许多张历史图共存（按时间戳区分）。
    # 之前 manju 写扁平 `asset_0_{kind}_{name}.png`，浏览历史找不到。
    from datetime import datetime as _dt_img
    from core.asset_browser import safe_asset_dir_name
    safe_proj = _sanitize_filename(project.name if project else "") or "default"
    safe_asset_name = _sanitize_filename(asset.name) or f"asset_{asset.id}"
    asset_dir = output_dir / safe_proj / "assets" / safe_asset_dir_name(asset.name)
    asset_dir.mkdir(parents=True, exist_ok=True)
    ts = _dt_img.now().strftime("%Y%m%d_%H%M%S")
    out = asset_dir / f"{safe_asset_name}_{ts}.png"

    # v0.7.7 重打 8（user 大骂版）：按 user 要求全部简化——
    # 1. 删兜底：image_prompt 才是源头，description 不参与生图
    # 2. 删翻译：image_prompt 编辑框里的内容（中文或英文随 user）原封不动发给 API
    #    （user 原话："发给api的就这里面的词就行了翻译什么？
    #      你就把这里的词原封不懂的发给api就行了"）
    # 3. 资产提取时 image_prompt = description 里"中文指令词"段（asset_parser 已实现）
    prompt = (getattr(asset, "image_prompt", "") or "").strip()

    # v1.1.5【C4 修复】:之前空 prompt 直接发给 API,各家行为不一致
    # (有的返回 400 报错,有的返回透明图,有的随机发挥)。修法:在源头
    # 直接抛 RuntimeError,UI 弹"该资产 image_prompt 为空,请先在资产
    # 列表里补全"提示。BatchAssetImageTask 会把这个资产计入 failures
    # (line 1602-1614 的 try/except 已经接住,会自动计入 result_failures)。
    if not prompt:
        raise RuntimeError(
            f"资产「{asset.name}」的 image_prompt 为空,无法生成参考图。"
            f"请在资产列表里点「✏️ 编辑」补全「中文指令词」段后再试。"
        )

    # v0.7.7：改用 ImageApiRunner 调 HTTP /v1/images/generations（OpenAI 兼容）
    # 复刻自老 software D:\剧本分镜助手\server.py:1795-1946。
    # 之前 v0.7.6 错用 DreaminaRunner 跑 dreamina.exe image 子命令，
    # 但 dreamina 是字节的 seedance 视频生成 CLI，生图根本不是它干的活。
    # 正确链路：复用 active config 的 base_url + api_key → POST /v1/images/generations
    runner = ImageApiRunner(
        base_url=config.image_base_url,
        api_key=config.image_api_key,
        model=config.image_model,
    )
    # v0.7.7：老 software 硬编码负向词（index.html:1255），不复刻成配置项
    # 传 negative= 空即可（实际不传，ImageApiRunner 内部拼 DEFAULT_NEGATIVE）
    # v0.7.8：把资产参考图带进去（base64 data URL 列表，>0 张就走图生图模式）
    # 复刻自老 software D:\剧本分镜助手\templates\index.html:1244-1246 +
    # server.py:1806, 1837-1839:body["image"] = ref_images[:16]
    ref_images = list(getattr(asset, "ref_images", []) or [])[:16]
    result = runner.run(
        prompt=prompt,
        output=out,
        negative="",  # 弃用，保留向后兼容；ImageApiRunner 内部用 DEFAULT_NEGATIVE
        name=asset.name,
        cancel_check=cancel_check,
        timeout=int(config.image_timeout),
        on_output=on_output,
        resolution=config.image_resolution,
        ratio=config.image_ratio,
        ref_images=ref_images,  # v0.7.8:>0 张时 body 加 "image" 字段
    )
    if result.exit_code != 0:
        raise RuntimeError(f"生图 API 失败 (exit={result.exit_code}): {result.error}")
    return result.image_path, prompt


class AssetImageTask(Task):
    """调用 dreamina.exe 给单个资产生成参考图。

    构造签名跟 asset_panel 调用一致：(asset, project, config, parent=None)

    v0.7.7 修"用户改 prompt 后生图还是用旧值"bug：
    之前 self._asset = asset 直接缓存 UI 传过来的旧 asset 对象，
    user 改 prompt → 800ms 后 _db.update_asset_prompt 写库 → UI 触发生图
    → task 拿的还是旧 asset（image_prompt 是空）→ 走错的 else 分支用空模板。
    修法：构造时如果传了 db，从 db 拉最新 asset 覆盖 self._asset。
    """

    def __init__(
        self,
        asset,
        project,
        config: "Config",
        parent: Any = None,
        output_dir: Optional[Path] = None,
        db: Any = None,  # v0.7.7：可选 db，用于拉最新 asset
    ) -> None:
        super().__init__(name=f"资产配图 · {asset.name}", parent=parent)
        # v0.7.7：从 db 拉最新 asset（如果传了 db），覆盖旧的引用
        if db is not None:
            try:
                fresh = db.get_asset(asset.id)
                if fresh is not None:
                    asset = fresh
                    log = logging.getLogger("manju.asset_image_task")
                    log.debug(
                        "AssetImageTask: 从 db 拉最新 asset id=%s image_prompt_len=%d",
                        asset.id, len(getattr(asset, "image_prompt", "") or ""),
                    )
            except Exception as e:  # noqa: BLE001
                log = logging.getLogger("manju.asset_image_task")
                log.warning("AssetImageTask: 拉最新 asset 失败: %s", e)
        self._asset = asset
        self._project = project
        self._config = config
        self._output_dir = _safe_output_dir(config, output_dir)
        # _persist_task_result 读这两个字段
        self.result_image_path: str = ""
        self.result_prompt: str = ""

    def run(self) -> AssetImageResult:
        self.emit_progress(f"为「{self._asset.name}」生成参考图…")
        image_path, prompt = _run_one_asset_image(
            asset=self._asset,
            project=self._project,
            config=self._config,
            output_dir=self._output_dir,
            cancel_check=lambda: self.is_cancelled,
            on_output=lambda line: self.emit_output(line),
        )
        self.result_image_path = image_path
        self.result_prompt = prompt
        return AssetImageResult(output_file=Path(image_path), prompt_used=prompt)


# ---------- BatchAssetImageTask ----------

@dataclass
class BatchAssetImageRequest:
    """v0.6.26：批量资产生图请求参数。"""
    project_id: str
    # 是否跳过已有图的资产（默认 True，避免重跑已生成好的）
    skip_existing: bool = True


@dataclass
class BatchAssetImageResult:
    """v0.6.26：批量生图结果。"""
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    # 失败的 (asset_name, error_message)
    failures: List[tuple] = field(default_factory=list)


class BatchAssetImageTask(Task):
    """v0.6.26：复刻自原软件 D:\\剧本分镜助手\\server.py:915-933
    `POST /api/projects/<id>/convert-assets`：给项目下所有资产批量跑生图。

    行为：
    - 串行跑（沿用 TaskQueue 串行约定，避免 dreamina 多开）
    - 逐个 emit progress 报告 (i/N) 名字
    - 单个失败不中断其他资产，failed 计数 +1
    - 默认跳过已有图的资产（skip_existing=True），可改成 False 全覆盖
    - 可取消（取消时已完成的保留进度，剩下的跳过）
    """

    def __init__(
        self,
        project,
        db: "Database",
        config: "Config",
        parent: Any = None,
        output_dir: Optional[Path] = None,
        skip_existing: bool = True,
    ) -> None:
        super().__init__(name=f"批量资产生图 · {project.name}", parent=parent)
        self._project = project
        self._db = db
        self._config = config
        self._output_dir = _safe_output_dir(config, output_dir)
        self._skip_existing = skip_existing
        self._request = BatchAssetImageRequest(
            project_id=project.id,
            skip_existing=skip_existing,
        )
        # 终态统计
        self.result_total: int = 0
        self.result_success: int = 0
        self.result_failed: int = 0
        self.result_skipped: int = 0
        self.result_failures: List[tuple] = []

    def run(self) -> BatchAssetImageResult:
        log = logging.getLogger("manju.batch_asset_image")
        log.info("project=%s skip_existing=%s",
                 self._project.id, self._skip_existing)
        # 1) 拿所有资产
        assets = self._db.list_assets(self._project.id)
        if not assets:
            self.emit_progress("项目下没有任何资产，无需生图。")
            return BatchAssetImageResult()

        # 2) 过滤
        todo: list = []
        skipped = 0
        for a in assets:
            if self._skip_existing and a.image_path and Path(a.image_path).exists():
                skipped += 1
                continue
            todo.append(a)
        self.result_total = len(todo)
        self.result_skipped = skipped

        if not todo:
            self.emit_progress(
                f"项目共 {len(assets)} 个资产，全部已有图（{skipped} 个跳过），无需生图。"
            )
            return BatchAssetImageResult(
                total=0, success=0, failed=0, skipped=skipped,
            )

        self.emit_progress(
            f"开始批量生图：共 {len(todo)} 个（{skipped} 个已存在已跳过）"
        )

        # 3) 串行跑
        for i, asset in enumerate(todo, 1):
            if self.is_cancelled:
                self.emit_progress(
                    f"⚠️ 已取消，停止在第 {i - 1}/{len(todo)} 个（已完成 {self.result_success} / 失败 {self.result_failed}）"
                )
                break
            self.emit_progress(
                f"({i}/{len(todo)}) 为「{asset.name}」生成参考图…"
            )
            try:
                image_path, prompt = _run_one_asset_image(
                    asset=asset,
                    project=self._project,
                    config=self._config,
                    output_dir=self._output_dir,
                    cancel_check=lambda: self.is_cancelled,
                    on_output=lambda line, _n=asset.name: self.emit_output(
                        f"  [{_n}] {line}"
                    ),
                )
                # 写回 db
                # v0.7.7 修 prompt 污染 bug（v0.7.7 重打 6 漏）：
                # 之前这里把 `prompt`（convert_to_standard_format 翻译后的英文）
                # 写回 image_prompt → user 编辑的中文被英文覆盖 → 选资产再编辑
                # 显示的是英文 → user 改成中文 → 保存 → 下次生图又被英文覆盖。
                # 陈戈 image_prompt 重复 2 段（中+英）就是这个 bug 的证据。
                # 修法：只写 image_path/image_status，**绝不动 image_prompt**。
                # image_prompt 只在资产提取时由 LLM 抽取、user 编辑时由 UI 写盘
                # 这两个权威源更新；生图是只读消费。
                self._db.update_asset_image(
                    asset.id,
                    image_path=image_path,
                    image_status="ready",
                    # image_prompt 不传，update_asset_image 保持原值
                )
                self.result_success += 1
                self.emit_output(
                    f"  ✓ [{i}/{len(todo)}] {asset.name} → {Path(image_path).name}"
                )
            except Exception as e:  # noqa: BLE001
                # 单个失败不中断
                err = str(e)
                log.exception("batch asset image failed: %s", asset.name)
                try:
                    self._db.update_asset_status(asset.id, "failed")
                except Exception:  # noqa: BLE001
                    log.exception("db update failed for %s", asset.name)
                self.result_failed += 1
                self.result_failures.append((asset.name, err))
                self.emit_output(
                    f"  ✗ [{i}/{len(todo)}] {asset.name} 失败: {err}"
                )

        # 4) 总结
        summary = (
            f"批量生图完成：共 {self.result_total} 个，"
            f"成功 {self.result_success}，失败 {self.result_failed}，"
            f"跳过 {self.result_skipped}"
        )
        self.emit_progress(summary)
        log.info("BatchAssetImageTask: %s", summary)

        return BatchAssetImageResult(
            total=self.result_total,
            success=self.result_success,
            failed=self.result_failed,
            skipped=self.result_skipped,
            failures=list(self.result_failures),
        )


# ---------- VideoTask ----------

class VideoTask(Task):
    """根据 link_mode 路由视频生成：
    - link_mode="web"（默认）：调 dreamina.exe（seedance 模型）走 web 视频生成
    - link_mode="api"：调 video_api_configs[active] 的 OpenAI 兼容 HTTP
      POST {base_url}/v1/videos/generations

    v0.7.8.39【链路路由硬约束】：两者**二选一**互斥。web 走 DreaminaRunner；
    api 走 _call_video_api（impl 紧跟 VideoTask 后面）。
    """

    def __init__(
        self,
        episode: "Episode",
        request: VideoRequest,
        config: Config,
        output_dir: Optional[Path] = None,
    ) -> None:
        seg = f"#{request.segment_index}" if request.segment_index is not None else ""
        link_tag = "API" if request.link_mode == "api" else "Web"
        super().__init__(name=f"视频生成({link_tag}) #{request.episode_id}{seg}")
        self._episode = episode
        self._request = request
        self._config = config
        self._output_dir = _safe_output_dir(config, output_dir)
        self._result_output_file: Optional[Path] = None

    @property
    def result_output_file(self) -> Optional[Path]:
        return self._result_output_file

    def run(self) -> VideoResult:
        # v0.7.8.39【链路路由】：根据 link_mode 选 web / api 链路
        if self._request.link_mode == "api":
            return self._run_api_link()
        return self._run_web_link()

    def _run_web_link(self) -> VideoResult:
        """web 链路：调 dreamina.exe（seedance 模型）。"""
        if not self._config.dreamina_video_args:
            raise RuntimeError(
                "config.hermes_api.json 未配置 dreamina_video_args，无法生成视频"
            )
        self.emit_progress("准备 web 视频生成（dreamina.exe）…")
        ext = self._config.video_output_extension or ".mp4"
        if not ext.startswith("."):
            ext = "." + ext
        out = self._output_path(ext)

        prompt = self._build_prompt_with_audio()
        self.emit_progress(f"调用 dreamina.exe 生成视频 ({out.name})…")

        runner = DreaminaRunner(
            self._config.dreamina_exe,
            self._config.dreamina_video_args,
        )
        result = runner.run(
            prompt=prompt,
            output=out,
            negative=self._config.dreamina_default_video_negative,
            name=self._safe_title(),
            cancel_check=lambda: self.is_cancelled,
            timeout=int(self._config.dreamina_video_max_wait),
            on_output=lambda line: self.emit_output(line),
        )

        if result.exit_code != 0:
            raise RuntimeError(
                f"dreamina 视频失败 (exit={result.exit_code}): {result.error}"
            )

        self._result_output_file = out
        return VideoResult(output_file=out, prompt_used=prompt)

    def _run_api_link(self) -> VideoResult:
        """v0.7.8.39 api 链路：调 video_api_configs[active] 的 OpenAI 兼容 HTTP。
        POST {base_url}/v1/videos/generations（multipart 含 prompt + 视频参数）。
        响应约定：JSON { "video_url": "https://..." | "output_file": "https://...",
                       "id": "...", "status": "succeeded"|"pending" }。
        """
        if not self._config.video_api_configs:
            raise RuntimeError(
                "config.hermes_api.json 未配置 video_api_configs，"
                "无法走 API 链路。请先在【设置 → 🎬 视频 API】添加 API config。"
            )
        if not self._config.video_api_base_url:
            raise RuntimeError(
                "active video_api_config 缺 base_url。请在【设置 → 🎬 视频 API】补上。"
            )
        if not self._config.video_api_key:
            raise RuntimeError(
                "active video_api_config 缺 api_key。请在【设置 → 🎬 视频 API】补上。"
            )
        self.emit_progress("准备 API 视频生成（OpenAI 兼容 HTTP）…")
        ext = ".mp4"
        out = self._output_path(ext)

        prompt = self._build_prompt_with_audio()
        params = dict(self._request.link_params or {})
        model = params.get("model") or self._config.video_api_model
        ratio = params.get("ratio") or ""
        duration = int(params.get("duration") or 0)
        resolution = params.get("resolution") or ""

        # v0.7.8.46：参考生视频 — 把本地资产图上传到 imgbb 拿公网 URL
        # 触发 agnes 图生视频模式（body.image 字段）
        # v0.7.8.57 强化诊断:每一步都打 log,让用户能精准看到
        # 1) ref_img 路径 + 是否存在
        # 2) image_host_api_key 是否配置
        # 3) imgbb 上传结果(URL 长度 + 前 64 字符)
        # 4) 最终 image_url 是否非空
        self.emit_progress(
            f"🔍 [诊断] reference_image={self._request.reference_image!r}"
        )
        image_url = ""
        ref_img = self._request.reference_image
        if ref_img and Path(ref_img).is_file():
            host_key = self._config.image_host_api_key
            if not host_key:
                # v0.7.8.57:这里打更明确的报错
                self.emit_progress(
                    f"❌ 缺 image_host_api_key (imgbb API key),无法上传参考图。\n"
                    f"   参考图:{Path(ref_img).name} ({Path(ref_img)})\n"
                    f"   解决:设置 → 🎨 资产图床 → 配置 imgbb API key"
                )
                raise RuntimeError(
                    f"本段含参考图 {Path(ref_img).name}，但 config.hermes_api.json "
                    f"缺 image_host_api_key（imgbb API key），无法走 API 链路。\n"
                    f"请在 config/hermes_api.json 顶层加 image_host_api_key 字段，"
                    f"或编辑该项目配置。"
                )
            self.emit_progress(
                f"📤 [诊断] 准备上传参考图到 imgbb:\n"
                f"   本地路径:{Path(ref_img)}\n"
                f"   文件大小:{Path(ref_img).stat().st_size // 1024}KB\n"
                f"   imgbb key:{'已配置(' + host_key[:8] + '...)' if host_key else '缺失'}"
            )
            image_url = _upload_to_imgbb(
                Path(ref_img), host_key,
                on_output=lambda line: self.emit_output(line),
            )
            # v0.7.8.57:imgbb 上传后立即打 log,确认是否拿到 URL
            self.emit_progress(
                f"☁️ [诊断] imgbb 上传完成,image_url 长度={len(image_url)}, "
                f"前 64 字符={image_url[:64]}"
            )
        elif ref_img:
            # 路径存在但文件不存在 / 路径无效
            self.emit_progress(
                f"⚠️ [诊断] reference_image 路径无效,跳过图生视频模式:\n"
                f"   路径:{ref_img}\n"
                f"   is_file():{Path(ref_img).is_file()}\n"
                f"   解决:检查资产是否已生成图 / 资产路径是否被移动 / 重新跑资产配图"
            )
        else:
            # 完全没 reference_image → 纯文生视频
            self.emit_progress(
                f"⚠️ [诊断] 该段无 reference_image (seg 里没绑资产图?),走纯文生视频模式"
            )

        self.emit_progress(
            f"调用 {self._config.video_api_base_url}/v1/videos "
            f"(model={model!r}, ratio={ratio!r}, duration={duration}s, "
            f"resolution={resolution!r}, 参考图={'有' if image_url else '无'})…"
        )

        out_path = _call_video_api(
            base_url=self._config.video_api_base_url,
            api_key=self._config.video_api_key,
            model=model,
            prompt=prompt,
            ratio=ratio,
            duration=duration,
            resolution=resolution,
            output_path=out,
            timeout=int(self._config.video_api_timeout or 1800),
            cancel_check=lambda: self.is_cancelled,
            on_output=lambda line: self.emit_output(line),
            image_url=image_url,  # v0.7.8.46
        )

        self._result_output_file = out_path
        return VideoResult(output_file=out_path, prompt_used=prompt)

    # ---- 内部辅助 ----

    def _safe_title(self) -> str:
        t = _sanitize_filename(self._request.episode_title)
        return t or "video"

    def _output_path(self, ext: str) -> Path:
        # v0.7.8.58 视频落盘路径:outputs/<项目名>-第N集-视频/🎞️ Segment X_<时间戳>.mp4
        # v0.7.8.59 调整:"🎞️ Segment X" 作为**文件名前缀**(不再建子目录)
        # 用户原话:"储存方式不对多了一个文件夹,outputs/<项目名>-第N集-视频/就行,
        # 🎞️ Segment X+时间戳为视频命名方式"
        from datetime import datetime as _dt
        seg_idx = self._request.segment_index
        if seg_idx is not None:
            ts = _dt.now().strftime("%Y%m%d_%H%M%S")
            safe_title = self._safe_title()
            out = self._output_dir / f"🎞️ Segment {seg_idx + 1}_{safe_title}_{ts}{ext}"
        else:
            # fallback 旧逻辑(无 segment_index 时)
            ts = _dt.now().strftime("%Y%m%d_%H%M%S")
            out = self._output_dir / f"video_{self._request.episode_id}_{self._safe_title()}_{ts}{ext}"
        out.parent.mkdir(parents=True, exist_ok=True)
        return out

    def _build_prompt_with_audio(self) -> str:
        """v0.6.20：把 audio_files 注入到 prompt 末尾（<audio file="..." /> 格式）。"""
        prompt = self._request.prompt_text
        if self._request.audio_files:
            from core.audio import build_audio_injection
            audio_block = build_audio_injection(self._request.audio_files)
            if audio_block:
                prompt = f"{prompt}\n{audio_block}"
                self.emit_progress(f"注入 {len(self._request.audio_files)} 个音频文件到 prompt")
        return prompt


def _upload_to_imgbb(local_path: Path, api_key: str, on_output=None) -> str:
    """v0.7.8.46：上传本地图片到 imgbb 图床，返回公网 URL。

    agnes 视频 API 的 image 字段只接受 URL，不接受本地路径或 base64。
    流程：
    1. 读本地图片 → base64
    2. POST https://api.imgbb.com/1/upload?key=xxx + form-data image=<base64>
    3. 返回 data.url（https://i.ibb.co/.../...png）

    Args:
        local_path: 本地图片绝对路径（PNG/JPG/GIF）
        api_key: imgbb API key
        on_output: 可选日志回调

    Returns:
        公网 URL 字符串

    Raises:
        RuntimeError: 上传失败
    """
    import base64 as _b64
    import urllib.parse as _urlparse
    from urllib import request as _urlreq
    from urllib import error as _urlerr
    import ssl as _ssl

    if not api_key:
        raise RuntimeError(
            "imgbb API key 未配置（config.hermes_api.json 缺 image_host_api_key），"
            "无法把本地参考图上传成 URL 给 agnes 视频 API。"
        )
    if not local_path or not Path(local_path).is_file():
        raise RuntimeError(f"本地图片不存在：{local_path}")

    img_path = Path(local_path)
    img_bytes = img_path.read_bytes()
    if len(img_bytes) > 32 * 1024 * 1024:
        raise RuntimeError(
            f"图片超过 32MB 限制（实际 {len(img_bytes)//1024//1024}MB），imgbb 拒收"
        )
    b64_data = _b64.b64encode(img_bytes).decode("ascii")
    if on_output:
        on_output(f"☁️ 上传图片到 imgbb: {img_path.name} ({len(img_bytes)//1024}KB)")

    url = "https://api.imgbb.com/1/upload"
    params = _urlparse.urlencode({
        "key": api_key,
        "image": b64_data,
        "name": img_path.stem,
    }).encode("ascii")

    req = _urlreq.Request(
        url,
        data=params,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE
    try:
        with _urlreq.urlopen(req, timeout=60, context=ctx) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except _urlerr.HTTPError as e:
        err_body = ""
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            pass
        raise RuntimeError(
            f"imgbb 上传失败 (HTTP {e.code}): {e.reason}\n{err_body[:500]}"
        ) from e
    except Exception as e:
        raise RuntimeError(f"imgbb 上传失败: {e}") from e

    try:
        import json as _json
        obj = _json.loads(text)
    except _json.JSONDecodeError as e:
        raise RuntimeError(f"imgbb 响应非 JSON: {text[:500]}") from e

    if not obj.get("success"):
        raise RuntimeError(f"imgbb 上传失败：{obj}")

    data = obj.get("data") or {}
    img_url = data.get("url") or data.get("display_url") or ""
    if not img_url:
        raise RuntimeError(f"imgbb 响应缺 url 字段：{obj}")
    if on_output:
        on_output(f"☁️ imgbb 上传成功 → {img_url}")
    return img_url


def _ratio_to_wh(ratio: str, resolution: str) -> tuple:
    """v0.7.8.45：根据 ratio + resolution 算 width/height。

    agnes 官方推荐协议用 width/height/num_frames/frame_rate 字段（不是 ratio/duration/resolution）。
    用户在生视频界面选 ratio（16:9 等）+ resolution（720p 等）+ duration（秒），
    这里换算成 agnes 接受的像素宽高。

    Args:
        ratio: "16:9" / "9:16" / "1:1" / "4:3" / "3:4" / "" 空
        resolution: "480p" / "720p" / "1080p" / "" 空

    Returns:
        (width, height) 像素
    """
    if not ratio:
        ratio = "16:9"
    if not resolution:
        resolution = "720p"
    # base 高度 = resolution 对应值
    height_map = {"480p": 480, "720p": 720, "1080p": 1080}
    height = height_map.get(resolution, 720)
    # 按 ratio 算 width
    try:
        w_ratio, h_ratio = ratio.split(":")
        w_ratio, h_ratio = int(w_ratio), int(h_ratio)
    except (ValueError, AttributeError):
        w_ratio, h_ratio = 16, 9
    width = int(height * w_ratio / h_ratio)
    # 宽高对齐到 8 的倍数（视频编码要求）
    width = (width // 8) * 8
    height = (height // 8) * 8
    return width, height


def _duration_to_num_frames(duration: int) -> int:
    """v0.7.8.45：duration 秒 → num_frames（8n+1 规则，frame_rate=24）。

    agnes 官方要求 num_frames ≤ 441 且遵循 8n + 1 规则。
    24 fps 下：1s→24+1=25，3s→73，5s→121，10s→241，18s→441
    """
    if not duration or duration <= 0:
        return 121  # 默认 5s
    # 限制范围 1-18s
    duration = max(1, min(18, duration))
    target = duration * 24 + 1  # 24fps
    # 找最近的 8n+1
    n = (target - 1) // 8
    candidates = [8 * n + 1, 8 * (n + 1) + 1]
    best = min(candidates, key=lambda x: abs(x - target))
    # 限制 ≤ 441
    return min(best, 441)


def _call_video_api(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    ratio: str,
    duration: int,
    resolution: str,
    output_path: Path,
    timeout: int = 1800,
    cancel_check: Optional[Callable[[], bool]] = None,
    on_output: Optional[Callable[[str], None]] = None,
    image_url: str = "",  # v0.7.8.46：参考生视频，imgbb 上传后的公网 URL
) -> Path:
    """v0.7.8.39：调 video_api_configs[active] 的 OpenAI 兼容 HTTP 生成视频。

    协议约定（参考各中转 API 通用实现 + OpenAI 异步任务模式）：
      POST {base_url}/v1/videos/generations
        Headers: Authorization: Bearer <api_key>
        Body (JSON): {
          "model": "<model>",
          "prompt": "<prompt>",
          "ratio": "<16:9|9:16|...>",   # 可选
          "duration": <int 秒>,         # 可选
          "resolution": "<720p|1080p|...>"  # 可选
        }
      Response: {
        "id": "<task_id>",
        "status": "succeeded" | "pending" | "failed",
        "video_url": "https://..."      # succeeded 时必有
      }
      或同步: {
        "output_file": "https://..."    # 同步返回
      }

    实现：
    1) POST 提交任务，拿到 task_id
    2) 周期性 GET {base_url}/v1/videos/generations/{task_id} 轮询状态
    3) status=succeeded → 拿 video_url，下载到 output_path
    4) status=failed → 抛异常
    5) cancel_check 返回 True → 抛 CancelledError
    """
    import json as _json
    import time as _time
    from urllib import request as _urlreq, error as _urlerr
    import urllib.parse as _urlparse

    def _emit(msg: str) -> None:
        if on_output:
            on_output(msg)

    base = base_url.rstrip("/")
    if not base.endswith("/v1"):
        # 仿生图 API 处理：_ensure_v1_suffix()，确保 /v1 后缀
        base = base + "/v1"
    # v0.7.8.45【对齐 agnes 官方协议 v2.0】（https://agnes-ai.com/zh-Hans/docs/agnes-video-v20）：
    # - 提交端点：POST /v1/videos（官方推荐，不带 /generations）
    #   fallback：POST /v1/video/generations（老接口，v0.7.8.44 用过）
    # - 提交参数：width/height/num_frames/frame_rate（不用 ratio/duration/resolution）
    # - 轮询（推荐）：GET /agnesapi?video_id={video_id}
    # - 轮询（兼容）：GET /v1/videos/{task_id}
    # - 轮询（老接口）：GET /v1/video/generations/{task_id}
    # - 状态：queued/in_progress/completed/failed（小写，OpenAI 扁平格式）
    # - 视频 URL 字段：remixed_from_video_id
    # v0.7.8.44 探测时实际能跑的端点（/v1/video/generations）是 agnes 老接口
    # 内部实现，但官方文档推荐 /v1/videos，现在以官方为准。
    submit_url_official = f"{base}/videos"
    submit_url_legacy = f"{base}/video/generations"

    # v0.7.8.45：把 ratio/duration/resolution 换算成 agnes 接受的 width/height/num_frames/frame_rate
    width, height = _ratio_to_wh(ratio, resolution)
    num_frames = _duration_to_num_frames(duration)
    frame_rate = 24  # v0.7.8.45：agnes 官方示例用 24fps，固定
    # v0.7.8.53 回退：v0.7.8.52 加的 title/mode/negative_prompt/extra_body.image
    # 反而触发了 agnes OpenAI 兼容层额外校验(HTTP 400 fail_to_fetch_task title:BadRequestError)。
    # 确认:v0.7.8.51 提交成功过(轮询到 completed),所以保持 v0.7.8.51 原 body(image 顶层)。
    body_obj = {
        "model": model,
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_frames": num_frames,
        "frame_rate": frame_rate,
    }
    # v0.7.8.46：参考生视频模式（图生视频）。
    # v0.7.8.55 试过 image 顶层 + input_reference（OpenAI 协议）—— 失败。
    # v0.7.8.56 修复：v0.7.8.51 旧 log 暴露真因 —— agnes 后端
    # `request_params.image_list: {}` 是**空 dict**,意味着 agnes 内部用
    # `image_list`(dict 格式)作为图生视频字段!顶层 `image` 字符串被 OpenAI
    # 兼容层丢弃,v0.7.8.46/51/55 三版都没真正把图传给 agnes worker。
    # 修复:加 `image_list` 字段(dict 格式,多 key 兜底: image / first_frame / 0)
    # + 保留 `image` 顶层 + `input_reference`(OpenAI 协议兜底)。
    # v0.7.8.52 加 extra_body 嵌套触发 HTTP 400 → 这次不嵌套 extra_body,
    # 只加顶层 `image_list` 字段。
    #
    # v0.7.8.71【bugfix】:server 端 2026-07-07 改 API 规范,`image_list` 不再
    # 接受 dict 类型(报错 "Invalid type for value. Expected primitive type,
    # got <class 'dict'>: {'first_frame': ..., 'image': ...}"),#2 段参考生
    # 视频模式全部 500 fail_to_fetch_task。
    # v0.7.8.71e 试 `image: str` 顶层 + `input_reference: str` 顶层 → 400
    # "Input should be a valid dictionary or object to extract fields from"。
    # v0.7.8.71f 试 `image_list: [url]` 列表(string list),server 应该接受
    # primitive type list 字段。其它兜底字段保留。
    if image_url:
        body_obj["image"] = image_url
        _emit(
            f"🖼 参考生视频模式:v0.7.8.71h 只发 image=string (URL 长度 {len(image_url)}) "
            f"= {image_url[:64]}{'...' if len(image_url) > 64 else ''}"
        )
    # v0.7.8.55:打 body log 便于诊断(image_url 截断前 32 字符防日志过长)
    body_log = _json.dumps(
        {k: (v[:32] + "..." if isinstance(v, str) and len(v) > 32 else v)
         for k, v in body_obj.items()},
        ensure_ascii=False,
    )
    _emit(f"📋 提交 body: {body_log}")
    body_bytes = _json.dumps(body_obj, ensure_ascii=False).encode("utf-8")

    # v0.7.8.45：先试官方 /v1/videos，404 Invalid URL → fallback 老接口 /v1/video/generations
    submit_text = ""
    submit_obj: dict = {}
    submit_url = ""
    for try_url in (submit_url_official, submit_url_legacy):
        submit_url = try_url
        _emit(f"📡 提交视频任务: POST {submit_url} ({width}x{height}, {num_frames}帧@{frame_rate}fps)")
        req = _urlreq.Request(
            submit_url,
            data=body_bytes,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with _urlreq.urlopen(req, timeout=min(timeout, 60)) as resp:
                submit_text = resp.read().decode("utf-8", errors="replace")
                break
        except _urlerr.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            if e.code == 404 and "Invalid URL" in err_body:
                _emit(f"⚠ {submit_url} 404 Invalid URL，尝试下一个端点…")
                continue
            raise RuntimeError(
                f"视频 API 提交失败 (HTTP {e.code}): {e.reason}\n{err_body[:500]}"
            ) from e
        except (TimeoutError, _urlerr.URLError) as e:
            raise RuntimeError(f"视频 API 提交失败: {e}") from e

    if not submit_text:
        raise RuntimeError(
            f"视频 API 提交失败：所有候选端点都 404 Invalid URL\n"
            f"  试过：{submit_url_official} / {submit_url_legacy}"
        )

    try:
        submit_obj = _json.loads(submit_text)
    except _json.JSONDecodeError as e:
        raise RuntimeError(f"视频 API 返回非 JSON: {submit_text[:500]}") from e

    task_id = submit_obj.get("id") or submit_obj.get("task_id") or ""
    video_id = submit_obj.get("video_id") or ""
    # v0.7.8.45：官方提交响应 status="queued"（小写），兼容大写
    status = submit_obj.get("status", "queued")
    # 同步返回：直接有 video_url（兼容嵌套 data.data.video_url）
    submit_inner = submit_obj.get("data") or {}
    if isinstance(submit_inner, dict):
        submit_inner = submit_inner.get("data") or submit_inner
    direct_url = (
        submit_obj.get("video_url")
        or submit_obj.get("output_file")
        or submit_obj.get("output_url")
        or submit_obj.get("url")
        or (submit_inner.get("video_url") if isinstance(submit_inner, dict) else "")
        or (submit_inner.get("output_file") if isinstance(submit_inner, dict) else "")
        or (submit_inner.get("output_url") if isinstance(submit_inner, dict) else "")
        or (submit_inner.get("url") if isinstance(submit_inner, dict) else "")
        or submit_obj.get("remixed_from_video_id")  # 兜底:某些 API 把 id 当产物占位
        or ""
    )
    if status.lower() in ("succeeded", "completed", "success") and direct_url:
        return _download_video(direct_url, output_path, on_output)
    if not task_id and not video_id:
        raise RuntimeError(
            f"视频 API 提交响应缺 id/task_id/video_id：\n{submit_text[:500]}"
        )

    # v0.7.8.45：轮询端点优先级
    # 1. 官方推荐：GET /agnesapi?video_id={video_id}（如果有 video_id）
    # 2. 官方兼容：GET /v1/videos/{task_id}
    # 3. 老接口：GET /v1/video/generations/{task_id}
    if not base.endswith("/v1"):
        bare_base = base  # e.g. https://chuangwei.cyou/v1
    else:
        bare_base = base
    poll_candidates = []
    if video_id:
        # 官方推荐端点不带 /v1 前缀（直接打 host）
        host_base = base.rstrip("/v1")
        poll_candidates.append(
            f"{host_base}/agnesapi?video_id={_urlparse.quote(video_id, safe='')}"
        )
    poll_candidates.append(
        f"{base}/videos/{_urlparse.quote(task_id, safe='')}"
    )
    poll_candidates.append(
        f"{base}/video/generations/{_urlparse.quote(task_id, safe='')}"
    )
    _emit(
        f"📡 视频任务已提交，task_id={task_id} video_id={video_id[:30]}…，"
        f"开始轮询（每 5s，候选端点 {len(poll_candidates)} 个）"
    )
    deadline = _time.time() + timeout
    while _time.time() < deadline:
        if cancel_check and cancel_check():
            raise RuntimeError("视频生成被用户取消")
        _time.sleep(5)
        for poll_url in poll_candidates:
            try:
                poll_req = _urlreq.Request(
                    poll_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    method="GET",
                )
                with _urlreq.urlopen(poll_req, timeout=30) as resp:
                    poll_text = resp.read().decode("utf-8", errors="replace")
                # 200 OK 才用这个端点
                if resp.status == 200:
                    break
            except _urlerr.HTTPError as e:
                # 404 → 试下一个候选端点
                if e.code == 404:
                    continue
                _emit(f"⚠️ 轮询 {poll_url[:80]} 失败（继续）: HTTP {e.code}")
                poll_text = ""
                continue
            except Exception as e:
                _emit(f"⚠️ 轮询 {poll_url[:80]} 异常（继续）: {e}")
                poll_text = ""
                continue
        else:
            # 所有候选都失败
            _emit("⚠️ 所有轮询端点都失败（继续）")
            continue
        try:
            poll_obj = _json.loads(poll_text)
        except _json.JSONDecodeError:
            _emit(f"⚠️ 轮询响应非 JSON（继续）: {poll_text[:200]}")
            continue
        # v0.7.8.45：解析响应（OpenAI 扁平 / agnes 嵌套双层 data 都支持）
        # 优先级：扁平 > 嵌套（扁平是官方推荐格式）
        if poll_obj.get("status"):
            # OpenAI 扁平 或 agnes /v1/videos/{id}
            status = poll_obj.get("status", "queued")
            fail_reason = poll_obj.get("error") or ""
            vurl = (
                poll_obj.get("remixed_from_video_id")
                or poll_obj.get("video_url")
                or poll_obj.get("output_file")
                or poll_obj.get("output_url")
                or ""
            )
        else:
            # agnes 嵌套 {"code":"success","data":{"status":"...","data":{"video_url":"..."}}}
            # v0.7.8.51 修复：产物 URL 在 inner_data.video_url,旧代码只查
            # inner_data.remixed_from_video_id(参考视频 id,不是 url) +
            # outer_data.result_url(字段名猜的,API 没这字段),
            # 导致 status=completed 但 vurl 永远="" 一直轮询到超时抛错
            outer_data = poll_obj.get("data") or {}
            inner_data = outer_data.get("data", {}) or {}
            status = outer_data.get("status", "queued")
            fail_reason = outer_data.get("fail_reason", "")
            vurl = (
                inner_data.get("video_url")
                or inner_data.get("url")
                or inner_data.get("output_file")
                or inner_data.get("output_url")
                or outer_data.get("video_url")
                or outer_data.get("url")
                or outer_data.get("output_file")
                or outer_data.get("output_url")
                or outer_data.get("result_url")
                or ""
            )
        status_lower = status.lower() if isinstance(status, str) else status
        if status_lower in ("completed", "succeeded", "success") and vurl:
            return _download_video(vurl, output_path, on_output)
        if status_lower in ("failed", "failure"):
            raise RuntimeError(f"视频任务失败：{fail_reason or status}")
        # v0.7.8.51:status=completed 但 vurl 解析失败 → 跳出而不是傻等
        # (API 实际已完成,但我们没识别 URL 字段;继续轮询 30 分钟浪费)
        # v0.7.8.53:加 fallback —— 扫整个 poll_obj 找任何看起来像 mp4 URL 的字段
        # v0.7.8.53:把截断长度从 1500 提到 8000,避免丢字段看不见
        if status_lower in ("completed", "succeeded", "success") and not vurl:
            scan_url = _scan_response_for_video_url(poll_obj)
            if scan_url:
                _emit(f"🔍 fallback 扫到视频 URL: {scan_url}")
                return _download_video(scan_url, output_path, on_output)
            _emit(
                f"⚠️ status=completed 但响应里找不到视频 URL 字段,完整响应:\n{poll_text[:8000]}"
            )
            raise RuntimeError(
                f"视频 API status=completed 但响应里找不到视频 URL 字段"
                f"(请查 agnes 视频 v2.0 协议)。\n完整响应:\n{poll_text[:8000]}"
            )
        # queued / in_progress / pending → 继续轮询
        _emit(f"⏳ status={status}，继续轮询…")
    raise RuntimeError(f"视频 API 轮询超时（{timeout}s），task_id={task_id}")


def _download_video(url: str, output_path: Path, on_output=None) -> Path:
    """v0.7.8.39：下载视频 URL 到本地 output_path（SSL verify=False 仿生图 API）。"""
    import ssl as _ssl
    from urllib import request as _urlreq

    def _emit(msg: str) -> None:
        if on_output:
            on_output(msg)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _emit(f"⬇️ 下载视频：{url} → {output_path.name}")
    ctx = _ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = _ssl.CERT_NONE
    try:
        with _urlreq.urlopen(url, timeout=120, context=ctx) as resp:
            with open(output_path, "wb") as f:
                while True:
                    chunk = resp.read(64 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
    except Exception as e:
        raise RuntimeError(f"下载视频失败: {e}\nURL: {url}") from e
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"下载的视频文件为空：{output_path}")
    return output_path


# v0.7.8.53:扫整个 poll 响应找任何看起来像视频 URL 的字段值
# 兜底用 —— 当 status=completed 但标准字段(remixed_from_video_id/video_url/output_*)都 null 时
# 不傻等 30 分钟,递归遍历响应找带 http(s) + 视频后缀 的字符串
_VIDEO_URL_HINT_KEYS = (
    "video", "url", "file", "output", "result", "media", "download", "playback", "source",
)
_VIDEO_URL_HINT_SUFFIXES = (".mp4", ".mov", ".webm", ".m4v", ".avi", ".mkv")


def _scan_response_for_video_url(obj):
    """v0.7.8.53:递归扫 dict/list,找带 http(s) 协议 + 视频后缀的字符串值。
    排除:值含 'None' / 是 'id' / 'task_id' / 'video_id' 等纯 id 字段。
    返回第一个匹配的 URL 字符串(优先字段名带 video/url 的),没有返回 ""。
    """
    def _looks_like_video_url(s: str) -> bool:
        if not isinstance(s, str) or len(s) < 16 or len(s) > 2000:
            return False
        sl = s.lower()
        if not (sl.startswith("http://") or sl.startswith("https://")):
            return False
        # 必须含视频后缀
        return any(suf in sl for suf in _VIDEO_URL_HINT_SUFFIXES)

    found: list = []  # [(priority, url)]

    def _walk(node, key: str = "", depth: int = 0) -> None:
        if depth > 6 or node is None:
            return
        if isinstance(node, dict):
            for k, v in node.items():
                _walk(v, str(k), depth + 1)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                _walk(item, f"{key}[{i}]", depth + 1)
        else:
            if _looks_like_video_url(node):
                # 优先级: 字段名含 video/url/file 的更高分
                key_lower = key.lower()
                pri = 0
                for hint in _VIDEO_URL_HINT_KEYS:
                    if hint in key_lower:
                        pri += 10
                        break
                # 排除明显是 id 的字段(虽然 _looks_like_video_url 已经要求 .mp4 等,
                # 防御一下)
                if any(bad in key_lower for bad in ("_id", "id", "prompt_id", "task_id")):
                    return
                found.append((pri, node))

    _walk(obj)
    if not found:
        return ""
    found.sort(key=lambda x: -x[0])
    return found[0][1]


def _sanitize_filename(name: str) -> str:
    """简单文件名清洗：去路径分隔符与控制字符。"""
    bad = '\\/:*?"<>|\0'
    out = "".join("_" if c in bad else c for c in name).strip()
    if not out:
        out = "asset"
    return out[:64]


# v0.7.8：老代码大量 `from core.generators import _safe_filename`（asset_panel.py +
# main_window.py 共 12 处），重构时函数改名 `_sanitize_filename` 没改全调用方。
# 加别名保兼容，避免 ImportError 整 app 启动不了。
_safe_filename = _sanitize_filename
