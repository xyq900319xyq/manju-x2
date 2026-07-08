"""v0.6.23：资产历史文件浏览对话框（图片 + 音频网格）。

复刻自原软件 D:\\剧本分镜助手\\server.py:1737-1793 `GET /browse/<path>` 的 UI：
- 网格展示 outputs/<项目>/assets/<资产>/ 下所有图片 + 音频
- 图片显示缩略图 + 文件名 + 大小 + "⭐ 选为当前图" 按钮
- 音频显示 🎵 图标 + 文件名 + 大小 + "🎵 选为当前音频" 按钮
- 当前选中的图 / 音频按钮高亮（绿/紫）

调用：
    dlg = AssetBrowserDialog(parent, project, asset, db, config)
    if dlg.exec():
        # 用户在 dlg 内部已点击 select 按钮，db 已更新
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton, QScrollArea,
    QWidget, QGridLayout, QFrame, QMessageBox, QDialogButtonBox,
)

from core.asset_browser import (
    AssetFile, list_asset_files, find_asset_dir, pick_image_as_current, pick_audio_as_current,
)
from core.database import Database
from core.models import Asset, Project

log = logging.getLogger("manju.ui.asset_browser")


# 卡片大小
THUMB_SIZE = 150
CARD_WIDTH = 180
CARD_HEIGHT = 230


class _AssetCard(QFrame):
    """v0.6.23：单条文件卡片（缩略图 / 音频 icon + 文件名 + select 按钮）。"""

    def __init__(
        self,
        file: AssetFile,
        is_current_image: bool,
        is_current_audio: bool,
        on_pick_image,
        on_pick_audio,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._file = file
        self._on_pick_image = on_pick_image
        self._on_pick_audio = on_pick_audio
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setStyleSheet(
            "_AssetCard { background: #fafafa; border: 1px solid #e0e0e0; border-radius: 4px; }"
        )
        self._build_ui(is_current_image, is_current_audio)

    def _build_ui(self, is_current_image: bool, is_current_audio: bool) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(4)

        # 缩略图 / 音频 icon
        if self._file.kind == "image":
            pix = QPixmap(self._file.path)
            if not pix.isNull():
                thumb = pix.scaled(
                    THUMB_SIZE, THUMB_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                lbl = QLabel()
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setFixedSize(THUMB_SIZE, THUMB_SIZE)
                lbl.setPixmap(thumb)
                outer.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
            else:
                lbl = QLabel("(损坏)")
                lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                lbl.setFixedSize(THUMB_SIZE, THUMB_SIZE)
                outer.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)
        else:
            # 音频：显示大 icon
            lbl = QLabel("🎵")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setFixedSize(THUMB_SIZE, THUMB_SIZE)
            lbl.setStyleSheet("font-size: 64px; color: #8b5cf6;")
            outer.addWidget(lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        # 文件名（截断）
        name_lbl = QLabel(self._file.name)
        name_lbl.setWordWrap(True)
        name_lbl.setStyleSheet("font-size: 10px; color: #555;")
        name_lbl.setToolTip(self._file.path)
        outer.addWidget(name_lbl)

        # 大小
        size_kb = self._file.size / 1024.0
        size_lbl = QLabel(f"{size_kb:.1f} KB")
        size_lbl.setStyleSheet("font-size: 9px; color: #888;")
        outer.addWidget(size_lbl)

        outer.addStretch(1)

        # select 按钮
        if self._file.kind == "image":
            if is_current_image:
                btn = QPushButton("✅ 当前图片")
                btn.setStyleSheet("background: #f59e0b; color: #fff; font-weight: bold;")
                btn.setEnabled(False)
            else:
                btn = QPushButton("⭐ 选为当前")
                btn.setStyleSheet("background: #238636; color: #fff;")
            btn.clicked.connect(lambda: self._on_pick_image(self._file))
            outer.addWidget(btn)
        else:
            if is_current_audio:
                btn = QPushButton("🎵 当前音频")
                btn.setStyleSheet("background: #8b5cf6; color: #fff; font-weight: bold;")
                btn.setEnabled(False)
            else:
                btn = QPushButton("🎵 选为音频")
                btn.setStyleSheet("background: #6e40c9; color: #fff;")
            btn.clicked.connect(lambda: self._on_pick_audio(self._file))
            outer.addWidget(btn)


class AssetBrowserDialog(QDialog):
    """v0.6.23：资产历史文件浏览对话框。"""

    def __init__(
        self,
        project: Project,
        asset: Asset,
        db: Database,
        outputs_dir: Path,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._project = project
        self._asset = asset
        self._db = db
        self._outputs_dir = Path(outputs_dir)
        self._files: list[AssetFile] = []
        self._build_ui()
        self._load_files()

    def _build_ui(self) -> None:
        self.setWindowTitle(f"🖼 历史文件 - {self._asset.name}")
        self.resize(820, 600)

        outer = QVBoxLayout(self)

        # 顶部信息
        info_lbl = QLabel(
            f"<b>项目:</b> {self._project.name}  "
            f"<b>资产:</b> {self._asset.name}  "
            f"<b>当前图:</b> {Path(self._asset.image_path).name if self._asset.image_path else '(无)'}"
        )
        info_lbl.setStyleSheet("padding: 4px; background: #f5f5f5;")
        outer.addWidget(info_lbl)

        # 滚动区
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { background: #fff; }")
        outer.addWidget(self._scroll, 1)

        # 容器 widget
        self._container = QWidget()
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(8, 8, 8, 8)
        self._grid.setSpacing(8)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._scroll.setWidget(self._container)

        # 底部按钮
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_box.rejected.connect(self.reject)
        outer.addWidget(btn_box)

    def _load_files(self) -> None:
        """扫描资产目录，加载所有图片 + 音频。"""
        asset_dir = find_asset_dir(
            self._outputs_dir, self._project.name, self._asset.name,
        )
        self._files = list_asset_files(asset_dir)
        self._render_grid()

    def _render_grid(self) -> None:
        """清空 grid，按行重排卡片。"""
        # 清空现有
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget() if item else None
            if w is not None:
                w.deleteLater()

        if not self._files:
            empty = QLabel(f"📂 该资产还没有历史文件\n\n{find_asset_dir(self._outputs_dir, self._project.name, self._asset.name)}")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #999; font-size: 14px; padding: 40px;")
            self._grid.addWidget(empty, 0, 0)
            return

        # 计算当前选中的图 / 音频
        current_image_path = self._asset.image_path or ""
        current_audio_path = ""
        try:
            current_audio_path = self._db.get_audio_selection(self._project.id, self._asset.name) or ""
        except Exception:  # noqa: BLE001
            pass

        # 按 4 列布局
        cols = 4
        for idx, f in enumerate(self._files):
            row, col = divmod(idx, cols)
            is_cur_img = (f.kind == "image" and current_image_path and f.path == current_image_path)
            is_cur_aud = (f.kind == "audio" and current_audio_path and f.path == current_audio_path)
            card = _AssetCard(
                f, is_cur_img, is_cur_aud,
                on_pick_image=self._on_pick_image,
                on_pick_audio=self._on_pick_audio,
            )
            self._grid.addWidget(card, row, col)

    @Slot(object)
    def _on_pick_image(self, file: AssetFile) -> None:
        """v0.6.23：把选中图片写入 db，刷新网格。"""
        try:
            pick_image_as_current(
                self._db, self._project.id, self._asset.name, file.path,
            )
        except Exception as e:  # noqa: BLE001
            log.exception("pick image failed")
            QMessageBox.critical(self, "错误", f"选图失败: {e}")
            return
        # 重新读 asset
        assets = self._db.list_assets(self._project.id)
        new_asset = next((a for a in assets if a.name == self._asset.name), None)
        if new_asset:
            self._asset = new_asset
        self._render_grid()
        QMessageBox.information(self, "提示", f"✓ 已选为当前图片: {file.name}")

    @Slot(object)
    def _on_pick_audio(self, file: AssetFile) -> None:
        """v0.6.23：把选中音频写入 db，刷新网格。"""
        try:
            pick_audio_as_current(
                self._db, self._project.id, self._asset.name, file.path,
            )
        except Exception as e:  # noqa: BLE001
            log.exception("pick audio failed")
            QMessageBox.critical(self, "错误", f"选音频失败: {e}")
            return
        self._render_grid()
        QMessageBox.information(self, "提示", f"✓ 已选为当前音频: {file.name}")
