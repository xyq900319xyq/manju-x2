"""v0.7.7：图片全屏预览对话框（lightbox）。

复刻自老 software D:\\剧本分镜助手\\templates\\index.html:2123-2132 `previewImage()`：
- 全屏黑色半透明遮罩（rgba(0,0,0,0.9)）+ 大图
- 点击任意位置关闭（与老 software 行为一致）
- ESC 关闭（增强，老 software 没做）
- 大图按比例缩放到 90vw × 90vh
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QDialog, QLabel, QVBoxLayout, QWidget,
)


class ImagePreviewDialog(QDialog):
    """v0.7.7：全屏 lightbox 点图放大。

    用法：
        dlg = ImagePreviewDialog("/path/to/image.png", parent=main_window)
        dlg.exec()
    """

    def __init__(self, image_path: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._image_path = image_path
        self._build_ui()

    def _build_ui(self) -> None:
        # 全屏无边框（与老 software previewImage 等价：position:fixed; top:0; left:0; w/h:100%）
        self.setWindowTitle("图片预览（点击关闭）")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowState(Qt.WindowState.WindowFullScreen)
        # 半透明黑底（rgba(0,0,0,0.9) 复刻）
        self.setStyleSheet("QDialog { background-color: rgba(0, 0, 0, 230); }")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel()
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("background: transparent;")
        lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        pix = QPixmap(self._image_path)
        if pix.isNull():
            lbl.setText(f"(无法加载图片: {self._image_path})")
            lbl.setStyleSheet("color: #FF6B6B; font-size: 18px; background: transparent;")
        else:
            # 等比缩放到屏幕 90%（max-width:90vw; max-height:90vh 复刻）
            from PySide6.QtGui import QGuiApplication
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                avail = screen.availableGeometry()
                max_w = int(avail.width() * 0.9)
                max_h = int(avail.height() * 0.9)
            else:
                max_w, max_h = 1600, 1000
            scaled = pix.scaled(
                max_w, max_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            lbl.setPixmap(scaled)
            lbl.setToolTip(Path(self._image_path).name)
        outer.addWidget(lbl)

        # 任意位置点击关闭（复刻 index.html:2126 `modal.onclick = function() { modal.remove(); }`）
        self.setMouseTracking(True)
        lbl.setMouseTracking(True)
        lbl.mousePressEvent = self._on_click_anywhere  # type: ignore[assignment]

    def _on_click_anywhere(self, _ev) -> None:  # noqa: ANN001
        self.accept()

    def keyPressEvent(self, ev: QKeyEvent) -> None:  # noqa: N802
        # ESC 关闭（增强，老 software 只有 click 关闭）
        if ev.key() == Qt.Key.Key_Escape:
            self.accept()
            return
        super().keyPressEvent(ev)
