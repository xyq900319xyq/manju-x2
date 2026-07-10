"""Task queue with single-thread serial execution.

Architecture (per project_memory):
- Task emits internal state only (progress / output / partial state)
- _QueueWorker.run_loop() 统一发送终态信号 (started/finished/failed/cancelled)
  → 防止 Task 自己再 emit 终态造成重复信号
- 锁只在 with 块里用，绝不手动 .release()
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from queue import Empty, Queue
from typing import Any, List, Optional

from PySide6.QtCore import QObject, QThread, Signal, Slot


# ---------- 枚举 / 数据 ----------

class TaskState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskResult:
    """Task 终态结果（worker 构造、UI 消费）。"""

    task_name: str
    state: TaskState
    output: str = ""
    error: str = ""
    duration: float = 0.0
    payload: Any = None  # 业务返回值（如 storyboard 路径、prompt 文本）


# ---------- Task 内部信号（仅供 Task 自己 emit） ----------

class _TaskSignals(QObject):
    """Task 自身用的内部信号。

    重要：
    - 这些是「内部 / 中间状态」信号
    - 终态信号（started/finished/failed/cancelled）由 _QueueWorker 统一 emit
    """

    progress = Signal(object, str)        # task, 阶段描述
    output = Signal(object, str)          # task, 一行输出
    partial = Signal(object, object)      # task, 中间产物 payload


# ---------- Task 基类 ----------

class Task:
    """单个可入队任务。

    子类重写 run() 即可，不要在里面 emit 终态信号。
    终态由 _QueueWorker.run_loop() 统一发。
    """

    def __init__(self, name: str = "Task", parent: Optional[QObject] = None) -> None:
        # Task 不继承 QObject，所以"parent"只是签名占位 — 调方写
        # `StoryboardTask(ep, p, cfg, parent=self)` 时不会爆。Task 自己
        # 在 worker 线程里 new，生命周期跟 main_window 无关。
        self._parent_ref = parent
        self._name = name
        self._state: TaskState = TaskState.PENDING
        self._signals = _TaskSignals()
        self._cancel_event = threading.Event()
        self._lock = threading.Lock()
        self._result: Any = None
        # 给每个 task 一个稳定 id，给 cancel(task_id) 用
        # 用 uuid4 而不是 id(name)，因为同名 task 可能在队列里同时存在
        import uuid
        self.task_id: str = uuid.uuid4().hex

    # ---------- 访问 ----------

    @property
    def name(self) -> str:
        return self._name

    @property
    def state(self) -> TaskState:
        return self._state

    @property
    def signals(self) -> _TaskSignals:
        """暴露给同线程内部订阅；UI 不直接连这里。"""
        return self._signals

    @property
    def result(self) -> Any:
        return self._result

    # ---------- 取消 ----------

    def cancel(self) -> None:
        self._cancel_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    # ---------- 内部状态（仅 worker 调用） ----------

    def _set_state(self, state: TaskState) -> None:
        """由 _QueueWorker 在状态机推进时调用。"""
        with self._lock:
            self._state = state

    def _set_result(self, value: Any) -> None:
        with self._lock:
            self._result = value

    # ---------- 业务侧 emit 辅助（中间状态） ----------

    def emit_progress(self, message: str) -> None:
        self._signals.progress.emit(self, message)

    def emit_output(self, line: str) -> None:
        self._signals.output.emit(self, line)

    def emit_partial(self, payload: Any) -> None:
        self._signals.partial.emit(self, payload)

    # ---------- 业务方法 ----------

    def run(self) -> Any:
        """子类重写：实际工作。

        返回值会作为 TaskResult.payload。
        想检查取消请用 self.is_cancelled。
        """
        raise NotImplementedError

    def cleanup(self) -> None:
        """可选：worker 在终态之后调用一次。默认 no-op。"""


# ---------- Worker（只在这里 emit 终态信号） ----------

class _QueueWorker(QObject):
    """后台 worker，串行处理 TaskQueue 里的任务。

    终态信号（task_started / task_finished / task_failed / task_cancelled）只在这里 emit，
    避免 Task.run() 内部异常路径也 emit 造成重复。
    """

    # 终态信号
    task_started = Signal(object)                # task
    task_finished = Signal(object, object)       # task, TaskResult
    task_failed = Signal(object, str)            # task, error_message
    task_cancelled = Signal(object)              # task
    queue_idle = Signal()                        # 队列空
    # 中间信号：把 Task.signals.progress 透到 UI（阶段文字）
    task_phase_changed = Signal(object, str)     # task, phase
    # 中间信号：把 task 的实时输出（hermes stdout 行）透到 UI
    task_output = Signal(object, str)            # task, line

    def __init__(self, queue_ref: "TaskQueue") -> None:
        super().__init__()
        self._queue_ref = queue_ref
        self._stop = False
        self._current_task: Optional[Task] = None
        self._lock = threading.Lock()

    # ---------- 控制 ----------

    def request_stop(self) -> None:
        """请求 worker 取消当前任务，但**不**让 worker 退出循环。

        **v0.6.10 修**：之前这个方法把 self._stop = True，导致 run_loop
        下次迭代立即 return，新入队的 task 永远不会被取 → 用户取消当前
        任务后，再点新任务就"没反应"。现在 _stop=True 拆到 TaskQueue.stop()
        里专门处理（UI 关闭时用），cancel(task_id) 只取消当前 task，worker
        继续跑下一个。
        """
        with self._lock:
            t = self._current_task
        if t is not None:
            t.cancel()

    @Slot(object, str)
    def _on_task_output(self, task: "Task", line: str) -> None:
        """把 task 的 stdout 行透到对外信号，让 UI 能看到 hermes 实时输出。"""
        self.task_output.emit(task, line)

    # ---------- 主循环（跑在 QThread 里） ----------

    def run_loop(self) -> None:
        """QThread.started 连接到这里。

        死循环：从 queue 拿 task → 调 task.run() → 统一发终态信号。
        """
        try:
            while True:
                # take_next 和 _current_task 必须放在同一个锁里，
                # 否则 request_stop() 可能在 take_next 返回后、
                # _current_task 被设置前执行，读到 None 而漏 cancel。
                task: Optional[Task] = None
                with self._lock:
                    if self._stop:
                        return
                    task = self._queue_ref._take_next()
                    if task is not None:
                        self._current_task = task
                        self._queue_ref._set_current_task(task)

                if task is None:
                    # 队列空，发 idle（让 UI 知道可以收尾）
                    # 注意：sleep 必须放在锁外，避免 cancel 卡住
                    self.queue_idle.emit()
                    time.sleep(0.05)
                    continue

                self._execute_one(task)
        finally:
            with self._lock:
                self._current_task = None
                self._queue_ref._set_current_task(None)

    # ---------- 单任务执行 ----------

    def _execute_one(self, task: Task) -> None:
        """执行一个 task，统一发终态信号。"""
        import logging
        log = logging.getLogger("manju.task_queue")
        log.info("_execute_one: 任务 %s 开始 (type=%s)", task.name, type(task).__name__)
        task._set_state(TaskState.RUNNING)
        # 任务开始跑了，从 _pending 移除（cancel(task_id) 不会再找到它，
        # 改走 task.cancel() → _cancel_event 路径）
        self._queue_ref._task_started_running(task)
        # 把 task 的中间状态（progress/output）透到 worker 的对外信号
        # 不连的话 UI 永远看不到阶段变化，状态栏一直卡在 "排队中..."
        try:
            task._signals.progress.connect(self.task_phase_changed)
            task._signals.output.connect(self._on_task_output)
        except Exception as e:
            # v1.1.5【C10 修复】:之前静默吞,emit 失败时 task_started/finished
            # 信号没发,UI 状态卡住,user 不知道任务在跑。加 log.exception
            # 让日志有痕迹,但仍然发 task_started(关键信号不能丢)。
            log.exception("connect task signals failed: %s", e)
        self.task_started.emit(task)

        start = time.monotonic()
        cancelled = False
        try:
            payload = task.run()
        except Exception as e:  # noqa: BLE001 - 任意业务异常都收
            duration = time.monotonic() - start
            log.exception("_execute_one: 任务 %s 抛异常 (%s 后)", task.name, f"{duration:.1f}s")
            task._set_state(TaskState.FAILED)
            try:
                task.cleanup()
            except Exception as cleanup_e:
                # v1.1.5【C10 修复】:之前静默吞,清理失败时 user 看到的"失败"
                # 是 task.run 抛的,但清理错误(比如关闭文件、kill 子进程)也
                # 失败会让资源泄漏。加 log 留痕迹。
                log.warning("task cleanup failed (after run exception): %s", cleanup_e)
            self.task_failed.emit(task, str(e))
            return

        duration = time.monotonic() - start
        # 检查取消：业务 run 正常返回但 cancel 被设置过
        if task.is_cancelled:
            cancelled = True
            task._set_state(TaskState.CANCELLED)
            try:
                task.cleanup()
            except Exception as cleanup_e:
                # v1.1.5【C10 修复】:同 above,清理失败时记录
                log.warning("task cleanup failed (after cancel): %s", cleanup_e)
            self.task_cancelled.emit(task)
            return

        # 正常完成
        task._set_result(payload)
        task._set_state(TaskState.COMPLETED)
        result = TaskResult(
            task_name=task.name,
            state=TaskState.COMPLETED,
            duration=duration,
            payload=payload,
        )
        try:
            task.cleanup()
        except Exception as cleanup_e:
            # v1.1.5【C10 修复】:同 above,清理失败时记录
            log.warning("task cleanup failed (after success): %s", cleanup_e)
        self.task_finished.emit(task, result)


# ---------- 公共 TaskQueue（UI 用） ----------

class TaskQueue(QObject):
    """线程安全的任务队列，UI 通过信号监听。

    用法：
        q = TaskQueue()
        q.start()
        q.submit(MyTask())
        q.task_finished.connect(on_done)
        ...
        q.stop()
    """

    # 转发 worker 终态信号
    task_started = Signal(object)
    task_finished = Signal(object, object)
    task_failed = Signal(object, str)
    task_cancelled = Signal(object)
    queue_idle = Signal()
    # 中间信号：透出 task 的 progress
    task_phase_changed = Signal(object, str)
    # 中间信号：透出 task 的实时输出
    task_output = Signal(object, str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._q: "Queue[Task]" = Queue()
        self._lock = threading.Lock()
        self._thread: Optional[QThread] = None
        self._worker: Optional[_QueueWorker] = None
        self._started = False
        # 已入队但 worker 还没取走的 task（给 cancel(task_id) 用）
        self._pending: set = set()
        # 当前正在跑的任务（worker 通过 _set_current_task 维护，给 cancel(task_id) 用）
        self._current_task: Optional[Task] = None

    # ---------- 生命周期 ----------

    def start(self) -> None:
        """启动后台线程。重复调用幂等。"""
        with self._lock:
            if self._started:
                return
            thread = QThread()
            worker = _QueueWorker(self)
            worker.moveToThread(thread)
            thread.started.connect(worker.run_loop)

            # worker 终态 → 本对象信号（让 UI 只需连本对象）
            worker.task_started.connect(self.task_started)
            worker.task_finished.connect(self.task_finished)
            worker.task_failed.connect(self.task_failed)
            worker.task_cancelled.connect(self.task_cancelled)
            worker.queue_idle.connect(self.queue_idle)
            worker.task_phase_changed.connect(self.task_phase_changed)
            worker.task_output.connect(self.task_output)

            # worker / thread 退出时清理引用
            thread.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)

            self._thread = thread
            self._worker = worker
            self._started = True

        thread.start()

    def stop(self, timeout_ms: int = 5000) -> None:
        """请求停止；等当前任务看到 cancel 并退出 worker 循环。

        **v0.6.10 改**：直接设 worker._stop = True（之前是调
        request_stop()，但 request_stop 在 v0.6.10 改了语义不再 set _stop，
        否则 cancel(task_id) 也会让 worker 退出循环）。
        """
        with self._lock:
            if not self._started:
                return
            worker = self._worker
            thread = self._thread
            self._started = False

        if worker is not None:
            # 1) 先取消当前任务（让业务层能正常响应）
            worker.request_stop()
            # 2) 再让 worker 退出循环
            with worker._lock:
                worker._stop = True
        if thread is not None:
            thread.quit()
            thread.wait(timeout_ms)

        with self._lock:
            self._worker = None
            self._thread = None

    # ---------- 入队 ----------

    def submit(self, task: Task) -> None:
        """把 task 推进队列。线程安全。首次入队会自动 start。"""
        if not self._started:
            self.start()
        # 同步入 _pending（给 cancel(task_id) 用），worker 取走时再 remove
        with self._lock:
            self._pending.add(task)
        self._q.put(task)
        # 通知一下（worker 不需要，但调试方便）
        # task_queued signal 不需要暴露给 UI

    def _task_started_running(self, task: Task) -> None:
        """worker 取到 task 准备跑时调，从 _pending 移除。"""
        with self._lock:
            self._pending.discard(task)

    def _set_current_task(self, task: Optional[Task]) -> None:
        """worker 设置/清空当前正在跑的 task（给 cancel(task_id) 用）。"""
        with self._lock:
            self._current_task = task

    # 别名：兼容老代码（main_window 旧版用的是 enqueue）
    enqueue = submit

    def cancel(self, task_id: str) -> bool:
        """取消指定 task_id 的任务。

        UI 上【取消】按钮调这个。返回 True 表示找到了任务并已发 cancel 信号，
        False 表示任务不在队列/不在跑（可能已完成）。

        **之前 v0.6.8 缺这个方法**，main_window 调 `self.task_queue.cancel(cur.task_id)`
        直接抛 AttributeError，被 Qt 信号吃掉，状态栏只显示"已请求取消..."但
        实际什么也没做 → 用户以为"取消没反应"。v0.6.9 修。

        **v0.6.9 再次修**：只 cancel 匹配的 task，不影响其他正在跑/排队的 task。
        - 当前正在跑（target == self._current_task）→ 调 worker.request_stop()
          让 worker 停 + 触发 task.cancel() 让业务层（hermes 子进程）看到
        - 还在 _pending 队列里 → 只设 _cancel_event，worker 取出时 _take_next()
          会通过 task.is_cancelled 拒绝执行（不发 finished/failed，只发 cancelled）
        """
        target: Optional[Task] = None
        is_current = False
        with self._lock:
            cur = self._current_task
            if cur is not None and getattr(cur, "task_id", None) == task_id:
                target = cur
                is_current = True
            else:
                # 已入队还没跑的：直接标 cancel
                for t in self._pending:
                    if getattr(t, "task_id", None) == task_id:
                        t.cancel()  # 设 _cancel_event
                        target = t
                        break
        if target is None:
            return False
        # 只有"目标 = worker 正在跑的任务"才影响 worker
        # pending 的 cancel 已通过 _cancel_event 传达，worker 取出时会自己看到
        if is_current:
            with self._lock:
                worker = self._worker
            if worker is not None:
                worker.request_stop()  # 里面会调 cur.cancel()
            else:
                target.cancel()
        return True

    def cancel_all(self) -> None:
        """请求取消：当前任务 cancel + 不再派发新任务。

        已入队但还没开始跑的任务，worker 仍会取出来，但 run 之前会先看 is_cancelled。
        """
        with self._lock:
            worker = self._worker
        if worker is not None:
            worker.request_stop()

        # 排空队列，给所有未执行的 task 标 cancel
        drained: List[Task] = []
        while True:
            try:
                t = self._q.get_nowait()
            except Empty:
                break
            t.cancel()
            drained.append(t)

        # 立刻在主线程发出 cancelled 信号（这些 task 根本没跑）
        for t in drained:
            t._set_state(TaskState.CANCELLED)
            self.task_cancelled.emit(t)

    # ---------- 内部（worker 用） ----------

    def _take_next(self) -> Optional[Task]:
        try:
            task = self._q.get_nowait()
        except Empty:
            return None
        if task.is_cancelled:
            # 已经要求取消，根本不跑
            task._set_state(TaskState.CANCELLED)
            self.task_cancelled.emit(task)
            return None
        return task
