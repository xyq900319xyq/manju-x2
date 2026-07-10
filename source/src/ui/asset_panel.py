"""资产清单面板：剧集详情 Tab 之一。

v0.7.0 改造（方案 C：master-detail 布局）：
- 每段（人物/场景/物品）内部改用 QSplitter 水平分割
- 左侧：紧凑列表（缩略图小图标 + 资产名 + 类型 tag + 状态）
- 右侧：单例详情（缩略图大图 + 描述 + Prompt 编辑 + 按钮行 + 音频行）
- 16+ 资产时可滚动列表、详情区只占一段空间
- 详情复用 AssetPanel 组件

显示项目级资产（从 assets 表），按钮：
- 提取项目资产（调 AssetExtractTask）
- 单个资产 生图（调 AssetImageTask）
- 打开已生成的图片
"""
import logging
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import Qt, Slot, QSize, QTimer
from PySide6.QtGui import QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QGroupBox, QMessageBox, QFrame,
    QFileDialog, QDialog, QPlainTextEdit, QDialogButtonBox,
    QSplitter, QListWidget, QListWidgetItem, QSizePolicy,
    QAbstractItemView, QStyledItemDelegate, QStyle,
)

from core.database import Database
from core.generators import AssetExtractTask, AssetImageTask, BatchAssetImageTask
from core.models import ASSET_KIND_LABELS, Asset, Project
from ui.ref_images_widget import RefImagesWidget

log = logging.getLogger("manju.ui.asset")


# ----------------------------------------------------------------------
# v0.7.8:Win32 原生文件选择对话框（QFileDialog / tkinter 都被 PyInstaller 打包干掉）
# ----------------------------------------------------------------------
def _win32_open_file_dialog(initial_dir: str = "") -> str:
    """v0.7.8:用 comdlg32.GetOpenFileNameW 弹 Windows 原生文件选择。

    QFileDialog(PySide6.QtWidgets)在 PyInstaller 打包下卡死不返回,tkinter
    在 PySide6 进程里 Tk() 也卡死 — 都不行。改用 Win32 API:
    - 完全不依赖 GUI 框架
    - PyInstaller 不需要 collect 任何东西(ctypes/windll 是 stdlib)
    - 弹的是 Windows 资源管理器自己的 dialog,稳如系统本身
    - user 关掉或取消 → 返回 ""
    - user 选文件 → 返回完整路径

    Args:
        initial_dir: 初始目录,空字符串用默认

    Returns:
        选中的文件完整路径,或 "" (取消/失败)
    """
    import ctypes
    from ctypes import wintypes

    try:
        comdlg32 = ctypes.windll.comdlg32
        # Win32 GetOpenFileNameW 签名:BOOL GetOpenFileNameW(LPOPENFILENAMEW)
        # 只 1 个参数,hwndOwner 在 OPENFILENAMEW.hwndOwner 字段里。
        comdlg32.GetOpenFileNameW.restype = wintypes.BOOL
        comdlg32.GetOpenFileNameW.argtypes = [ctypes.c_void_p]
    except Exception as e:
        log.exception("v0.7.8:加载 comdlg32 失败: %s", e)
        return ""

    # OPENFILENAMEW 结构（只填我们用到的字段,其余置 0）
    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", ctypes.c_void_p),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", ctypes.c_void_p),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    # OFN_EXPLORER = 0x00080000, OFN_FILEMUSTEXIST = 0x00001000, OFN_HIDEREADONLY = 0x00000004
    OFN_EXPLORER = 0x00080000
    OFN_FILEMUSTEXIST = 0x00001000
    OFN_HIDEREADONLY = 0x00000004

    # 文件类型 filter:"图片\0*.png;*.jpg;*.jpeg;*.webp;*.bmp\0所有文件\0*.*\0\0"
    filter_str = "图片\0*.png;*.jpg;*.jpeg;*.webp;*.bmp\0所有文件\0*.*\0\0"
    # buffer 给 4096 字符
    buf = ctypes.create_unicode_buffer(4096)
    # 初始目录
    init = initial_dir if initial_dir and Path(initial_dir).exists() else None

    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = 0
    ofn.lpstrFilter = filter_str
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
    ofn.nMaxFile = 4096
    ofn.lpstrInitialDir = init
    ofn.lpstrTitle = "选择资产图片"
    ofn.Flags = OFN_EXPLORER | OFN_FILEMUSTEXIST | OFN_HIDEREADONLY

    try:
        ok = comdlg32.GetOpenFileNameW(ctypes.byref(ofn))
    except Exception as e:
        log.exception("v0.7.8:Win32 GetOpenFileNameW 异常: %s", e)
        return ""
    if not ok:
        # CommDlgExtendedError 看具体错误
        try:
            err = comdlg32.CommDlgExtendedError()
            log.warning("v0.7.8:Win32 GetOpenFileNameW 取消/失败,err=%d", err)
        except Exception as e:
            # v1.1.5【C10 修复】:留 log 让用户能问的时候有迹可循
            log.debug("comdlg32 不可用: %s", e)
        return ""
    return buf.value


# ----------------------------------------------------------------------
# v0.7.8.14:Win32 原生**多选**文件选择（用于剧本导入）
# ----------------------------------------------------------------------
def _win32_open_files_dialog(
    title: str = "选择文件（可多选）",
    file_filter: str = "所有文件 (*.*)\0*.*\0\0",
    initial_dir: str = "",
) -> list[str]:
    """v0.7.8.14:用 comdlg32.GetOpenFileNameW **多选**文件。

    跟 _win32_open_file_dialog 区别:加 OFN_ALLOWMULTISELECT(0x00000200) +
    OFN_EXPLORER(0x00080000),buffer 给大一点(32K)容多文件。多个路径用 \0
    分隔,末尾 \0\0 结束。

    Returns:
        选中的文件路径列表。取消 / 失败返回 []。
    """
    import ctypes
    from ctypes import wintypes

    try:
        comdlg32 = ctypes.windll.comdlg32
        comdlg32.GetOpenFileNameW.restype = wintypes.BOOL
        comdlg32.GetOpenFileNameW.argtypes = [ctypes.c_void_p]
    except Exception as e:
        log.exception("v0.7.8.14:加载 comdlg32 失败: %s", e)
        return []

    class OPENFILENAMEW(ctypes.Structure):
        _fields_ = [
            ("lStructSize", wintypes.DWORD),
            ("hwndOwner", wintypes.HWND),
            ("hInstance", wintypes.HINSTANCE),
            ("lpstrFilter", wintypes.LPCWSTR),
            ("lpstrCustomFilter", wintypes.LPWSTR),
            ("nMaxCustFilter", wintypes.DWORD),
            ("nFilterIndex", wintypes.DWORD),
            ("lpstrFile", wintypes.LPWSTR),
            ("nMaxFile", wintypes.DWORD),
            ("lpstrFileTitle", wintypes.LPWSTR),
            ("nMaxFileTitle", wintypes.DWORD),
            ("lpstrInitialDir", wintypes.LPCWSTR),
            ("lpstrTitle", wintypes.LPCWSTR),
            ("Flags", wintypes.DWORD),
            ("nFileOffset", wintypes.WORD),
            ("nFileExtension", wintypes.WORD),
            ("lpstrDefExt", wintypes.LPCWSTR),
            ("lCustData", wintypes.LPARAM),
            ("lpfnHook", ctypes.c_void_p),
            ("lpTemplateName", wintypes.LPCWSTR),
            ("pvReserved", ctypes.c_void_p),
            ("dwReserved", wintypes.DWORD),
            ("FlagsEx", wintypes.DWORD),
        ]

    OFN_EXPLORER = 0x00080000
    OFN_FILEMUSTEXIST = 0x00001000
    OFN_HIDEREADONLY = 0x00000004
    OFN_ALLOWMULTISELECT = 0x00000200

    buf = ctypes.create_unicode_buffer(32768)
    init = initial_dir if initial_dir and Path(initial_dir).exists() else None
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = 0
    ofn.lpstrFilter = file_filter
    ofn.nFilterIndex = 1
    ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
    ofn.nMaxFile = 32768
    ofn.lpstrInitialDir = init
    ofn.lpstrTitle = title
    ofn.Flags = (
        OFN_EXPLORER | OFN_FILEMUSTEXIST | OFN_HIDEREADONLY | OFN_ALLOWMULTISELECT
    )

    try:
        ok = comdlg32.GetOpenFileNameW(ctypes.byref(ofn))
    except Exception as e:
        log.exception("v0.7.8.14:Win32 GetOpenFileNameW 多选异常: %s", e)
        return []
    if not ok:
        try:
            err = comdlg32.CommDlgExtendedError()
            log.info("v0.7.8.14:Win32 多选 dialog 取消/失败 err=%d", err)
        except Exception:
            pass
        return []

    # 多选时,buffer 格式: "<dir>\0<file1>\0<file2>\0...\0\0"
    # 单选时: "<full_path>\0\0"
    raw = buf.value
    parts = raw.split("\0")
    # 去掉末尾空串
    while parts and parts[-1] == "":
        parts.pop()
    if not parts:
        return []
    if len(parts) == 1:
        # 单选
        return [parts[0]]
    # 多选:第一个是目录,后面是文件名,拼成完整路径
    base_dir = parts[0]
    out = []
    for name in parts[1:]:
        out.append(str(Path(base_dir) / name))
    return out


# ========================================================================
# 详情区（master-detail 的右侧）
# ========================================================================

class AssetPanel(QFrame):
    """单个资产详情：左侧缩略图 + 右侧描述 + 操作按钮。

    v0.7.0：改成详情专用，被外层列表选中时 refresh(asset) 切换内容。
    旧版本是"每个资产一个独立面板"（纵向堆 16 个），太占空间。
    v0.7.8.49:_thumb_cache 给 494x373 大缩略图加 mtime 缓存,避免
    show_asset 每次都重读 + SmoothTransformation 重采样(50-200ms)。
    """

    # v0.7.8.49:全 AssetPanel 共用一份大图缓存,切不同资产不重复 load
    _THUMB_CACHE: dict = {}
    _THUMB_CACHE_MAX = 64

    @classmethod
    def _get_thumb_cached(cls, path: str, w: int, h: int):
        try:
            mt = Path(path).stat().st_mtime
        except OSError:
            return None
        key = (path, mt, w, h)
        cached = cls._THUMB_CACHE.get(key)
        if cached is not None:
            return cached
        if len(cls._THUMB_CACHE) > cls._THUMB_CACHE_MAX:
            cls._THUMB_CACHE.clear()
        pix = QPixmap(path)
        if pix.isNull():
            return None
        scaled = pix.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        cls._THUMB_CACHE[key] = scaled
        return scaled

    def __init__(
        self,
        project: Project,
        db: Database,
        on_enqueue: Callable,
        on_open_outputs: Callable[[Path], None],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._asset: Optional[Asset] = None
        self._project = project
        self._db = db
        self._on_enqueue = on_enqueue
        self._on_open_outputs = on_open_outputs
        self._built = False
        self._build_ui()
        self.setVisible(False)  # 初始隐藏

    def _build_ui(self) -> None:
        if self._built:
            return
        self._built = True
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # 头部：kind + name + 状态
        head = QHBoxLayout()
        self._kind_lbl = QLabel("")
        head.addWidget(self._kind_lbl)
        self._name_lbl = QLabel("")
        self._name_lbl.setStyleSheet("font-size: 14px; font-weight: bold;")
        self._name_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        head.addWidget(self._name_lbl, 1)
        self._status_lbl = QLabel("")
        head.addWidget(self._status_lbl)
        outer.addLayout(head)

        # 主体：左侧大缩略图 / 右侧上下(描述 + Prompt)
        # v0.7.8.27:按用户要求重排版,缩略图放大成 340x380 大方框,
        # 描述 + Prompt 在右面竖排(各占 1 份,Prompt 不再被压成 100px)。
        body = QHBoxLayout()
        body.setSpacing(12)

        # 缩略图区(大框,左边) — v0.7.8.29:4:3 比例,高 380 → 宽 506
        thumb_box = QGroupBox()
        thumb_box.setFixedSize(506, 380)
        thumb_box.setTitle("缩略图（点击放大）")
        thumb_lay = QVBoxLayout(thumb_box)
        thumb_lay.setContentsMargins(6, 6, 6, 6)
        self._thumb = QLabel()
        self._thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumb.setStyleSheet(
            "background: #1E1E1E; color: #777;"
            "QLabel:hover { background: #2A2A2A; }"  # v0.7.7:hover 提示
        )
        # 4:3 = 494:373(506 - 12 padding = 494, 380 - 7 padding = 373)
        self._thumb.setFixedSize(494, 373)
        self._thumb.setText("(未生成)")
        # v0.7.7:缩略图点击触发全屏预览
        self._thumb.setCursor(Qt.CursorShape.PointingHandCursor)
        self._thumb.mousePressEvent = self._on_thumb_clicked  # type: ignore[assignment]
        thumb_lay.addWidget(self._thumb)
        body.addWidget(thumb_box)

        # 右半区:上下 = 描述 + Prompt(用 QWidget 包 QVBoxLayout)
        right_w = QWidget()
        right_lay = QVBoxLayout(right_w)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(8)

        # 描述区(上半)
        desc_box = QGroupBox("描述")
        desc_lay = QVBoxLayout(desc_box)
        desc_lay.setContentsMargins(4, 4, 4, 4)
        desc_scroll = QScrollArea()
        desc_scroll.setWidgetResizable(True)
        desc_scroll.setStyleSheet("background: transparent; border: none;")
        self._desc_text = QLabel("")
        self._desc_text.setWordWrap(True)
        self._desc_text.setStyleSheet("color: #DDD; background: transparent;")
        self._desc_text.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._desc_text.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        desc_scroll.setWidget(self._desc_text)
        desc_lay.addWidget(desc_scroll, 1)
        right_lay.addWidget(desc_box, 1)

        # Prompt 编辑(下半)
        prompt_box = QGroupBox("✏️ Prompt 编辑（生图前可改）")
        prompt_lay = QVBoxLayout(prompt_box)
        prompt_lay.setContentsMargins(8, 8, 8, 8)
        self._prompt_edit = QPlainTextEdit()
        self._prompt_edit.setPlaceholderText(
            "留空 = 用默认 prompt 模板(来自 description)。\n"
            "改这里后会自动存盘,下次生图用你改的版本。"
        )
        self._prompt_edit.setStyleSheet("background: #252525; font-size: 11px;")
        # v0.7.8.27:取消 100px 限制,跟随右半区弹性伸展
        self._prompt_edit.textChanged.connect(self._on_prompt_changed)
        prompt_lay.addWidget(self._prompt_edit, 1)
        self._prompt_save_lbl = QLabel("")
        self._prompt_save_lbl.setStyleSheet("color: #888; font-size: 11px;")
        prompt_lay.addWidget(self._prompt_save_lbl)
        # v0.7.7 重打 8:删 800ms 自动保存定时器,改完 keystroke 立即同步写库
        self._prompt_dirty = False
        self._prompt_initial = ""
        right_lay.addWidget(prompt_box, 1)

        body.addWidget(right_w, 1)
        outer.addLayout(body)

        # v0.7.8:📷 参考图(图生图支持)
        # 复刻自老 software D:\剧本分镜助手\templates\index.html:1101-1173
        # 数据存 assets.ref_images (db JSON 字段),生图时 generators.py 读
        self._ref_widget = RefImagesWidget(on_change=self._on_refs_changed)
        outer.addWidget(self._ref_widget)

        # 按钮行
        btn_row = QHBoxLayout()
        self._btn_image = QPushButton("🎨 生图")
        self._btn_image.setFixedHeight(30)
        self._btn_image.clicked.connect(self._on_click_image)
        btn_row.addWidget(self._btn_image)

        self._btn_upload = QPushButton("📤 上传图片")
        self._btn_upload.setFixedHeight(30)
        self._btn_upload.setToolTip("从本地选一张图作为本资产图片（覆盖 AI 生成的）")
        self._btn_upload.clicked.connect(self._on_click_upload)
        btn_row.addWidget(self._btn_upload)

        self._btn_browse = QPushButton("🖼 浏览历史")
        self._btn_browse.setFixedHeight(30)
        self._btn_browse.setToolTip("浏览本资产目录下的所有历史图片 + 音频，选为当前")
        self._btn_browse.clicked.connect(self._on_click_browse)
        btn_row.addWidget(self._btn_browse)

        self._btn_open = QPushButton("📄 打开文件")
        self._btn_open.setFixedHeight(30)
        self._btn_open.clicked.connect(self._on_click_open)
        btn_row.addWidget(self._btn_open)

        self._btn_audio = QPushButton("🎵 选音频")
        self._btn_audio.setFixedHeight(30)
        self._btn_audio.setToolTip("从本地选一个音频文件作为本资产背景音")
        self._btn_audio.clicked.connect(self._on_click_audio)
        btn_row.addWidget(self._btn_audio)

        self._ts_lbl = QLabel("")
        self._ts_lbl.setStyleSheet("color: #888;")
        btn_row.addWidget(self._ts_lbl, 1)
        outer.addLayout(btn_row)

        # v0.6.20：🔊 当前音频展示行
        self._audio_row = QHBoxLayout()
        self._audio_lbl = QLabel("")
        self._audio_lbl.setStyleSheet("color: #B5B5B5; font-size: 11px;")
        self._audio_lbl.setWordWrap(True)
        self._audio_row.addWidget(self._audio_lbl, 1)
        self._btn_clear_audio = QPushButton("🗑 清音频")
        self._btn_clear_audio.setFixedHeight(24)
        self._btn_clear_audio.setToolTip("清除本资产选定的音频")
        self._btn_clear_audio.clicked.connect(self._on_click_clear_audio)
        self._audio_row.addWidget(self._btn_clear_audio)
        outer.addLayout(self._audio_row)

        # 整体设为深色背景
        self.setStyleSheet("AssetPanel { background: #353535; border: 1px solid #4A4A4A; border-radius: 4px; }")

    def show_asset(self, asset: Asset) -> None:
        """v0.7.0：列表选中后切到该资产的详情。"""
        self._asset = asset
        self.setVisible(True)
        # 头部
        self._kind_lbl.setText(f"<b>[{ASSET_KIND_LABELS.get(asset.kind, asset.kind)}]</b>")
        self._kind_lbl.setStyleSheet(self._kind_color(asset.kind))
        self._name_lbl.setText(asset.name)
        self._status_lbl.setText(self._status_text())
        self._status_lbl.setStyleSheet(self._status_color())
        # 描述
        self._desc_text.setText(asset.description or "(无描述)")
        # v0.7.0：prompt 编辑框默认显示 description（用户看到"生图关键词"），
        # 用户改后存到 image_prompt 字段；空 image_prompt 时生图任务用 description
        # 当 prompt（保持原行为）。
        # v0.7.7 重打 18：user 反馈"默认=描述本身"做法不对，
        # 这里应该显示 description 里"中文指令词"段（生图关键词），不是整个 description。
        # 三级 fallback：
        #   1. asset.image_prompt（用户已编辑）
        #   2. 从 description 提取"中文指令词"段（_extract_image_prompt）
        #   3. asset.description（最后兜底，正常情况不会到这）
        from core.asset_parser import _extract_image_prompt
        if asset.image_prompt:
            cur_prompt = asset.image_prompt
        else:
            extracted = _extract_image_prompt(asset.description or "")
            cur_prompt = extracted or asset.description or ""
        if cur_prompt != self._prompt_initial:
            self._prompt_initial = cur_prompt
            self._prompt_edit.blockSignals(True)
            self._prompt_edit.setPlainText(cur_prompt)
            self._prompt_edit.blockSignals(False)
            self._prompt_dirty = False
            if asset.image_prompt:
                self._prompt_save_lbl.setText("✓ 已保存（自定义）")
                self._prompt_save_lbl.setStyleSheet("color: #FF8C42; font-size: 11px;")
            elif _extract_image_prompt(asset.description or ""):
                self._prompt_save_lbl.setText("○ 默认 = 中文指令词段（自动提取）")
                self._prompt_save_lbl.setStyleSheet("color: #888; font-size: 11px;")
            else:
                self._prompt_save_lbl.setText("○ 默认 = 描述本身（无中文指令词段）")
                self._prompt_save_lbl.setStyleSheet("color: #888; font-size: 11px;")
        # 按钮
        self._btn_open.setEnabled(bool(asset.image_path))
        # 时间戳
        if asset.image_updated:
            self._ts_lbl.setText(f"最近更新: {asset.image_updated}")
        else:
            self._ts_lbl.setText("")
        # 音频
        self._audio_lbl.setText(self._audio_status_text())
        self._btn_clear_audio.setVisible(bool(self._current_audio_path()))
        # 缩略图
        self._refresh_thumb()
        # v0.7.8:参考图(从 db 加载)
        self._ref_widget.set_refs(asset.ref_images)

    def refresh(self, asset: Asset) -> None:
        """任务完成后回调：用最新 asset 刷新。"""
        if self._asset and self._asset.id == asset.id:
            self.show_asset(asset)
        # else: 当前显示的不是这个 asset → 不动（外层会处理）

    # v0.7.8:参考图存盘回调（RefImagesWidget on_change）
    def _on_refs_changed(self, refs: List[str]) -> None:
        """参考图增删/排序后立即存 db。

        跟 v0.7.7 重打 8 的 prompt 编辑"无 800ms 定时器、改完立即存"一致:
        user 操作完 keystroke / 点 + / 点 ✕ 立刻写库,不延迟。
        """
        if not self._asset:
            return
        try:
            self._db.set_asset_ref_images(self._asset.id, refs)
            self._asset.ref_images = list(refs)
        except Exception:
            log.exception("v0.7.8:写参考图到 db 失败")

    def _kind_color(self, kind: str) -> str:
        return {
            "character": "color: #4A9EFF;",  # 蓝
            "scene": "color: #4ADE80;",       # 绿
            "prop": "color: #FF8C42;",        # 橙
        }.get(kind, "color: #B5B5B5;")

    def _status_text(self) -> str:
        if not self._asset:
            return ""
        s = self._asset.image_status
        if s == "ready":
            return "✓ 已生成"
        if s == "generating":
            return "⏳ 生成中"
        if s == "failed":
            return "✗ 失败"
        return "○ 未生成"

    def _status_color(self) -> str:
        if not self._asset:
            return ""
        s = self._asset.image_status
        if s == "ready":
            return "color: #4ADE80;"
        if s == "generating":
            return "color: #4A9EFF;"
        if s == "failed":
            return "color: #FF6B6B;"
        return "color: #B5B5B5;"

    def _refresh_thumb(self) -> None:
        if not self._asset:
            return
        path = self._asset.image_path
        if path and Path(path).exists():
            # v0.7.8.49:用 classmethod 缓存的 thumb 替代原同步重采样
            scaled = self._get_thumb_cached(path, 494, 373)
            if scaled is not None and not scaled.isNull():
                self._thumb.setPixmap(scaled)
                return
        self._thumb.setText("(未生成)" if not path else "(文件丢失)")
        self._thumb.setPixmap(QPixmap())

    def _on_thumb_clicked(self, _ev) -> None:  # noqa: ANN001
        """v0.7.7：缩略图点击 → 全屏 lightbox 预览（复刻 index.html:2123-2132 previewImage）。"""
        if not self._asset or not self._asset.image_path:
            return
        p = Path(self._asset.image_path)
        if not p.exists():
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(self, "提示", f"图片文件已丢失: {p}")
            return
        from ui.image_preview_dialog import ImagePreviewDialog
        dlg = ImagePreviewDialog(str(p), parent=self)
        dlg.exec()

    # ---------- v0.6.26 行内 prompt 编辑 ----------
    @Slot()
    def _on_prompt_changed(self) -> None:
        # v0.7.7 重打 8（user 大骂版）：删 800ms 自动保存定时器。
        # user 原话："改个prompt还要保存800秒？...保存了你提示已保存就行了呗"
        # 改完 keystroke 立即同步写 db + 立即显示"✓ 已保存"。
        if not self._asset:
            return
        cur = self._prompt_edit.toPlainText()
        if cur == self._prompt_initial:
            if self._prompt_dirty:
                self._prompt_dirty = False
                self._prompt_save_lbl.setText(
                    "✓ 已保存" if cur else "○ 留空"
                )
                self._prompt_save_lbl.setStyleSheet("color: #888; font-size: 11px;")
            return
        # 立即写库 + 立即显已保存
        try:
            self._db.update_asset_prompt(self._asset.id, cur)
            self._prompt_initial = cur
            self._prompt_dirty = False
            self._prompt_save_lbl.setText("✓ 已保存")
            self._prompt_save_lbl.setStyleSheet("color: #4ADE80; font-size: 11px;")
            # v1.1.5【B7 修复】:写库后必须更新 self._asset.image_prompt + 通知
            # listw 的 UserRole(同 listw item 内存里的对象)。
            # 之前只写库不更新内存 → 切到别的资产再切回来,show_asset 读
            # self._asset.image_prompt(还是旧值)→ 提示词被旧值覆盖回滚。
            # 修法:in-place 更新 dataclass 字段 + 从 db 拉 fresh asset 重置
            # 内存引用 + 通知 listw item 更新 UserRole,下次切回来拿到新值。
            self._asset = self._db.get_asset(self._asset.id) or self._asset
            try:
                self._asset.image_prompt = cur
            except Exception:
                # dataclass frozen 等极少数情况降级:重新赋值
                pass
            if hasattr(self, "listw") and self.listw is not None:
                from PySide6.QtCore import Qt
                for i in range(self.listw.count()):
                    item = self.listw.item(i)
                    if item and item.data(Qt.ItemDataRole.UserRole) is self._asset:
                        item.setData(Qt.ItemDataRole.UserRole, self._asset)
                        break
        except Exception:  # noqa: BLE001
            log.exception("update_asset_prompt failed")
            self._prompt_save_lbl.setText("✗ 保存失败，看 logs/manju.log")
            self._prompt_save_lbl.setStyleSheet("color: #FF6B6B; font-size: 11px;")

    @Slot()
    def _on_prompt_save_due(self) -> None:  # noqa: N802
        # v0.7.7 重打 8：保留方法以兼容旧信号连接，实际 _on_prompt_changed
        # 改成同步立即写库了，timer 删了。
        return

    # ---------- v0.6.20 音频 ----------
    def _current_audio_path(self) -> str:
        if not self._asset:
            return ""
        try:
            return self._db.get_audio_selection(self._project.id, self._asset.name) or ""
        except Exception:
            return ""

    def _audio_status_text(self) -> str:
        ap = self._current_audio_path()
        if not ap:
            return "<i>🔇 尚未选音频</i>"
        p = Path(ap)
        return f"🔊 当前音频: <b>{p.name}</b>"

    @Slot()
    def _on_click_audio(self) -> None:
        if not self._asset:
            return
        from core.audio import safe_copy_audio
        cfg = self._parent_config_or_none()
        if cfg is None:
            QMessageBox.warning(self, "提示", "找不到 config")
            return
        from core.generators import _safe_filename
        proj_dir = Path(cfg.outputs_dir) / _safe_filename(self._project.name)
        assets_root = proj_dir / "assets"
        assets_root.mkdir(parents=True, exist_ok=True)
        start_dir = str(assets_root) if assets_root.exists() else ""
        path_str, _ = QFileDialog.getOpenFileName(
            self, "选择音频文件", start_dir,
            "音频 (*.mp3 *.wav *.ogg *.m4a *.aac *.flac)",
        )
        if not path_str:
            return
        src = Path(path_str)
        if not src.exists():
            QMessageBox.warning(self, "提示", f"文件不存在: {src}")
            return
        safe_asset = _safe_filename(self._asset.name) or f"asset_{self._asset.id}"
        target_dir = assets_root / safe_asset
        target = target_dir / src.name
        try:
            safe_copy_audio(src, target)
        except OSError as e:
            log.exception("copy audio failed")
            QMessageBox.critical(self, "错误", f"复制失败: {e}")
            return
        try:
            self._db.set_audio_selection(self._project.id, self._asset.name, str(target))
        except Exception as e:  # noqa: BLE001
            log.exception("set_audio_selection failed")
            QMessageBox.critical(self, "错误", f"写入 db 失败: {e}")
            return
        self.show_asset(self._asset)
        QMessageBox.information(self, "提示", f"✓ 已选音频: {target.name}")

    @Slot()
    def _on_click_clear_audio(self) -> None:
        if not self._asset:
            return
        try:
            self._db.clear_audio_selection(self._project.id, self._asset.name)
        except Exception as e:  # noqa: BLE001
            log.exception("clear_audio_selection failed")
            QMessageBox.critical(self, "错误", f"清音频失败: {e}")
            return
        self.show_asset(self._asset)

    @Slot()
    def _on_click_image(self) -> None:
        if not self._asset or not self._asset.description:
            QMessageBox.warning(self, "提示", "该资产没有描述，请先提取项目资产。")
            return
        task = AssetImageTask(
            asset=self._asset,
            project=self._project,
            config=self._parent_config(),
            parent=self,
            db=self._db,  # v0.7.7：传 db 让 task 拉最新 asset（user 改的 prompt 不被覆盖）
        )
        self._on_enqueue(task)

    @Slot()
    def _on_click_open(self) -> None:
        if not self._asset or not self._asset.image_path:
            return
        path = Path(self._asset.image_path)
        if not path.exists():
            QMessageBox.information(self, "提示", "图片文件已丢失")
            return
        self._on_open_outputs(path)

    @Slot()
    def _on_click_browse(self) -> None:
        if not self._asset:
            return
        cfg = self._parent_config_or_none()
        if cfg is None:
            QMessageBox.warning(self, "提示", "找不到 config")
            return
        from ui.asset_browser_dialog import AssetBrowserDialog
        dlg = AssetBrowserDialog(
            project=self._project,
            asset=self._asset,
            db=self._db,
            outputs_dir=Path(cfg.outputs_dir),
            parent=self,
        )
        dlg.exec()
        assets = self._db.list_assets(self._project.id)
        new_asset = next((a for a in assets if a.name == self._asset.name), None)
        if new_asset is not None:
            self.show_asset(new_asset)

    @Slot()
    def _on_click_upload(self) -> None:
        try:
            self._do_upload()
        except Exception as e:  # noqa: BLE001
            import logging as _log
            _log.getLogger("manju").exception("upload 异常: %s", e)
            try:
                QMessageBox.critical(self, "错误", f"上传失败: {e}")
            except Exception:
                pass

    def _do_upload(self) -> None:
        import logging as _log
        _log.getLogger("manju").warning("upload click: asset=%r", self._asset.name if self._asset else None)
        if not self._asset:
            return
        # v0.7.8：上传图用 Config.get() 单例取 config，不用 _parent_config_or_none
        # （AssetPanel.parent() 是 None，链断了拿不到 config，会 raise）
        cfg = self._parent_config()
        _log.getLogger("manju").warning("upload: got cfg=%r", type(cfg).__name__ if cfg else None)
        start_dir = ""
        if cfg is not None and getattr(cfg, "outputs_dir", None):
            from core.generators import _safe_filename
            proj_dir = Path(cfg.outputs_dir) / _safe_filename(self._project.name) / "assets"
            if proj_dir.exists():
                start_dir = str(proj_dir)
        # v0.7.8：QFileDialog 和 tkinter 都在 PyInstaller 打包下不行
        # （QFileDialog 卡死不返回，tkinter Tk() 卡死），改用 Win32 原生
        # comdlg32.GetOpenFileNameW。完全不依赖任何 GUI 框架,Windows 系统级 native。
        _log.getLogger("manju").warning("upload: start_dir=%r", start_dir)
        path_str = _win32_open_file_dialog(start_dir)
        _log.getLogger("manju").warning("upload: win32 returned path_str=%r", path_str)
        if not path_str:
            return
        src = Path(path_str)
        if not src.exists():
            QMessageBox.warning(self, "提示", f"文件不存在: {src}")
            return
        try:
            target = self._copy_uploaded_image(src)
        except Exception as e:  # noqa: BLE001
            log.exception("upload asset image failed")
            QMessageBox.critical(self, "错误", f"上传失败: {e}")
            return
        try:
            # v0.7.7 重打 20：update_asset_image 移除了 image_prompt 参数，
            # 不再传 "(用户上传)" marker（违规用 image_prompt 字段当图片来源）。
            self._db.update_asset_image(
                self._asset.id,
                image_path=str(target),
                image_status="ready",
            )
        except Exception as e:  # noqa: BLE001
            log.exception("db update failed")
            QMessageBox.critical(self, "错误", f"写入 db 失败: {e}")
            return
        fresh = self._db.get_asset(self._asset.id)
        if fresh:
            self.show_asset(fresh)
        QMessageBox.information(self, "提示", f"✓ 已上传: {target.name}")

    def _copy_uploaded_image(self, src: Path) -> Path:
        # v0.7.7：保存路径对齐老 software server.py:1689-1696：
        # `outputs/<safe_proj>/assets/<safe_asset>/<prefix>_<safe_name>_<ts>.<ext>`
        # — 跟 _run_one_asset_image 一致，每个资产一个子文件夹。
        # 之前 manju 写扁平 `proj_dir/{kind}_{name}.png`，浏览历史找不到。
        from datetime import datetime as _dt_img
        from core.asset_browser import safe_asset_dir_name
        from core.generators import _safe_filename
        # v0.7.8：用 Config.get() 单例，不用 _parent_config_or_none
        # （AssetPanel 没设 parent，走链拿到 None，会 raise）
        cfg = self._parent_config()
        if cfg is None:
            raise RuntimeError("找不到 config")
        safe_proj = _safe_filename(self._project.name) or "default"
        asset_dir = (
            Path(cfg.outputs_dir)
            / safe_proj
            / "assets"
            / safe_asset_dir_name(self._asset.name)
        )
        asset_dir.mkdir(parents=True, exist_ok=True)
        safe_name = _safe_filename(self._asset.name) or f"asset_{self._asset.id}"
        ext = src.suffix.lower() or ".png"
        ts = _dt_img.now().strftime("%Y%m%d_%H%M%S")
        target = asset_dir / f"{self._asset.kind}_{safe_name}_{ts}{ext}"
        import shutil
        shutil.copy2(src, target)
        return target

    def _parent_config(self):
        # v0.7.7 bug fix：直接返回 main_window 启动时缓存的 config 对象的话，
        # 设置面板「保存」后调 Config.reload() 只替换 Config._instance 单例，
        # **不会**更新 main_window 上 self.config 这个旧引用 → 所有 task 用的还是
        # 旧 config（image_model 等字段还是默认值）。改成直接拿最新单例。
        from core.config import Config
        return Config.get()

    def _parent_config_or_none(self):
        w = self.parent()
        while w is not None:
            if hasattr(w, "config"):
                return w.config
            w = w.parent()
        return None


# ========================================================================
# 列表项代理（自定义 item 渲染）
# ========================================================================

class AssetListItemDelegate(QStyledItemDelegate):
    """资产列表项渲染：图标 + 资产名（粗体） + 状态。

    v0.7.0：master-detail 的左侧列表项样式。
    v0.7.8.49:加 _pixmap_cache 避免每次 paint 都重读 48x48 pixmap。
    50 个资产 × 每次 paint 重读 = 50×QPixmap load + 50×SmoothTransform
    (50-200ms/次)。QListWidget 的 paint 触发频率很高(滚轮 hover 选中都触发),
    必须缓存。cache key = (image_path, mtime),图片文件被新生成时自动失效。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        # v0.7.8.49:pixmap 缓存 {(path, mtime, size): QPixmap}
        self._pixmap_cache: dict = {}

    def sizeHint(self, option, index) -> QSize:
        return QSize(220, 56)  # 宽自适应，高 56

    def _get_cached_pixmap(self, path: str, w: int, h: int):
        """v0.7.8.49:带 mtime 校验的 pixmap 缓存。"""
        try:
            mt = Path(path).stat().st_mtime
        except OSError:
            mt = 0
        key = (path, mt, w, h)
        cached = self._pixmap_cache.get(key)
        if cached is not None:
            return cached
        if len(self._pixmap_cache) > 200:  # 防止无限增长
            self._pixmap_cache.clear()
        pix = QPixmap(path)
        if pix.isNull():
            return None
        pix = pix.scaled(
            w, h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._pixmap_cache[key] = pix
        return pix

    def paint(self, painter, option, index) -> None:
        asset: Asset = index.data(Qt.ItemDataRole.UserRole)
        if asset is None:
            return super().paint(painter, option, index)

        painter.save()

        # 背景（选中态用主题强调色，未选中用透明走 QSS 默认）
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, Qt.GlobalColor.transparent)  # 让 QSS 处理
        else:
            painter.fillRect(option.rect, Qt.GlobalColor.transparent)

        rect = option.rect.adjusted(4, 4, -4, -4)

        # 左侧缩略图（48x48 圆角）
        thumb_rect = rect.adjusted(0, 0, 0, 0)
        thumb_rect.setWidth(48)
        thumb_rect.setHeight(48)
        if asset.image_path and Path(asset.image_path).exists():
            pix = self._get_cached_pixmap(asset.image_path, 48, 48)
            if pix is not None and not pix.isNull():
                painter.drawPixmap(thumb_rect, pix)
            else:
                self._draw_thumb_placeholder(painter, thumb_rect)
        else:
            self._draw_thumb_placeholder(painter, thumb_rect)

        # 右侧：资产名（粗体） + 状态（小字）
        text_rect = rect.adjusted(56, 4, 0, 0)
        from PySide6.QtGui import QFont, QColor
        name_font = QFont(option.font)
        name_font.setBold(True)
        name_font.setPointSize(11)
        painter.setFont(name_font)
        painter.setPen(QColor("#FFFFFF"))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextSingleLine, asset.name)

        # 状态
        status = self._status_text(asset)
        status_color = QColor(self._status_color(asset))
        small_font = QFont(option.font)
        small_font.setPointSize(9)
        small_font.setBold(False)
        painter.setFont(small_font)
        painter.setPen(status_color)
        status_rect = text_rect.adjusted(0, 22, 0, 0)
        painter.drawText(status_rect, Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextSingleLine, status)

        painter.restore()

    def _draw_thumb_placeholder(self, painter, rect) -> None:
        from PySide6.QtGui import QColor, QBrush
        painter.fillRect(rect, QColor("#2A2A2A"))
        painter.setPen(QColor("#777"))
        f = painter.font()
        f.setPointSize(8)
        painter.setFont(f)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "无图")

    def _status_text(self, asset: Asset) -> str:
        s = asset.image_status
        if s == "ready":
            return f"✓ 已生成 · {asset.kind}"
        if s == "generating":
            return f"⏳ 生成中 · {asset.kind}"
        if s == "failed":
            return f"✗ 失败 · {asset.kind}"
        return f"○ 未生成 · {asset.kind}"

    def _status_color(self, asset: Asset) -> str:
        s = asset.image_status
        if s == "ready":
            return "#4ADE80"  # 绿（已生成）
        if s == "generating":
            return "#FF8C42"  # v0.7.0：橙（替换蓝）
        if s == "failed":
            return "#FF6B6B"  # 红
        return "#B5B5B5"


# ========================================================================
# 主面板
# ========================================================================

class AssetListWidget(QScrollArea):
    """资产清单的滚动容器。

    v0.7.0 改造（方案 C：master-detail）：
    - 顶部操作栏（不变）
    - 主体 3 段（人物/场景/物品）每段内：
      - QSplitter 水平分割（可拖动）
      - 左侧：QListWidget 紧凑列表
      - 右侧：单例 AssetPanel 详情（点列表项切换）
    - 16+ 资产时，列表可滚动，详情区固定空间

    复刻自原软件 D:\\剧本分镜助手\\templates\\index.html 的 assetView
    """

    SECTIONS: tuple = (
        ("character", "人物", "#4A9EFF"),  # 蓝
        ("scene", "场景", "#4ADE80"),       # 绿
        ("prop", "物品", "#FF8C42"),        # 橙
    )

    def __init__(
        self,
        project: Project,
        db: Database,
        on_enqueue: Callable,
        on_open_outputs: Callable[[Path], None],
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._project = project
        self._db = db
        self._on_enqueue = on_enqueue
        self._on_open_outputs = on_open_outputs
        # 每段：dict[kind] = {"box", "list": QListWidget, "panel": AssetPanel, "splitter": QSplitter, "empty": QLabel}
        self._section_data: dict = {}
        self._list_file: Optional[Path] = None
        self._list_text: str = ""
        self.setWidgetResizable(True)
        # v0.7.8.37f fix:作为 tab 页面时 QTabWidget 内部 QStackedWidget 默认
        # 不给子 widget Expanding,会算 QScrollArea.sizeHint(~256x192) 给 tab,
        # tab 高度被压成 ~200 → 看不到内容。强制 Expanding 让 QTabWidget
        # 把 splitter 给的高度透下来。
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        container = QWidget()
        self._lay = QVBoxLayout(container)
        self._lay.setContentsMargins(4, 4, 4, 4)
        self._lay.setSpacing(8)

        # ===== 顶部操作栏 =====
        top = QHBoxLayout()
        self._btn_extract = QPushButton("🔍 提取项目资产")
        self._btn_extract.setFixedHeight(32)
        self._btn_extract.clicked.connect(self._on_click_extract)
        top.addWidget(self._btn_extract)

        self._btn_reextract = QPushButton("♻️ 清空 + 重新提取")
        self._btn_reextract.setFixedHeight(32)
        self._btn_reextract.clicked.connect(self._on_click_reextract)
        top.addWidget(self._btn_reextract)

        self._btn_batch_image = QPushButton("🚀 一键全项目生图")
        self._btn_batch_image.setFixedHeight(32)
        self._btn_batch_image.setToolTip(
            "给本项目下所有资产（没图的）批量跑 dreamina 生图。\n"
            "已有图的会跳过（保持现状）。\n"
            "复刻自老软件 /convert-assets 接口。"
        )
        self._btn_batch_image.clicked.connect(self._on_click_batch_image)
        top.addWidget(self._btn_batch_image)

        self._btn_copy_list = QPushButton("📋 复制资产列表")
        self._btn_copy_list.setFixedHeight(32)
        self._btn_copy_list.setToolTip(
            "把「人物资产：xxx、xxx\n场景资产：xxx、xxx\n物品资产：xxx、xxx」"
            "复制到剪贴板，可粘贴到下游视频 prompt agent。"
        )
        self._btn_copy_list.clicked.connect(self._on_click_copy_list)
        self._btn_copy_list.setEnabled(False)
        top.addWidget(self._btn_copy_list)

        self._btn_view_full = QPushButton("📄 查看资产名清单")
        self._btn_view_full.setFixedHeight(32)
        self._btn_view_full.setToolTip("弹窗显示人/场/物三段名字列表（和做提示词时灌给 agent 的【项目资产】表完全一致）")
        self._btn_view_full.clicked.connect(self._on_click_view_full)
        self._btn_view_full.setEnabled(False)
        top.addWidget(self._btn_view_full)

        self._summary_lbl = QLabel("（无资产）")
        self._summary_lbl.setStyleSheet("color: #B5B5B5;")
        top.addWidget(self._summary_lbl, 1)

        wrap = QWidget()
        wrap_lay = QHBoxLayout(wrap)
        wrap_lay.setContentsMargins(0, 0, 0, 0)
        wrap_lay.addLayout(top)
        self._lay.addWidget(wrap)

        # ===== 3 段（人物/场景/物品）=====
        for kind, label, color in self.SECTIONS:
            box = QGroupBox()
            box.setStyleSheet(
                f"QGroupBox {{ border: 1px solid #4A4A4A; border-radius: 4px;"
                f" margin-top: 14px; padding-top: 8px; background: #353535; }}"
                f"QGroupBox::title {{ subcontrol-origin: margin;"
                f" subcontrol-position: top left; padding: 0 6px;"
                f" color: {color}; font-weight: bold; }}"
            )

            # 段内：QSplitter(列表, 详情) + empty 占位
            splitter = QSplitter(Qt.Orientation.Horizontal)
            splitter.setChildrenCollapsible(False)
            splitter.setHandleWidth(2)
            # 左侧：列表
            listw = QListWidget()
            listw.setObjectName(f"assetList_{kind}")
            listw.setItemDelegate(AssetListItemDelegate(listw))
            listw.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            listw.setMinimumWidth(220)
            listw.setMaximumWidth(360)
            listw.itemSelectionChanged.connect(
                lambda k=kind: self._on_section_selection_changed(k)
            )
            # 右侧：详情（单例，3 段共用？不行，每段独立，selected 切换）
            panel = AssetPanel(
                project=self._project,
                db=self._db,
                on_enqueue=self._on_enqueue,
                on_open_outputs=self._on_open_outputs,
            )

            splitter.addWidget(listw)
            splitter.addWidget(panel)
            splitter.setStretchFactor(0, 0)
            splitter.setStretchFactor(1, 1)
            splitter.setSizes([240, 700])
            splitter.setStyleSheet(
                "QSplitter::handle { background: #4A4A4A; }"
                "QSplitter::handle:hover { background: #FF8C42; }"
            )

            # empty 占位（无资产时显示，覆盖 splitter）
            empty_lbl = QLabel(f"<i>暂无{label}资产</i>")
            empty_lbl.setStyleSheet("color: #B5B5B5; padding: 16px;")
            empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty_lbl.setVisible(False)

            box_lay = QVBoxLayout(box)
            box_lay.setContentsMargins(8, 8, 8, 8)
            box_lay.setSpacing(6)
            box_lay.addWidget(splitter)
            box_lay.addWidget(empty_lbl)

            self._lay.addWidget(box)
            self._section_data[kind] = {
                "box": box,
                "splitter": splitter,
                "list": listw,
                "panel": panel,
                "empty": empty_lbl,
                "label": label,
                "color": color,
            }

        self.setWidget(container)
        self.refresh()

    # ---------- 刷新 ----------

    def refresh(self) -> None:
        assets = self._db.list_assets(self._project.id)

        if not assets:
            self._summary_lbl.setText("（无资产 — 点【提取项目资产】开始）")
            self._btn_copy_list.setEnabled(False)
            self._btn_view_full.setEnabled(False)
            for kind, _label, _color in self.SECTIONS:
                self._set_section_empty(kind, True, f"暂无{_label}资产")
            return

        # 按 kind 分组
        by_kind: dict = {k: [] for k, _, _ in self.SECTIONS}
        for a in assets:
            by_kind.get(a.kind, []).append(a)

        n_kind = {k: 0 for k in ASSET_KIND_LABELS.keys()}
        for a in assets:
            n_kind[a.kind] = n_kind.get(a.kind, 0) + 1

        # 更新每段
        for kind, label, color in self.SECTIONS:
            section_assets = by_kind.get(kind, [])
            sd = self._section_data[kind]
            box = sd["box"]
            listw: QListWidget = sd["list"]
            panel: AssetPanel = sd["panel"]
            empty_lbl: QLabel = sd["empty"]

            box.setTitle(f"  {label}资产  ({len(section_assets)})  ")

            if not section_assets:
                self._set_section_empty(kind, True, f"暂无{label}资产")
                # 清空列表
                listw.clear()
                panel.setVisible(False)
                continue

            # 填充列表
            listw.blockSignals(True)
            listw.clear()
            section_assets.sort(key=lambda a: a.name)
            for a in section_assets:
                item = QListWidgetItem()
                item.setData(Qt.ItemDataRole.UserRole, a)
                listw.addItem(item)
            # 默认选中第一个
            if listw.count() > 0:
                listw.setCurrentRow(0)
            listw.blockSignals(False)
            empty_lbl.setVisible(False)
            sd["splitter"].setVisible(True)

            # v0.7.8.49:把"触发第一项 show_asset(加载 494x373 pixmap)"
            # 推到下个 event loop tick,refresh() 立刻返回,UI 不卡。
            # 资产图加载是纯本地 I/O + SmoothTransformation 重采样,主线程
            # 会卡 50-200ms (1-3 张图)。用 QTimer.singleShot 推到 idle 跑。
            QTimer.singleShot(0, lambda k=kind: self._on_section_selection_changed(k))

        # 摘要
        self._summary_lbl.setText(
            f"共 {len(assets)} 个资产  "
            f"人物 {n_kind.get('character',0)} · "
            f"场景 {n_kind.get('scene',0)} · "
            f"物品 {n_kind.get('prop',0)}"
        )

        self._refresh_list_text_from_cache()
        self._btn_copy_list.setEnabled(bool(self._list_text))
        self._btn_view_full.setEnabled(bool(assets))

    def _set_section_empty(self, kind: str, empty: bool, msg: str = "") -> None:
        sd = self._section_data.get(kind)
        if sd is None:
            return
        sd["empty"].setText(f"<i>{msg}</i>" if msg else "<i>暂无</i>")
        sd["empty"].setVisible(empty)
        sd["splitter"].setVisible(not empty)

    def _on_section_selection_changed(self, kind: str) -> None:
        """v0.7.0：左侧列表选中变化时，更新右侧详情。"""
        sd = self._section_data.get(kind)
        if sd is None:
            return
        listw: QListWidget = sd["list"]
        panel: AssetPanel = sd["panel"]
        item = listw.currentItem()
        if item is None:
            panel.setVisible(False)
            return
        asset: Asset = item.data(Qt.ItemDataRole.UserRole)
        if asset is None:
            panel.setVisible(False)
            return
        panel.show_asset(asset)

    def _refresh_list_text_from_cache(self) -> None:
        if self._list_text:
            return
        from core.asset_parser import list_file_path, _SECTION_KIND
        cfg = self._parent_config_or_none()
        if cfg is not None and getattr(cfg, "outputs_dir", None):
            lf = list_file_path(cfg.outputs_dir, self._project.id)
            if lf.exists():
                try:
                    self._list_text = lf.read_text(encoding="utf-8")
                    self._list_file = lf
                    return
                except OSError:
                    pass
        d = {title: [] for title in _SECTION_KIND}
        section_map = {kind: title for title, kind in _SECTION_KIND.items()}
        for a in self._db.list_assets(self._project.id):
            k = section_map.get(a.kind)
            if k:
                d[k].append(a.name)
        lines = []
        for section_key, _kind in _SECTION_KIND.items():
            items = d.get(section_key) or []
            if items:
                lines.append(f"{section_key}：{'、'.join(items)}")
        self._list_text = "\n".join(lines)

    def _parent_config_or_none(self):
        w = self.parent()
        while w is not None:
            if hasattr(w, "config"):
                return w.config
            w = w.parent()
        return None

    def _parent_config(self):
        # v0.7.7 bug fix：直接返回 main_window 启动时缓存的 config 对象的话，
        # 设置面板「保存」后调 Config.reload() 只替换 Config._instance 单例，
        # **不会**更新 main_window 上 self.config 这个旧引用 → 所有 task 用的还是
        # 旧 config（image_model 等字段还是默认值）。改成直接拿最新单例。
        from core.config import Config
        return Config.get()

    # ---------- 任务完成回调 ----------

    def set_asset_list(self, text: str, file: Optional[Path] = None) -> None:
        self._list_text = text or ""
        self._list_file = file
        self._btn_copy_list.setEnabled(bool(self._list_text))
        self._btn_view_full.setEnabled(True)

    def update_asset(self, asset: Asset) -> None:
        """任务完成后回调：刷新对应行 + 详情。"""
        # 找哪段有它
        for kind, _label, _color in self.SECTIONS:
            sd = self._section_data.get(kind)
            if sd is None:
                continue
            listw: QListWidget = sd["list"]
            panel: AssetPanel = sd["panel"]
            for i in range(listw.count()):
                item = listw.item(i)
                a: Asset = item.data(Qt.ItemDataRole.UserRole)
                if a and a.id == asset.id:
                    item.setData(Qt.ItemDataRole.UserRole, asset)
                    # 如果当前选中的是它，刷新详情
                    if listw.currentItem() is item:
                        panel.show_asset(asset)
                    else:
                        # 触发重绘（delegate 读 UserRole）
                        listw.viewport().update()
                    return
        # 没找到 → 全量 refresh
        self.refresh()

    # ---------- 按钮回调 ----------

    @Slot()
    def _on_click_extract(self) -> None:
        log.info("_on_click_extract: 触发，project_id=%s", self._project.id if self._project else None)
        if self._project is None:
            log.warning("_on_click_extract: 无当前项目")
            return
        eps = self._db.list_episodes(self._project.id)
        if not eps:
            log.warning("_on_click_extract: 项目无剧集，project_id=%s", self._project.id)
            QMessageBox.warning(self, "提示", "项目下没有剧集，无法提取资产。")
            return
        try:
            cfg = self._parent_config()
            task = AssetExtractTask(
                project=self._project,
                episodes=eps,
                config=cfg,
                parent=self,
            )
        except Exception:  # noqa: BLE001
            log.exception("_on_click_extract: AssetExtractTask 构造失败")
            QMessageBox.critical(self, "错误", "构造资产抽取任务失败，看 logs/manju.log。")
            return
        log.info("_on_click_extract: 构造完成，name=%s", task.name)
        if self._on_enqueue is None:
            log.error("_on_click_extract: _on_enqueue 没绑（按钮回调缺失）")
            QMessageBox.critical(self, "错误", "内部错误：按钮回调未绑定。")
            return
        try:
            self._on_enqueue(task)
            log.info("_on_click_extract: 已交给 _on_enqueue")
        except Exception:  # noqa: BLE001
            log.exception("_on_click_extract: _on_enqueue 抛了")

    @Slot()
    def _on_click_reextract(self) -> None:
        ret = QMessageBox.question(
            self, "确认",
            "将删除本项目所有资产记录（包括已生成的图片路径），然后重新跑 AI 提取。\n确定继续？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._db.delete_assets(self._project.id)
        self._list_text = ""
        self._list_file = None
        self._btn_copy_list.setEnabled(False)
        self._on_click_extract()

    @Slot()
    def _on_click_batch_image(self) -> None:
        if self._project is None:
            return
        ret = QMessageBox.question(
            self, "批量生图",
            "将给本项目下所有资产批量跑 dreamina 生图。\n\n"
            "• 选「Yes」= 跳过已有图（推荐）\n"
            "• 选「No」= 全部覆盖（强制重跑）\n\n"
            "（单个失败不中断其他资产）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Yes,
        )
        if ret == QMessageBox.StandardButton.Cancel:
            return
        skip_existing = (ret == QMessageBox.StandardButton.Yes)
        try:
            cfg = self._parent_config()
        except Exception as e:  # noqa: BLE001
            log.exception("batch image: 找不到 config")
            QMessageBox.critical(self, "错误", f"找不到 config: {e}")
            return
        try:
            task = BatchAssetImageTask(
                project=self._project,
                db=self._db,
                config=cfg,
                parent=self,
                skip_existing=skip_existing,
            )
        except Exception:  # noqa: BLE001
            log.exception("batch image: 构造任务失败")
            QMessageBox.critical(self, "错误", "构造批量生图任务失败，看 logs/manju.log。")
            return
        if self._on_enqueue is None:
            QMessageBox.critical(self, "错误", "内部错误：按钮回调未绑定。")
            return
        try:
            self._on_enqueue(task)
            log.info(
                "_on_click_batch_image: 已入队 (project=%s, skip_existing=%s)",
                self._project.id, skip_existing,
            )
        except Exception:  # noqa: BLE001
            log.exception("batch image: _on_enqueue 抛了")
            QMessageBox.critical(self, "错误", "提交任务失败，看 logs/manju.log。")

    @Slot()
    def _on_click_copy_list(self) -> None:
        if not self._list_text:
            QMessageBox.information(self, "提示", "资产列表为空。先点【提取项目资产】。")
            return
        QGuiApplication.clipboard().setText(self._list_text)
        n_lines = self._list_text.count("\n") + 1
        n_total = sum(
            self._list_text.count("、") + 1
            for line in self._list_text.split("\n")
            if "：" in line
        )
        log.info("资产列表已复制到剪贴板（%d 段，共 %d 个资产）", n_lines, n_total)
        original = self._btn_copy_list.text()
        self._btn_copy_list.setText("✓ 已复制")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, lambda: self._btn_copy_list.setText(original))

    @Slot()
    def _on_click_view_full(self) -> None:
        # v0.7.8.24：弹窗显示的是"人/场/物三段纯名字列表"（就是
        # `format_asset_list_text()` 那种格式），不再是 hermes 原始 markdown。
        # 1) 这个名字表同时就是做提示词时灌给 seedance agent 的 `asset_names`
        #    （见 core/prompts.py:build_seedance_prompt），用户在弹窗里能直接
        #    看到 agent 会收到什么
        # 2) `_list_text` 优先来自 `set_asset_list()`（任务成功落盘）；
        #    没设过就 `_refresh_list_text_from_cache()` 从 db.assets.name 拼
        #    （db 有数据 + hermes 任务失败 / 文件丢了的兜底）—— **不**动
        #    agent / hermes 代码
        # 3) db 也没资产 → 提示先做资产抽取
        if not self._list_text:
            self._refresh_list_text_from_cache()
        if not self._list_text:
            QMessageBox.information(
                self, "提示",
                "项目下还没有资产。请先点【提取项目资产】。",
            )
            return
        content = self._list_text
        dlg = QDialog(self)
        dlg.setWindowTitle(f"资产名字清单 - {self._project.name}")
        dlg.resize(640, 480)
        lay = QVBoxLayout(dlg)
        info_lbl = QLabel(
            f"这就是生成提示词时灌给 agent 的【项目资产】列表    长度: {len(content)} 字符"
        )
        info_lbl.setStyleSheet("color: #B5B5B5;")
        lay.addWidget(info_lbl)
        text = QPlainTextEdit()
        text.setPlainText(content)
        text.setReadOnly(True)
        font = text.font()
        font.setFamily("Consolas, Menlo, monospace")
        text.setFont(font)
        lay.addWidget(text, 1)
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        copy_btn = btns.addButton("📋 复制全文", QDialogButtonBox.ButtonRole.ActionRole)
        copy_btn.clicked.connect(lambda: QGuiApplication.clipboard().setText(content))
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        dlg.exec()
