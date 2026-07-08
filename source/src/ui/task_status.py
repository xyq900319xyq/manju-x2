"""状态栏上的任务状态组件：显示当前任务名 + 阶段 + 取消按钮。"""
from PySide6.QtWidgets import QWidget, QLabel, QPushButton, QHBoxLayout
from PySide6.QtCore import Signal


class TaskStatusWidget(QWidget):
    """状态栏永久 widget。无任务时隐藏。"""

    cancel_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        # v0.7.8.37l:不再 setVisible(False) —— 始终 visible,只清空内部 label。
        # 任务没运行时 widget 占位 0 宽(内部 QLabel 全空 + cancel 按钮隐藏),
        # 让状态栏高度永远不变化。
        self.setVisible(True)

        self._task_name = QLabel("")
        self._task_name.setStyleSheet("color: #0066cc; font-weight: bold;")
        self._phase = QLabel("")
        self._phase.setStyleSheet("color: #555;")
        self._status_icon = QLabel("")
        self._cancel_btn = QPushButton("⏹ 取消")
        self._cancel_btn.setFixedHeight(24)
        self._cancel_btn.setVisible(False)  # 没任务时不显示
        self._cancel_btn.clicked.connect(self.cancel_requested.emit)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)
        layout.addWidget(self._status_icon)
        layout.addWidget(self._task_name)
        layout.addWidget(self._phase)
        layout.addWidget(self._cancel_btn)
        self.setLayout(layout)

        self._current_task = None  # type: ignore

    def show_task(self, task) -> None:
        self._current_task = task
        self._status_icon.setText("⏳")
        self._task_name.setText(task.name)
        # 注意：show_task 是从 task_started 信号调来的，任务已经开始执行
        # 旧的 "排队中..." 措辞会让用户以为没动；现在直接显示"运行中…"
        self._phase.setText("运行中…")
        # v0.7.8.37l:不再 setVisible(True) —— 始终 visible,只显示内容
        # 让状态栏高度不变化
        self._cancel_btn.setVisible(True)

    def update_phase(self, phase: str) -> None:
        self._phase.setText(phase)

    def mark_success(self) -> None:
        # v0.7.8.68【bugfix】:终态必须**立即**清 _current_task,不能依赖
        # 1.5s 后的 QTimer.singleShot(..., self.clear)。
        # 原因:之前 mark_* 不动 _current_task,任务完成后 1.5s 内用户点新
        # 生成按钮 → line 1774 早返回 + 弹 "已有任务在跑",用户看到的是
        # "我点了没反应"(弹窗被关掉就以为没动)。
        # 跟 _enqueue_task (main_window.py:2174-2179) 的 state==RUNNING
        # 检查不同,这里 _current_task 是 widget 自己的字段,清空就行。
        self._current_task = None
        self._status_icon.setText("✓")
        self._phase.setText("完成")
        self._cancel_btn.setVisible(False)

    def mark_failed(self, reason: str) -> None:
        # v0.7.8.68:跟 mark_success 同理,立刻释放 _current_task
        self._current_task = None
        self._status_icon.setText("✗")
        self._phase.setText(f"失败: {reason[:50]}")
        self._cancel_btn.setVisible(False)

    def mark_cancelled(self) -> None:
        # v0.7.8.68:跟 mark_success 同理,立刻释放 _current_task
        self._current_task = None
        self._status_icon.setText("⏹")
        self._phase.setText("已取消")
        self._cancel_btn.setVisible(False)

    def clear(self) -> None:
        self._current_task = None
        self._status_icon.setText("")
        self._task_name.setText("")
        self._phase.setText("")
        # v0.7.8.37l:不再 setVisible(False) —— 始终 visible,只清空内容
        # 让状态栏高度永远不变(占位 0 宽)
        self._cancel_btn.setVisible(False)

    @property
    def current_task(self):
        return self._current_task
