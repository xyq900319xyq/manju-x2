"""v0.7.8 资产参考图管理组件。

复刻自老 software D:\\剧本分镜助手\\templates\\index.html:1101-1173：
- 最多 16 张 base64 data URL
- 60×60 缩略图 + 图N 角标 + ▲▼(排序) + ✕(删除)
- + 按钮(点选多文件) + 拖拽上传
- on_change 回调(refs 列表变了就调,UI 层存 db)
"""
import base64
import logging
import mimetypes
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

log = logging.getLogger("manju.ui.ref_images")


class RefImagesWidget(QFrame):
    """v0.7.8:资产参考图管理 UI。

    用法:
        widget = RefImagesWidget(on_change=lambda refs: db.set_asset_ref_images(asset.id, refs))
        widget.set_refs(asset.ref_images)  # 从 db 加载
    """

    MAX_REFS = 16  # 复刻自老 software index.html:1122 `>= 16` 限制

    # 支持的图片后缀(小写)
    IMG_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")

    def __init__(
        self,
        on_change: Optional[Callable[[List[str]], None]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._on_change = on_change
        self._refs: List[str] = []
        self._build_ui()

    # ---------------- UI 构建 ----------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)
        self.setStyleSheet(
            "RefImagesWidget { background: #2A2A2A; border: 1px solid #3A3A3A; border-radius: 6px; }"
        )

        # 标题行
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        title = QLabel("📷 参考图（图生图，最多 16 张）")
        title.setStyleSheet("color: #B5B5B5; font-size: 12px; font-weight: 600; background: transparent; border: none;")
        head.addWidget(title)
        head.addStretch(1)
        self._count_lbl = QLabel("0 / 16")
        self._count_lbl.setStyleSheet("color: #888; font-size: 11px; background: transparent; border: none;")
        head.addWidget(self._count_lbl)
        outer.addLayout(head)

        # 网格行(横排 60×60 缩略图 + + 按钮)
        self._grid = QFrame()
        self._grid.setStyleSheet(
            "QFrame { background: #1F1F1F; border: 1px dashed #3A3A3A; border-radius: 6px; }"
        )
        self._grid.setAcceptDrops(True)
        # 拖拽事件直接挂到 grid(让整个 grid 都接受拖拽)
        self._grid.dragEnterEvent = self._on_drag_enter  # type: ignore
        self._grid.dragMoveEvent = self._on_drag_enter  # type: ignore
        self._grid.dropEvent = self._on_drop  # type: ignore
        self._grid_lay = QHBoxLayout(self._grid)
        self._grid_lay.setContentsMargins(6, 6, 6, 6)
        self._grid_lay.setSpacing(4)
        self._grid_lay.addStretch(1)
        outer.addWidget(self._grid)

    # ---------------- 公开 API ----------------

    def set_refs(self, refs: List[str]) -> None:
        """从 db 加载参考图(只更新内部列表,不触发 on_change)。"""
        # 限长 + 过滤空值
        self._refs = [r for r in (refs or []) if r][: self.MAX_REFS]
        self._render()

    def get_refs(self) -> List[str]:
        return list(self._refs)

    # ---------------- 渲染 ----------------

    def _render(self) -> None:
        # 清空 grid(保留 stretch)
        while self._grid_lay.count() > 1:
            item = self._grid_lay.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        # 加缩略图
        for i, ref in enumerate(self._refs):
            self._grid_lay.insertWidget(self._grid_lay.count() - 1, self._make_thumb(i, ref))
        # + 按钮(未满 16)
        if len(self._refs) < self.MAX_REFS:
            self._grid_lay.insertWidget(self._grid_lay.count() - 1, self._make_add_btn())
        # 计数
        self._count_lbl.setText(f"{len(self._refs)} / {self.MAX_REFS}")

    def _make_thumb(self, idx: int, data_url: str) -> QFrame:
        """单张缩略图(60×60 + 图N + ▲▼✕)。"""
        f = QFrame()
        f.setFixedSize(60, 60)
        f.setStyleSheet(
            "QFrame { background: #252525; border: 1px solid #4A4A4A; border-radius: 4px; }"
        )
        lay = QVBoxLayout(f)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # 缩略图(占上 44px)
        img = QLabel()
        img.setFixedSize(60, 44)
        img.setAlignment(Qt.AlignCenter)
        img.setStyleSheet("background: transparent; border: none;")
        b = self._data_url_to_bytes(data_url)
        if b:
            pix = QPixmap()
            if pix.loadFromData(b):
                img.setPixmap(
                    pix.scaled(58, 42, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            else:
                img.setText("❓")
                img.setStyleSheet("color: #888; font-size: 11px; background: transparent; border: none;")
        else:
            img.setText("❓")
            img.setStyleSheet("color: #888; font-size: 11px; background: transparent; border: none;")
        lay.addWidget(img)
        # v0.7.8.27:点击缩略图 → ImagePreviewDialog 全屏预览。
        # 写临时 PNG(因为 ImagePreviewDialog 接受 file path,
        # 参考图在 db 里是 base64 data URL,不能直接传)。
        img.setCursor(Qt.PointingHandCursor)
        img.setToolTip(f"图{idx + 1} · 点击放大")
        img.mousePressEvent = lambda _e, _b=b: self._on_thumb_clicked(_b)  # type: ignore

        # 角标行(图N + ▲▼✕,16px 高)
        bar_w = QFrame()
        bar_w.setFixedHeight(16)
        bar_w.setStyleSheet("background: rgba(0,0,0,0.5); border: none; border-radius: 0 0 4px 4px;")
        bar = QHBoxLayout(bar_w)
        bar.setContentsMargins(2, 0, 2, 0)
        bar.setSpacing(1)
        num = QLabel(f"图{idx + 1}")
        num.setStyleSheet("color: white; font-size: 9px; background: transparent; border: none;")
        bar.addWidget(num)
        bar.addStretch(1)
        if idx > 0:
            bar.addWidget(self._mini_btn("▲", lambda: self._on_move(idx, -1)))
        if idx < len(self._refs) - 1:
            bar.addWidget(self._mini_btn("▼", lambda: self._on_move(idx, 1)))
        bar.addWidget(self._mini_btn("✕", lambda: self._on_remove(idx), color="rgba(200,60,60,0.7)"))
        lay.addWidget(bar_w)
        return f

    def _mini_btn(self, text: str, on_click: Callable[[], None], color: str = "rgba(0,0,0,0.4)") -> QLabel:
        """16×16 角标按钮(用 QLabel + mousePressEvent 实现点击,避免 QPushButton 高度问题)。"""
        b = QLabel(text)
        b.setFixedSize(14, 14)
        b.setAlignment(Qt.AlignCenter)
        b.setStyleSheet(
            f"color: white; font-size: 9px; background: {color}; border-radius: 2px;"
        )
        b.setCursor(Qt.PointingHandCursor)
        b.mousePressEvent = lambda e: on_click()  # type: ignore
        return b

    def _on_thumb_clicked(self, png_bytes: bytes) -> None:
        """v0.7.8.27:参考图缩略图点击 → 全屏预览。

        把 base64 解码后的 PNG 字节写到系统 temp 目录的 1 个 .png,
        传给 ImagePreviewDialog,dialog 关闭后清理。
        """
        import tempfile
        import os as _os
        if not png_bytes:
            return
        tmp_path: Optional[str] = None
        try:
            tmp = tempfile.NamedTemporaryFile(
                prefix="manju_ref_", suffix=".png", delete=False,
            )
            tmp.write(png_bytes)
            tmp.flush()
            tmp.close()
            tmp_path = tmp.name
            from ui.image_preview_dialog import ImagePreviewDialog
            dlg = ImagePreviewDialog(tmp_path, parent=self)
            dlg.exec()
        except Exception:
            log.exception("RefImagesWidget._on_thumb_clicked 失败")
        finally:
            if tmp_path:
                try:
                    _os.unlink(tmp_path)
                except OSError:
                    pass

    def _make_add_btn(self) -> QLabel:
        """+ 按钮(点击弹文件选择)。"""
        btn = QLabel("+")
        btn.setFixedSize(60, 60)
        btn.setAlignment(Qt.AlignCenter)
        btn.setStyleSheet(
            "color: #888; font-size: 26px; border: 1px dashed #555; border-radius: 4px; background: transparent;"
        )
        btn.setCursor(Qt.PointingHandCursor)
        btn.mousePressEvent = lambda e: self._on_add()  # type: ignore
        return btn

    # ---------------- 操作 ----------------

    def _on_add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选参考图（可多选）",
            "",
            "图片 (*.png *.jpg *.jpeg *.webp *.bmp)",
        )
        added = 0
        for p in paths:
            if len(self._refs) >= self.MAX_REFS:
                break
            if not p.lower().endswith(self.IMG_EXTS):
                continue
            try:
                self._refs.append(self._path_to_data_url(p))
                added += 1
            except Exception as e:
                log.warning("读参考图失败 %s: %s", p, e)
        if added:
            self._render()
            self._notify()

    def _on_remove(self, idx: int) -> None:
        if 0 <= idx < len(self._refs):
            self._refs.pop(idx)
            self._render()
            self._notify()

    def _on_move(self, idx: int, direction: int) -> None:
        new = idx + direction
        if 0 <= new < len(self._refs):
            self._refs[idx], self._refs[new] = self._refs[new], self._refs[idx]
            self._render()
            self._notify()

    def _notify(self) -> None:
        if self._on_change:
            try:
                self._on_change(list(self._refs))
            except Exception:
                log.exception("RefImagesWidget on_change 回调失败")

    # ---------------- 拖拽 ----------------

    def _on_drag_enter(self, e) -> None:
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def _on_drop(self, e) -> None:
        added = 0
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if not p or not p.lower().endswith(self.IMG_EXTS):
                continue
            if len(self._refs) >= self.MAX_REFS:
                break
            try:
                self._refs.append(self._path_to_data_url(p))
                added += 1
            except Exception as ex:
                log.warning("拖入参考图失败 %s: %s", p, ex)
        if added:
            self._render()
            self._notify()

    # ---------------- 工具 ----------------

    @staticmethod
    def _path_to_data_url(path: str) -> str:
        mime, _ = mimetypes.guess_type(path)
        if not mime:
            mime = "image/png"
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return f"data:{mime};base64,{b64}"

    @staticmethod
    def _data_url_to_bytes(data_url: str) -> bytes:
        if not data_url:
            return b""
        if data_url.startswith("data:"):
            idx = data_url.find(",")
            if idx > 0:
                try:
                    return base64.b64decode(data_url[idx + 1:])
                except Exception:
                    return b""
        return b""
