"""对话框：新建/编辑 项目 / 剧集。

v0.6.18 改造：
- NewProjectDialog 加 style_id / render_type 下拉（v0.6.17 注入 prompt 依赖这俩字段）
- NewEpisodeDialog 加 render_type 下拉

v0.6.28 改造：
- 渲染类型统一走项目级。NewEpisodeDialog 不再让用户选 render_type，
  所有需要渲染类型的地方直接读 project.render_type。

v0.6.29 改造：
- NewEpisodeDialog 加 [📁 导入文件] 按钮，支持多选 .txt/.md/.docx，
  内容追加到现有剧本后面（用户可继续手动改/再追加）。

style 列表来自 core.prompts.STYLES（16 个，复刻自原软件 server.py:185-202）
render 列表来自 core.prompts.RENDER_TYPES（48 个，复刻自原软件 server.py:204-257）
"""
import os
from PySide6.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QTextEdit, QDialogButtonBox,
    QVBoxLayout, QSpinBox, QComboBox, QLabel, QHBoxLayout, QPushButton,
    QFileDialog, QMessageBox,
)


def _read_script_file(path: str) -> str:
    """v0.6.29：读剧本文件内容。支持 .txt / .md / .docx。

    - .txt / .md：按 utf-8 读（带 BOM 也兼容），失败回退 gbk
    - .docx：python-docx 抽所有 paragraph.text，空段也保留（保留段落分隔）
    - 其它后缀：抛 ValueError

    Returns:
        文本内容（去掉首尾空白）。

    Raises:
        FileNotFoundError: 文件不存在
        PermissionError: 没权限读
        ValueError: 不支持的文件类型
        Exception: 其它读取错误
    """
    ext = os.path.splitext(path)[1].lower()
    if ext in (".txt", ".md"):
        # utf-8-sig 自动去 BOM；失败回退 gbk（Windows 常见）
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                return f.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="gbk") as f:
                return f.read()
    if ext == ".docx":
        try:
            from docx import Document
        except ImportError as e:
            raise RuntimeError(
                "读 .docx 需要 python-docx: pip install python-docx"
            ) from e
        try:
            doc = Document(path)
        except Exception as e:
            # python-docx 文件不存在 / 不是真 docx 都抛 PackageNotFoundError，
            # 转成 FileNotFoundError / ValueError 让上层统一处理
            cls_name = type(e).__name__
            if "PackageNotFound" in cls_name or "not found" in str(e).lower():
                raise FileNotFoundError(f"无法打开 docx 文件: {path}") from e
            raise ValueError(f"不是有效的 .docx 文件: {path} ({cls_name})") from e
        # 段间用换行隔开（保留段落结构）
        return "\n".join(p.text for p in doc.paragraphs)
    raise ValueError(f"不支持的文件类型: {ext}（仅支持 .txt / .md / .docx）")


def _build_style_combo(default_style_id=None) -> QComboBox:
    """v0.6.18：构造 STYLES 下拉。格式：「经典电影 Classic Cinematic」。

    默认第一项是 "（不指定）"（对应 value=""），后续是 STYLES 的 (name + en)。
    """
    from core.prompts import STYLES
    combo = QComboBox()
    combo.setMinimumWidth(280)
    combo.addItem("（不指定 — 用全局默认）", "")
    for sid, info in STYLES.items():
        label = f"{info['name']} {info['en']}"
        combo.addItem(label, sid)
    # 选默认值
    if default_style_id and default_style_id in STYLES:
        idx = combo.findData(default_style_id)
        if idx >= 0:
            combo.setCurrentIndex(idx)
    return combo


def _build_render_combo(default_render_type=None) -> QComboBox:
    """v0.6.18：构造 RENDER_TYPES 下拉（按 category 分组）。"""
    from core.prompts import RENDER_TYPES
    combo = QComboBox()
    combo.setMinimumWidth(280)
    combo.addItem("（不指定 — 用全局默认）", "")
    # 按 category 分组（参考原软件 server.py 的分类）
    by_cat: dict = {}
    for rid, info in RENDER_TYPES.items():
        cat = info.get("category", "其他")
        by_cat.setdefault(cat, []).append((rid, info))
    for cat in sorted(by_cat.keys()):
        # 第一个分组项做 separator
        combo.addItem(f"── {cat} ──", "")
        combo.model().item(combo.count() - 1).setEnabled(False)
        for rid, info in by_cat[cat]:
            label = f"{info['name']} ({rid})"
            combo.addItem(label, rid)
    if default_render_type and default_render_type in RENDER_TYPES:
        idx = combo.findData(default_render_type)
        if idx >= 0:
            combo.setCurrentIndex(idx)
    return combo


class NewProjectDialog(QDialog):
    """v0.6.18：加 style_id / render_type 字段（v0.6.17 prompt 注入依赖）。"""

    def __init__(
        self,
        parent=None,
        default_name: str = "",
        default_desc: str = "",
        default_style_id: str = "",
        default_render_type: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle("项目")
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.name_edit = QLineEdit(default_name)
        self.name_edit.setPlaceholderText("例：修仙界禁止搞军火")
        self.desc_edit = QTextEdit(default_desc)
        self.desc_edit.setPlaceholderText("项目简介（可空）")
        self.desc_edit.setFixedHeight(70)
        form.addRow("项目名 *", self.name_edit)
        form.addRow("简介", self.desc_edit)
        # v0.6.18：style / render 切换（与原软件 PATCH /api/projects/<id> 对齐）
        self.style_combo = _build_style_combo(default_style_id)
        self.render_combo = _build_render_combo(default_render_type)
        # 提示标签
        style_hint = QLabel(
            "影响：分镜 / 资产生图 / 视频 prompt 的视觉风格注入"
        )
        style_hint.setStyleSheet("color: #888; font-size: 11px;")
        render_hint = QLabel(
            "影响：3D/2D/真人/定格 等渲染类型（核心生图参数）"
        )
        render_hint.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("视觉风格", self.style_combo)
        form.addRow("", style_hint)
        form.addRow("渲染类型", self.render_combo)
        form.addRow("", render_hint)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def data(self):
        return (
            self.name_edit.text().strip(),
            self.desc_edit.toPlainText().strip(),
            self.style_combo.currentData() or "",
            self.render_combo.currentData() or "",
        )


class NewEpisodeDialog(QDialog):
    """v0.6.28：删掉 render_type 字段，渲染类型统一走项目级。
    v0.6.29：加 [📁 导入文件] 按钮，支持 .txt/.md/.docx 多选追加到剧本框。

    之前 v0.6.18 加的剧集级 render_type 实际是冗余的（项目级已经定好）。
    现在新建/编辑剧集不再让用户选 render_type，避免用户重复配置。
    """

    # v0.6.29：支持的文件类型
    SCRIPT_FILE_FILTER = (
        "剧本文件 (*.txt *.md *.docx);;文本文件 (*.txt);;Markdown (*.md);;Word 文档 (*.docx);;所有文件 (*)"
    )

    def __init__(
        self,
        parent=None,
        default_num: int = 1,
        default_title: str = "",
        default_script: str = "",
    ):
        super().__init__(parent)
        self.setWindowTitle("剧集")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.num_edit = QSpinBox()
        self.num_edit.setRange(1, 9999)
        self.num_edit.setValue(default_num)
        self.title_edit = QLineEdit(default_title)
        self.title_edit.setPlaceholderText("例：把师尊炸死了")
        self.script_edit = QTextEdit(default_script)
        self.script_edit.setPlaceholderText(
            "原始剧本（可空）\n"
            "可手动输入，或点下方 [📁 导入文件] 从 .txt / .md / .docx 加载\n"
            "（支持多选，内容会追加到现有剧本后面）"
        )
        self.script_edit.setFixedHeight(160)
        # v0.6.29：剧本框 + 导入按钮 横向布局
        script_row = QHBoxLayout()
        script_row.addWidget(self.script_edit, 1)
        script_col = QVBoxLayout()
        script_col.setSpacing(6)
        self._btn_import = QPushButton("📁\n导入\n文件")
        self._btn_import.setFixedWidth(56)
        self._btn_import.setToolTip(
            "从本地文件加载剧本到上方输入框\n"
            "支持 .txt / .md / .docx\n"
            "可多选，多个文件内容会依次追加"
        )
        self._btn_import.clicked.connect(self._on_import_files)
        script_col.addWidget(self._btn_import)
        script_col.addStretch(1)
        script_row.addLayout(script_col)
        form.addRow("集数", self.num_edit)
        form.addRow("标题 *", self.title_edit)
        form.addRow("剧本", script_row)
        # v0.6.28：渲染类型移到项目级，剧集不再单选
        render_hint = QLabel(
            "渲染类型在项目级配置（项目设置 → 渲染类型），所有剧集共用。"
        )
        render_hint.setStyleSheet("color: #888; font-size: 11px;")
        form.addRow("", render_hint)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def data(self):
        """v0.6.28：返回 3-tuple（num, title, script）— 不再返回 render_type。"""
        return (
            self.num_edit.value(),
            self.title_edit.text().strip(),
            self.script_edit.toPlainText(),
        )

    # ============ v0.6.29 剧本文件导入 ============

    def _on_import_files(self) -> None:
        """弹文件选择对话框，多选 .txt/.md/.docx，追加到剧本框。"""
        # v0.6.29：用 self 作为 parent 避免 Z-order 问题
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择剧本文件（可多选）",
            "",
            self.SCRIPT_FILE_FILTER,
        )
        if not files:
            return
        # 读取并追加
        success_parts: list[str] = []
        failed: list[tuple[str, str]] = []  # (path, reason)
        for fp in files:
            try:
                content = _read_script_file(fp)
                if content:
                    success_parts.append(f"=== {os.path.basename(fp)} ===\n{content}")
                else:
                    # 空文件也提示一下，但不报错
                    success_parts.append(f"=== {os.path.basename(fp)} ===\n（文件为空）")
            except Exception as e:  # noqa: BLE001
                failed.append((os.path.basename(fp), f"{type(e).__name__}: {e}"))
        # 追加到剧本框（保留原内容）
        if success_parts:
            existing = self.script_edit.toPlainText()
            new_block = "\n\n".join(success_parts)
            if existing.strip():
                self.script_edit.setPlainText(existing + "\n\n" + new_block)
            else:
                self.script_edit.setPlainText(new_block)
        # 失败汇总（不阻塞，只提示）
        if failed:
            msg = "以下文件导入失败：\n" + "\n".join(
                f"  - {n}: {r}" for n, r in failed
            )
            QMessageBox.warning(self, "部分文件导入失败", msg)
        # 成功摘要
        if success_parts and not failed:
            # 简短提示
            n = len(success_parts)
            QMessageBox.information(
                self, "导入完成", f"已成功导入 {n} 个文件到剧本框。"
            )
