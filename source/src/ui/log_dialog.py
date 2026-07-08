"""错误日志面板：内存缓冲 + 弹窗显示。

最小可用集（不引第三方、不落盘、不分级、不过滤）：
- LogBuffer：list[str] 内存缓冲
- LogDialog：QPlainTextEdit 窗，按时间倒序显示
- main_window 在 task_started/finished/failed/cancelled 时调 buffer.append()

不监听 task 中间 output（会刷屏，状态栏阶段文字已经够用）。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton, QLabel,
)
from PySide6.QtCore import Qt, QObject, Signal

log = logging.getLogger("manju.log")


class LogBuffer(QObject):
    """日志缓冲。emit changed 后 dialog 自动刷新。

    不做线程安全约束：实际只在主线程调 append（main_window 的 task_* 槽都是 Qt 跨线程 queued 到主线程）。
    """

    changed = Signal()

    def __init__(self, max_lines: int = 5000, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._lines: List[str] = []
        self._max = max_lines

    def append(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self._lines.append(f"[{ts}] {text}")
        if len(self._lines) > self._max:
            # 丢最旧的
            del self._lines[: len(self._lines) - self._max]
        self.changed.emit()

    def clear(self) -> None:
        self._lines.clear()
        self.changed.emit()

    def lines(self) -> List[str]:
        """返回副本（外部用），时间倒序。"""
        return list(reversed(self._lines))

    def __len__(self) -> int:
        return len(self._lines)


class LogDialog(QDialog):
    """日志弹窗。打开时渲染当前 buffer 内容，按时间倒序。"""

    def __init__(self, buffer: LogBuffer, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("运行日志")
        self.setMinimumSize(720, 480)
        self._buffer = buffer
        self._build_ui()
        self._buffer.changed.connect(self._refresh)
        self._refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # 顶部信息行
        self._info = QLabel("")
        self._info.setStyleSheet("color: #666;")
        root.addWidget(self._info)

        # 日志正文
        self._view = QPlainTextEdit()
        self._view.setReadOnly(True)
        self._view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        # 等宽字体看起来更舒服
        font = self._view.font()
        font.setFamily("Consolas, 'Courier New', monospace")
        self._view.setFont(font)
        root.addWidget(self._view, 1)

        # 底部按钮
        bar = QHBoxLayout()
        self._btn_clear = QPushButton("🗑 清空日志")
        self._btn_clear.clicked.connect(self._buffer.clear)
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(self.accept)
        bar.addWidget(self._btn_clear)
        bar.addStretch(1)
        bar.addWidget(btn_close)
        root.addLayout(bar)

    def _refresh(self) -> None:
        n = len(self._buffer)
        self._info.setText(f"共 {n} 条记录（最新在上）")
        # 按时间倒序
        body = "\n".join(self._buffer.lines())
        # 保持光标在顶部（最新一条）
        self._view.setPlainText(body)
        cur = self._view.textCursor()
        cur.movePosition(cur.MoveOperation.Start)
        self._view.setTextCursor(cur)
