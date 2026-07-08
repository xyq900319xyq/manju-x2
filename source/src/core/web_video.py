"""v0.6.22：web 视频生成（自定义命令模板调外部脚本）。

复刻自原软件 D:\\剧本分镜助手\\server.py:1956-2001 `POST /api/video/generate/web`。
原软件用 `agent-browser` 半成品（注释"后续按实际页面调整"），manju 改成
**用户自定义命令模板**（更通用）：

    cmd_template: str = "python D:/scripts/my_video.py {prompt_file} {output_file}"

manju 把 prompt 写到临时文件，替换占位符，调 subprocess.run 跑用户的脚本。
用户脚本自己负责调 videoApiUrl / 浏览器自动化 / 写 mp4 到 {output_file}。

支持占位符：
    {prompt_file}  → 临时文件绝对路径（utf-8 文本）
    {output_file}  → 期望产物 mp4 绝对路径
    {prompt}       → prompt 文本（**短用** — 超过 8000 字符会触发 Windows
                     命令行长度限制，自动走文件）

使用前提：用户在设置里配 `web_video.cmd_template`。
非空 → 视频 Tab "🌐 浏览器生成" 按钮启用。
"""
from __future__ import annotations

import logging
import re
import shlex
import shutil
import subprocess
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class WebVideoRequest:
    """v0.6.22：web 视频生成请求参数。

    字段语义复刻原软件 server.py:1962-1965 接收的 episode_id / segment_ids。
    """
    episode_id: int
    episode_title: str
    prompt_text: str
    segment_index: Optional[int] = None
    output_path: Path = field(default_factory=Path)   # 期望产物 mp4 路径
    cmd_template: str = ""                              # 用户配的命令模板


@dataclass
class WebVideoResult:
    """v0.6.22：web 视频生成结果。"""
    video_path: str = ""
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    error: str = ""


# ---------- 命令模板 ----------
PLACEHOLDERS = ("{prompt_file}", "{output_file}", "{prompt}")


def validate_cmd_template(template: str) -> str:
    """校验命令模板 — 空 / 含占位符 / 第一段命令在 PATH。

    Returns:
        错误信息（空 = 通过）

    复刻原软件 server.py:1989-1998 `subprocess.run(agent-browser, ...)` 的 try/except
    行为，加占位符校验。
    """
    if not template or not template.strip():
        return "命令模板为空"
    if not any(p in template for p in PLACEHOLDERS):
        return f"命令模板必须含至少一个占位符: {', '.join(PLACEHOLDERS)}"
    # 抽第一个 token
    try:
        # v0.6.22 修：posix=False 让 Windows 反斜杠路径不被当 escape
        first = shlex.split(template, posix=False)[0]
    except ValueError as e:
        return f"命令模板解析失败: {e}"
    if not shutil.which(first):
        return f"命令 '{first}' 不在 PATH 中（请先安装）"
    return ""


def render_cmd(template: str, prompt_file: str, output_file: str, prompt: str = "") -> str:
    """v0.6.22：替换占位符。文件路径转 forward-slash + 加双引号避免 shlex 拆分时空格问题。

    同时**全局**把反斜杠转 forward-slash（Windows 上 forward-slash 同样有效，
    且避免 shlex posix 模式把 `\\` 当 escape 字符吞掉）。prompt 的双引号转义在
    全局替换之后做，避免被一并转成 `/`。
    """
    out = template
    out = out.replace("{prompt_file}", f'"{prompt_file.replace(chr(92), "/")}"')
    out = out.replace("{output_file}", f'"{output_file.replace(chr(92), "/")}"')
    out = out.replace("{prompt}", "\x00PROMPT\x00")
    out = out.replace("\\", "/")
    prompt_escaped = prompt.replace('"', '\\"')
    out = out.replace("\x00PROMPT\x00", prompt_escaped)
    return out


# ---------- 执行 ----------
def run_web_video(
    request: WebVideoRequest,
    timeout: float = 600.0,
) -> WebVideoResult:
    """v0.6.22：同步跑 web 视频生成（写 prompt 文件 + 调命令 + 等产物）。

    行为：
    1. 校验 cmd_template（空 / 无占位符 / 命令不在 PATH）
    2. 写 prompt 到 `<output>.prompt.txt`（UTF-8）
    3. shlex.split 模板 + 替换占位符
    4. subprocess.run(..., timeout=timeout, capture_output=True)
    5. 检查 `<output>` 是否被创建（>= 100 字节算成功）
    6. 返回 WebVideoResult

    Returns:
        WebVideoResult — video_path 非空 = 成功
    """
    err = validate_cmd_template(request.cmd_template)
    if err:
        return WebVideoResult(error=err, returncode=-1)

    output_path = Path(request.output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_file = str(output_path) + ".prompt.txt"
    Path(prompt_file).write_text(request.prompt_text or "", encoding="utf-8")

    rendered = render_cmd(
        request.cmd_template,
        prompt_file=prompt_file,
        output_file=str(output_path),
        prompt=request.prompt_text or "",
    )
    try:
        # v0.6.22 修：posix=True（默认），路径已转 forward-slash + 双引号，shlex 会正确解析
        cmd_args = shlex.split(rendered)
    except ValueError as e:
        return WebVideoResult(error=f"模板解析失败: {e}", returncode=-2)

    log.info("v0.6.22 web video 调: %s", cmd_args)
    try:
        proc = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return WebVideoResult(
            error=f"超时（{timeout}s）", stdout=e.stdout or "", stderr=e.stderr or "",
            returncode=-3,
        )
    except OSError as e:
        return WebVideoResult(error=f"OS 错误: {e}", returncode=-4)

    # 检查产物
    if not output_path.exists() or output_path.stat().st_size < 100:
        return WebVideoResult(
            error=f"命令退出 rc={proc.returncode} 但产物 {output_path.name} 未生成或太小",
            stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode,
        )
    return WebVideoResult(
        video_path=str(output_path),
        stdout=proc.stdout,
        stderr=proc.stderr,
        returncode=proc.returncode,
    )


# ---------- 路径 helper ----------
def safe_web_video_filename(ep_title: str, seg_index: int) -> str:
    """v0.6.22：构造 web 视频文件路径（mp4）。"""
    safe = re.sub(r'[\\/*?:"<>|]', "_", ep_title) or f"ep_{uuid.uuid4().hex[:6]}"
    return f"webvideo_{safe}_seg{seg_index:02d}_{uuid.uuid4().hex[:6]}.mp4"
