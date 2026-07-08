"""Subprocess wrapper for hermes.exe.

v0.7.5：完全复刻老软件 D:\\剧本分镜助手\\server.py:560, 3095 的链路
—— `subprocess.run(capture_output=True, text=True, encoding='utf-8', timeout=7200)`
Popen 内部用 PIPE 收集 stdout/stderr，communicate() 等子进程结束一次性拿完整输出。
EXE 进程下 Popen PIPE 实时读漏数据的问题因此彻底解决（之前 v0.7.4 走
reader thread 实时读,hermes 跑通但 manju 拿不到 stdout → db 不更新）。

保留的 manju 必要特性:
- cancel() 用守护线程主动 kill 子进程,主线程 communicate() 立即返回
- timeout 用 Popen.communicate(timeout=...) 强制结束

删除的 manju 自创机制:
- reader thread (实时读 stdout)
- _drain_queue
- idle_kill / seen_any_output / last_stdout_time
"""
from __future__ import annotations

import os
import re
import shlex
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Tuple

# Windows：抑制 hermes.exe 的控制台窗口（黑屏）。
# 没这个 flag，从 GUI app 调 console app 会弹个黑窗口，hermes 退之前一直在那。
# 只在 Windows 上用，其他平台 CREATE_NO_WINDOW 不存在。
if os.name == "nt":
    _NO_WINDOW = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
else:
    _NO_WINDOW = 0


# ---------- Data Classes ----------

@dataclass
class RunResult:
    """Result of a single ManjuTask execution."""

    returncode: Optional[int] = None
    output: str = ""
    cancelled: bool = False
    timed_out: bool = False
    duration: float = 0.0
    args: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Return True if the task completed successfully."""
        return (
            (not self.cancelled)
            and (not self.timed_out)
            and self.returncode == 0
        )


# ---------- Exceptions ----------

class HermesError(Exception):
    """Base exception for hermes.exe wrapper errors."""
    pass


class HermesTimeoutError(HermesError):
    """Raised when the task exceeds the timeout."""
    pass


class HermesCancelledError(HermesError):
    """Raised when the task is cancelled."""
    pass


class HermesNonZeroExitError(HermesError):
    """Raised when hermes.exe exits with a non-zero code."""
    pass


class HermesInvalidSubcommandError(HermesError):
    """hermes.exe 拒绝子命令（`invalid choice` 错误）。

    比 HermesNonZeroExitError 更具体：业务层可以让 UI 给用户明确指引，
    告诉他们去【设置】→【API 配置】改 profiles.<业务key>。
    """

    def __init__(self, message: str, bad: str, available: List[str]) -> None:
        super().__init__(message)
        self.bad = bad
        self.available = list(available)


# hermes 错误输出格式：
#   hermes: error: argument command: invalid choice: 'asset-designer'
#   (choose from 'chat', 'model', 'fallback', 'secrets', 'migrate', ...)
# 输出可能被 argparse 截断（用 ...），所以 findall 抽所有 'xxx' 形式
_INVALID_CHOICE_BAD_RE = re.compile(r"invalid choice: '([^']+)'")
_CHOICES_LIST_RE = re.compile(r"choose from\s+(.+)", re.DOTALL)


def parse_invalid_choice(output: str) -> Optional[Tuple[str, List[str]]]:
    """从 hermes 错误输出解析 invalid choice 错误。

    返回 (被拒绝的子命令, 可用子命令列表) 或 None。
    鲁棒：支持输出被 argparse 截断（用 ... 省略剩余子命令）。
    """
    if not output:
        return None
    bad_m = _INVALID_CHOICE_BAD_RE.search(output)
    if bad_m is None:
        return None
    bad = bad_m.group(1)
    # 在 bad 之后找 choose from 部分
    after_bad = output[bad_m.end():]
    choices_m = _CHOICES_LIST_RE.search(after_bad)
    if choices_m is None:
        return bad, []
    choices_blob = choices_m.group(1)
    # 抽所有 'xxx' 形式（可能后面有 ... 表示截断）
    available = re.findall(r"'([^']+)'", choices_blob)
    return bad, available


# ---------- Main Task Class ----------

class ManjuTask:
    """Single hermes.exe call task.

    v0.7.5：完全复刻老软件 D:\\剧本分镜助手\\server.py:560, 3095 的
    `subprocess.run(capture_output=True, text=True, encoding='utf-8', timeout=7200)`。
    链路 = Popen(stdout=PIPE, stderr=STDOUT, text=True, encoding='utf-8',
    errors='replace', stdin=DEVNULL) + proc.communicate(timeout=...) 一次性读完整 stdout。

    cancel 机制:守护线程 monitor _cancel_event,看到 cancel → proc.terminate()
    (5s 后 proc.kill())。主线程 proc.communicate() 因进程已死立即返回,
    cancelled=True → raise HermesCancelledError。

    timeout 机制:proc.communicate(timeout=self.timeout) 超时 → raise
    TimeoutExpired → proc.kill() + proc.communicate() 收尸 → timed_out=True
    → raise HermesTimeoutError。

    删除的旧机制(v0.7.4 及更早):
    - reader thread 实时读 stdout(EXE 进程下漏数据)
    - _drain_queue(只 drain 一次漏数据)
    - idle_kill / seen_any_output / last_stdout_time(防 hermes 卡死的兜底,
      老 software 走 subprocess.run,hermes 死锁直接等 7200s timeout 兜底,不要这个)
    """

    def __init__(
        self,
        args: List[str],
        cwd: Optional[Path] = None,
        env: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> None:
        if not args:
            raise HermesError("ManjuTask.args cannot be empty")
        self.args: List[str] = list(args)
        self.cwd: Optional[Path] = cwd
        self.env: Optional[dict] = env
        self.timeout: Optional[float] = timeout
        self._cancel_event = threading.Event()
        self._proc: Optional[subprocess.Popen] = None

    def cancel(self) -> None:
        """Cancel the running task."""
        self._cancel_event.set()

    def run(
        self,
        on_output: Optional[Callable[[str], None]] = None,
    ) -> RunResult:
        """Execute synchronously, return RunResult.

        链路: Popen(stdout=PIPE, stderr=STDOUT, stdin=DEVNULL, text=True,
        encoding='utf-8', errors='replace') + proc.communicate(timeout=self.timeout)
        —— 等同老 software subprocess.run(capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=7200) 行为。
        """
        start = time.monotonic()
        self._cancel_event.clear()

        env = {**os.environ, **self.env} if self.env else None
        # v0.7.8.2:manju EXE 在 main.py 写 os.environ["PYTHONHOME"] = _internal 让自己
        # 的打包 Python 找 stdlib;但这个 PYTHONHOME 会被子进程继承,hermes.exe 自己用
        # 的 Python 在 D:\Hermes\hermes-agent\venv\,看到 PYTHONHOME 指 _internal 就
        # 在错的 prefix 找 encodings → ModuleNotFoundError,hermes 启动崩溃 exit 1。
        # 修法:无论 task 传不传 env(传了就合并,没传 Popen 会自动继承父进程),都**先
        # 复制再剔除** PYTHONHOME / PYTHONPATH 这两个 Python-only 污染变量,让 hermes
        # 走自己 venv 的 stdlib。
        # 注意:**不能**用 `if env is not None` 跳过(env=None 时 Popen 默认继承父进程,
        # 仍会泄漏污染变量,需要先做一份父环境 dict 再剥)。
        if env is None:
            env = dict(os.environ)
        for k in ("PYTHONHOME", "PYTHONPATH"):
            env.pop(k, None)
        # v0.7.5：跟老 software D:\剧本分镜助手\server.py:560, 3095 行为完全一致
        # stdin=DEVNULL 复刻 hermes stdin EOF 触发退出的行为
        # stderr=STDOUT 把 stderr 合到 stdout,老 software combined = result.stdout + result.stderr
        # 直接走 stdlib 默认行为,EXE 进程下不再有"reader thread 漏数据"的问题
        proc = subprocess.Popen(
            self.args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(self.cwd) if self.cwd else None,
            env=env,
            text=True,
            encoding='utf-8',
            errors='replace',
            # v0.7.8.21:加 CREATE_NO_WINDOW 抑制 hermes 子进程弹黑框
            # (hermes.exe 是 PyInstaller 打包的 console binary,从 GUI app 调它
            # 不加这个 flag 会弹个黑窗口,用户看到以为有 cmd 卡在那)
            creationflags=_NO_WINDOW,
        )
        self._proc = proc

        # 守护线程:monitor cancel_event,被设则主动 kill 子进程
        # 这样主线程 proc.communicate() 因子进程已死立即返回
        def _cancel_watcher() -> None:
            # 短轮询,看到 cancel_event 被设就 terminate
            while not self._cancel_event.wait(timeout=0.1):
                if proc.poll() is not None:
                    return
            # cancel_event 被 set,主动 kill
            if proc.poll() is None:
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5.0)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

        cancel_thread = threading.Thread(target=_cancel_watcher, daemon=True)
        cancel_thread.start()

        cancelled = False
        timed_out = False
        stdout = ""
        try:
            try:
                stdout, _ = proc.communicate(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    stdout, _ = proc.communicate()
                except Exception:
                    stdout = ""
        finally:
            self._proc = None
            # cancel 路径:守护线程已杀进程 → cancelled 由 _cancel_event 标志判断
            if self._cancel_event.is_set() and not timed_out:
                cancelled = True
            # 关闭 stdout PIPE 句柄(避免 EXE 进程下 fd 泄漏)
            try:
                if proc.stdout is not None:
                    proc.stdout.close()
            except Exception:
                pass

        duration = time.monotonic() - start
        rc = proc.returncode
        output = (stdout or "").rstrip() if stdout else ""

        # 调 on_output 回调(老 software 不调这个,manju 给 UI 透传 hermes 输出)
        if on_output is not None and output:
            for line in output.splitlines():
                try:
                    on_output(line)
                except Exception:
                    pass

        result = RunResult(
            returncode=rc,
            output=output,
            cancelled=cancelled,
            timed_out=timed_out,
            duration=duration,
            args=self.args,
        )

        if cancelled:
            raise HermesCancelledError(f"Task was cancelled: {self._cmdline()}")
        if timed_out:
            raise HermesTimeoutError(
                f"Task timed out ({self.timeout}s): {self._cmdline()}"
            )
        if rc is not None and rc != 0:
            # 失败时把 hermes 的完整输出写到 log 文件,方便调试
            import logging
            logging.getLogger("manju.hermes").error(
                "hermes.exe exit %s\n--- args ---\n%s\n--- output (tail) ---\n%s",
                rc, self._cmdline(),
                (output or "")[-2000:] if output else "",
            )
            raise HermesNonZeroExitError(
                f"hermes.exe exit code {rc}: {self._cmdline()}"
                + (f"\n--- output (tail) ---\n{output[-2000:]}" if output else "")
            )
        return result

    # ---------- Internal ----------

    def _cmdline(self) -> str:
        try:
            return " ".join(shlex.quote(a) for a in self.args)
        except Exception:
            return " ".join(self.args)


# ---------- Batch Task Queue ----------

class ManjuTaskQueue:
    """FIFO batch execution of multiple ManjuTasks.

    - Single-thread serial execution
    - Any task exception doesn't stop subsequent tasks
    - Results collected to results list
    - stop_on_error=True: stop on First Error
    """

    def __init__(self, stop_on_error: bool = False) -> None:
        self._tasks: List[ManjuTask] = []
        self._stop_on_error = stop_on_error
        self._lock = threading.Lock()
        self._cancelled = False

    def push(self, task: ManjuTask) -> None:
        with self._lock:
            self._tasks.append(task)

    def cancel_all(self) -> None:
        self._cancelled = True
        with self._lock:
            for t in self._tasks:
                t.cancel()

    def run_all(
        self,
        on_task_start: Optional[Callable[[ManjuTask], None]] = None,
        on_task_done: Optional[Callable[[ManjuTask, RunResult], None]] = None,
        on_output: Optional[Callable[[ManjuTask, str], None]] = None,
    ) -> List[RunResult]:
        results: List[RunResult] = []
        with self._lock:
            tasks = list(self._tasks)
        for t in tasks:
            if self._cancelled:
                break
            if on_task_start is not None:
                try:
                    on_task_start(t)
                except Exception:
                    pass
            try:
                result = t.run(
                    on_output=(
                        lambda line, _t=t: on_output(_t, line)
                        if on_output is not None
                        else None
                    )
                )
            except HermesError as e:
                result = RunResult(
                    returncode=None,
                    output=str(e),
                    cancelled=isinstance(e, HermesCancelledError),
                    timed_out=isinstance(e, HermesTimeoutError),
                    args=t.args,
                )
                if on_task_done is not None:
                    try:
                        on_task_done(t, result)
                    except Exception:
                        pass
                results.append(result)
                if self._stop_on_error:
                    break
                continue

            if on_task_done is not None:
                try:
                    on_task_done(t, result)
                except Exception:
                    pass
            results.append(result)
        return results


# ---------- Convenience Entry Point ----------

def run_hermes(
    args: List[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[dict] = None,
    timeout: Optional[float] = None,
) -> RunResult:
    """One-time execution: build task + run."""
    task = ManjuTask(args, cwd=cwd, env=env, timeout=timeout)
    return task.run()
