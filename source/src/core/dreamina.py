"""Dreamina 外部调用：通过 subprocess 调 dreamina.exe（资产生图 / 视频生成）。

约束：dreamina.exe 是外部黑盒工具，仅通过 subprocess 调；与 D:\\剧本分镜助手\\
     无**运行时**依赖（不 import 也不调它的代码）；允许读它的代码作为参考
     并手工翻译逻辑到本目录，所有复刻必须标"复刻自 server.py:XXX"。
命令模板在 config/hermes_api.json 里可改，模板变量：
- {prompt}     — prompt 文本
- {negative}   — 负向提示词
- {output}     — 输出文件绝对路径（生图=.png，视频=.mp4）
- {name}       — 资产 / 镜头名

复用方式：同一份 DreaminaRunner + args_template 既能生图也能生视频，
区别只在 config 里的 `dreamina_image_args` / `dreamina_video_args` 模板。
"""
import json
import logging
import os
import queue
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

log = logging.getLogger("manju.dreamina")


@dataclass
class ImageResult:
    exit_code: int           # 0=ok; -1=cancelled; -2=timeout; -3=error
    image_path: str          # 成功时 = 输出文件绝对路径（图片 / 视频 都用这个字段）
    error: str               # 失败原因
    log_text: str            # dreamina 全部输出（用于调试）


class DreaminaRunner:
    """调一次 dreamina.exe（生图 / 生视频 都用这个类）。

    工作流程：
    1. 用构造时传入的 args_template 替换变量 → 拼出最终 argv
    2. Popen 启动 dreamina.exe
    3. 读 stdout / stderr（dreamina 输出 JSON 行：{"type": "progress", ...} / {"type": "done", "path": ...}）
    4. 退出后检查输出文件是否存在
    """

    def __init__(self, dreamina_exe: str | Path, args_template: List[str]):
        self._exe = str(dreamina_exe)
        self._template = list(args_template)

    @property
    def exe(self) -> str:
        return self._exe

    def _build_argv(self, prompt: str, negative: str, output: Path, name: str) -> List[str]:
        """把模板拼成实际 argv。模板里的 {xxx} 会被替换。"""
        out: List[str] = []
        for piece in self._template:
            try:
                out.append(
                    piece.format(
                        prompt=prompt,
                        negative=negative,
                        output=str(output),
                        name=name,
                    )
                )
            except KeyError as e:
                log.warning("dreamina args 模板含未知占位符 %s，原样保留", e)
                out.append(piece)
        return out

    def run(
        self,
        prompt: str,
        output: Path,
        negative: str = "",
        name: str = "asset",
        cancel_check: Callable[[], bool] = lambda: False,
        timeout: int = 600,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> ImageResult:
        """同步阻塞调用 dreamina.exe 生图。

        参数：
            prompt:    生图 prompt（中文/英文皆可）
            output:    输出图片路径（.png）
            negative:  负向提示词
            name:      资产名（用于模板变量）
            cancel_check: 取消回调
            timeout:   超时秒数
            on_output: 每行 stdout 回调

        返回：ImageResult
        """
        if not self._exe:
            return ImageResult(-3, "", "dreamina_exe 未配置", "")
        if not os.path.exists(self._exe):
            return ImageResult(-3, "", f"dreamina.exe 不存在: {self._exe}", "")

        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        # 删掉旧的（防止误判）
        if output.exists():
            try:
                output.unlink()
            except Exception:
                pass

        argv = self._build_argv(prompt=prompt, negative=negative, output=output, name=name)
        # 拼成最终命令行：<dreamina_exe> <argv...>
        full_argv = [self._exe] + list(argv)
        log.info("starting dreamina  argv=%s  output=%s", full_argv, output)
        try:
            proc = subprocess.Popen(
                full_argv,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except Exception as e:
            log.exception("启动 dreamina 失败")
            return ImageResult(-3, "", f"启动 dreamina 失败: {e}", "")

        # 后台读 stdout
        output_q: "queue.Queue[Optional[str]]" = queue.Queue()

        def _reader():
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    output_q.put(line)
            except Exception as e:
                log.warning("dreamina reader error: %s", e)
            finally:
                output_q.put(None)

        reader = threading.Thread(target=_reader, daemon=True)
        reader.start()

        chunks: list[str] = []
        cancelled = False
        timed_out = False
        deadline = time.time() + timeout if timeout else None
        try:
            while True:
                if cancel_check():
                    log.info("cancel requested, terminating dreamina (pid=%s)", proc.pid)
                    cancelled = True
                    self._kill_proc(proc)
                    break
                if deadline is not None and time.time() > deadline:
                    log.warning("dreamina timeout (%ds), killing", timeout)
                    timed_out = True
                    self._kill_proc(proc)
                    break
                try:
                    line = output_q.get(timeout=0.5)
                except queue.Empty:
                    continue
                if line is None:
                    break
                chunks.append(line)
                if on_output:
                    try:
                        on_output(line)
                    except Exception:
                        pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        except Exception as e:
            log.exception("dreamina run loop error")
            try:
                proc.kill()
            except Exception:
                pass
            return ImageResult(-3, "", f"运行异常: {e}", "".join(chunks))

        reader.join(timeout=2)
        log_text = "".join(chunks)
        exit_code = proc.returncode or 0

        if cancelled:
            return ImageResult(-1, "", "已取消", log_text)
        if timed_out:
            return ImageResult(-2, "", f"超时（{timeout}s）", log_text)
        if exit_code != 0:
            return ImageResult(exit_code, "", f"dreamina 退出码 {exit_code}: {log_text[-200:]}", log_text)

        # 退出码 0 但还要看文件
        if not output.exists():
            return ImageResult(-3, "", f"dreamina 退出成功但输出文件不存在: {output}", log_text)
        return ImageResult(0, str(output), "", log_text)

    @staticmethod
    def _kill_proc(proc: subprocess.Popen, grace: float = 3.0) -> None:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=grace)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=grace)
        except Exception:
            pass
