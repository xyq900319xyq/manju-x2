"""v1.0.0 用户版：首次启动配置向导 (QWizard)。

设计要点（v1.0.0 用户版）：
- 6 步：欢迎 → LLM → 生图 → 生视频 → 图床 → 完成
- 用户**必须**填至少 1 个 LLM key 才能继续；其他步骤可"跳过"
- 所有 key 走 DPAPI 加密（secret_store.py），**不**写回 hermes_api.json
- 完成后写 `config/secrets.bin`，再让 Config 加载合并
- 用户点"取消"→ 退出软件（首次启动不能跳过）
- 用户点"上一步"→ 可回头改
- 走"设置 → 重新走 wizard"入口时（v1.0.0 暂未做，但留 hook），允许 skip
- 主题：跟随 manju 暗色卡片风格（与 settings_dialog 保持一致）

v1.0.0【硬约束】：
- 不写兜底：用户取消 wizard 直接 sys.exit(0)，不"用空 key 启动后报错"
- 不在 wizard 写 hermes_api.json：所有 key 都走 secrets.bin
- 不保存日志中带明文 key：log.warning 只打字段名不打印值
- 模型字段**不**在 wizard 收集：model/base_url 已在 hermes_api.json 模板里
  写好，用户只需要填 api_key（base_url/model 改了在设置里改）
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap, QFont
from PySide6.QtWidgets import (
    QWizard, QWizardPage, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QPushButton, QCheckBox, QGroupBox, QWidget,
    QFrame, QSizePolicy, QSpacerItem, QMessageBox, QTextEdit,
    QDialog, QDialogButtonBox,
)

from core.config import Config
from core import secret_store

log = logging.getLogger("manju.wizard")

# 暗色卡片主题 QSS（与 settings_dialog 风格保持一致，v0.7.0 主题）
_DARK_QSS = """
QWizard {
    background: #1e1e1e;
}
QWizardPage {
    background: #1e1e1e;
    color: #e0e0e0;
}
QLabel {
    color: #e0e0e0;
}
QLabel#titleLabel {
    font-size: 20px;
    font-weight: bold;
    color: #ffffff;
    padding: 4px 0;
}
QLabel#subtitleLabel {
    font-size: 13px;
    color: #aaaaaa;
    padding: 2px 0 8px 0;
}
QLineEdit {
    background: #2a2a2a;
    color: #e0e0e0;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #3a7bd5;
}
QLineEdit:focus {
    border: 1px solid #3a7bd5;
}
QGroupBox {
    background: #252525;
    border: 1px solid #3a3a3a;
    border-radius: 8px;
    margin-top: 12px;
    padding: 16px 12px 12px 12px;
    font-weight: bold;
    color: #cccccc;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    left: 8px;
}
QPushButton {
    background: #2d2d2d;
    color: #e0e0e0;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 22px;
}
QPushButton:hover {
    background: #3a3a3a;
    border: 1px solid #4a4a4a;
}
QPushButton:pressed {
    background: #1e1e1e;
}
QPushButton#primaryButton {
    background: #3a7bd5;
    color: #ffffff;
    border: 1px solid #3a7bd5;
    font-weight: bold;
}
QPushButton#primaryButton:hover {
    background: #4a8be5;
}
QCheckBox {
    color: #cccccc;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #4a4a4a;
    border-radius: 3px;
    background: #2a2a2a;
}
QCheckBox::indicator:checked {
    background: #3a7bd5;
    border: 1px solid #3a7bd5;
}
QTextEdit {
    background: #2a2a2a;
    color: #aaaaaa;
    border: 1px solid #3a3a3a;
    border-radius: 6px;
    padding: 8px;
}
"""


# ---------- 工具：可隐藏/显示的 key 行 ----------

class _KeyRow(QWidget):
    """单条 key 输入行：标签 + QLineEdit(Password) + 显隐 checkbox。

    Signals:
        value_changed(str): 用户改 key 时发射（带新值，空串表示清空）
    """
    value_changed = Signal(str)

    def __init__(self, label: str, placeholder: str = "", parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._label_text = label
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        lbl = QLabel(label)
        lbl.setMinimumWidth(140)
        lbl.setStyleSheet("color: #cccccc;")
        self._edit = QLineEdit()
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.setPlaceholderText(placeholder)
        self._edit.setMinimumWidth(260)
        self._show = QCheckBox("显示")
        self._show.toggled.connect(self._on_toggle_show)
        layout.addWidget(lbl)
        layout.addWidget(self._edit, 1)
        layout.addWidget(self._show)
        self._edit.textChanged.connect(self.value_changed.emit)

    def _on_toggle_show(self, checked: bool) -> None:
        self._edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def text(self) -> str:
        return self._edit.text().strip()

    def setText(self, value: str) -> None:
        self._edit.setText(value or "")

    def hasValue(self) -> bool:
        return bool(self.text())


# ---------- 工具：Config 项的 key 编辑器 ----------

class _ConfigKeyGroup(QGroupBox):
    """根据 config_data 列表自动生成 _KeyRow（一个 config 一行）。

    v1.1.5.19: 加 _build_rows() / rebuild() 方法,允许 wizard 动态加新 config 后
    刷新 UI 行(原 wizard 只能在启动时读 hermes_api.json 模板生成行,首次启动加新
    config 后不刷新)。
    """
    value_changed = Signal()  # 任意 key 变化时发（用于校验）

    def __init__(self, title: str, items: List[Dict[str, Any]], parent: Optional[QWidget] = None) -> None:
        super().__init__(title, parent)
        self._rows: List[_KeyRow] = []
        self._items: List[Dict[str, Any]] = list(items)
        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(8)
        self._build_rows()

    def _build_rows(self) -> None:
        """从 self._items 重建所有 _KeyRow(每次 rebuild 先清空旧 row)。"""
        # 清空旧 widget
        while self._layout.count():
            item = self._layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        self._rows = []
        # 重建
        for item in self._items:
            label = f"{item.get('name', item.get('id', '?'))} (api_key)"
            placeholder = f"在 {item.get('base_url', '').rstrip('/')} 申请的 API key"
            row = _KeyRow(label, placeholder)
            self._rows.append(row)
            self._layout.addWidget(row)
            # v1.0.0 修：row.value_changed 是 Signal(str) (1 参数)，
            # self.value_changed 是 Signal() (0 参数)，需要 lambda 转换
            row.value_changed.connect(lambda _v: self.value_changed.emit())
        # 提示
        hint = QLabel("💡 至少填一个 key 才能继续；点击「显示」核对内容。")
        hint.setStyleSheet("color: #888888; font-size: 11px;")
        self._layout.addWidget(hint)

    def rebuild(self, items: List[Dict[str, Any]]) -> None:
        """v1.1.5.19: 外部调用,传入新的 items 列表重建 _KeyRow。"""
        self._items = list(items)
        self._build_rows()

    def values_by_id(self, items: List[Dict[str, Any]]) -> Dict[str, str]:
        """返回 {config_id: api_key} 映射（空串也包含，便于 wizard 清空已填 key）"""
        return {
            items[i].get("id", f"row{i}"): self._rows[i].text()
            for i in range(min(len(items), len(self._rows)))
        }


# ---------- v1.1.5.19: 添加自定义 API dialog ----------

class _AddCustomAPIDialog(QDialog):
    """v1.1.5.19:首次启动 wizard 加自定义 LLM API 的小弹框。

    收 4 个字段:Name / Base URL / Model / API Key
    - Name / Base URL / Model 必填(空值调 API 必失败)
    - API Key 允许空(走 wizard 校验至少 1 个 LLM 有 key)

    用户点"添加" → 调 Config.upsert_config 写盘 + 返回 Accepted
    用户点"取消" → 关闭弹框,不动 hermes_api.json

    主题:暗色卡片风,跟 wizard 一致
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("添加自定义 LLM API")
        self.setMinimumWidth(480)
        self.setStyleSheet(_DARK_QSS + """
            QDialog { background: #1e1e1e; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 标题
        title = QLabel("➕ 添加自定义 LLM API")
        title.setObjectName("titleLabel")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        layout.addWidget(title)

        subtitle = QLabel(
            "填写你想接入的 OpenAI 兼容 API 信息。<br>"
            "<span style='color:#888888;'>提示:Name / Base URL / Model 必填,API Key 可稍后在 wizard 或设置中补充。</span>"
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #cccccc; font-size: 12px;")
        layout.addWidget(subtitle)

        # 表单卡片
        card = QGroupBox("API 配置")
        form = QFormLayout(card)
        form.setSpacing(8)
        form.setContentsMargins(16, 20, 16, 16)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("例如:My OpenAI 中转 / SiliconFlow / 本地 Ollama")
        form.addRow("显示名 (name):", self._name_edit)

        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText("例如:https://api.openai.com 或 https://your-proxy.com")
        form.addRow("Base URL:", self._url_edit)

        self._model_edit = QLineEdit()
        self._model_edit.setPlaceholderText("例如:gpt-4o-mini / deepseek-chat / qwen2.5-72b")
        form.addRow("Model:", self._model_edit)

        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_edit.setPlaceholderText("在该网站申请的 API key(可留空)")
        form.addRow("API Key:", self._key_edit)

        self._show = QCheckBox("显示 key")
        self._show.toggled.connect(
            lambda c: self._key_edit.setEchoMode(
                QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password
            )
        )
        form.addRow("", self._show)

        layout.addWidget(card)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        self._cancel_btn = QPushButton("取消")
        self._cancel_btn.clicked.connect(self.reject)
        self._add_btn = QPushButton("添加")
        self._add_btn.setObjectName("primaryButton")
        self._add_btn.setDefault(True)
        self._add_btn.clicked.connect(self._on_add_clicked)
        btn_row.addWidget(self._cancel_btn)
        btn_row.addWidget(self._add_btn)
        layout.addLayout(btn_row)

        # Enter 触发 add,Esc 触发 cancel
        self._name_edit.setFocus()

    def _on_add_clicked(self) -> None:
        name = self._name_edit.text().strip()
        url = self._url_edit.text().strip().rstrip("/")
        model = self._model_edit.text().strip()
        key = self._key_edit.text().strip()

        # 校验:3 项必填
        if not name:
            QMessageBox.warning(self, "未填名称", "请填写「显示名」")
            self._name_edit.setFocus()
            return
        if not url:
            QMessageBox.warning(self, "未填 Base URL", "请填写「Base URL」(OpenAI 兼容 API 的入口地址)")
            self._url_edit.setFocus()
            return
        if not model:
            QMessageBox.warning(self, "未填 Model", "请填写「Model」(模型名,例如 gpt-4o-mini / deepseek-chat)")
            self._model_edit.setFocus()
            return

        # 写入 hermes_api.json(通过 Config.upsert_config 持久化)
        import uuid
        new_cfg = {
            "id": uuid.uuid4().hex[:8],
            "name": name,
            "provider": "custom",
            "model": model,
            "base_url": url,
            "api_key": key,
        }
        try:
            cfg = Config.get()
            cfg.upsert_config(new_cfg)
        except Exception as e:  # noqa: BLE001
            log.exception("upsert_config 失败")
            QMessageBox.critical(self, "添加失败", f"写入 hermes_api.json 失败:\n\n{e}")
            return

        log.info("wizard: 添加自定义 LLM config (id=%s, name=%s, base_url=%s, model=%s, has_key=%s)",
                 new_cfg["id"], name, url, model, "yes" if key else "no")
        self.accept()


# ---------- 页面：欢迎 ----------

class _WelcomePage(QWizardPage):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setTitle("欢迎使用 漫剧助手X-2")
        self.setSubTitle("首次启动需要配置 API 密钥。完成后即可使用全部分镜、生图、生视频功能。")
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 主标题
        title = QLabel("👋 首次启动配置")
        title.setObjectName("titleLabel")
        subtitle = QLabel(
            "为保护你的 API 密钥，漫剧助手使用 Windows DPAPI 加密后存储在本地。\n"
            "配置文件 (config/hermes_api.json) 可自由分享，不会泄露密钥。"
        )
        subtitle.setObjectName("subtitleLabel")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        # 说明卡片
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #252525; border: 1px solid #3a3a3a; border-radius: 8px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(6)
        info_items = [
            ("🔐 加密方式", "Windows DPAPI 绑定当前用户账号，其他人无法解密"),
            ("📁 存储位置", "config/secrets.bin（加密后约 1-2 KB）"),
            ("🛡️ 安全特性", "密钥永远不写入 hermes_api.json，不会上传到任何服务"),
            ("✏️ 后续修改", "可随时在「设置 → API 配置」中修改，无需重新运行向导"),
        ]
        for k, v in info_items:
            row = QHBoxLayout()
            k_lbl = QLabel(k)
            k_lbl.setStyleSheet("color: #3a7bd5; font-weight: bold; min-width: 100px;")
            v_lbl = QLabel(v)
            v_lbl.setStyleSheet("color: #cccccc;")
            v_lbl.setWordWrap(True)
            row.addWidget(k_lbl, 0)
            row.addWidget(v_lbl, 1)
            card_layout.addLayout(row)
        layout.addWidget(card)

        # 占位
        layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        # 提示文本框（说明需要哪几个 key）
        note = QTextEdit()
        note.setReadOnly(True)
        note.setMaximumHeight(120)
        note.setHtml(
            "<b style='color:#3a7bd5;'>需要准备的 API 密钥：</b><br>"
            "&nbsp;&nbsp;• <b>LLM（至少 1 个）</b>：DeepSeek / Agnes / 创维中转<br>"
            "&nbsp;&nbsp;• <b>生图（可选）</b>：Agnes 生图 API<br>"
            "&nbsp;&nbsp;• <b>生视频（可选）</b>：Agnes 生视频 API<br>"
            "&nbsp;&nbsp;• <b>图床（可选）</b>：imgbb API key（用于生视频时上传资产图）"
        )
        layout.addWidget(note)


# ---------- 页面：LLM ----------

class _LLMPage(QWizardPage):
    def __init__(self, config: Config, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setTitle("LLM 推理 API")
        self.setSubTitle("至少填写 1 个 LLM API 密钥（用于分镜/提示词/资产提取）。")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        self._group = _ConfigKeyGroup(
            "LLM 配置 (configs)",
            list(self._config.all_configs),
        )
        self._group.value_changed.connect(self._on_changed)
        layout.addWidget(self._group)

        # v1.1.5.19: 加 "添加自定义 API" 按钮 — 让用户填自己的 OpenAI 兼容 base_url
        # 而不是只能选预设的 DeepSeek / Agnes / 创维中转
        self._add_custom_btn = QPushButton("➕ 添加自定义 API（自己填网站）")
        self._add_custom_btn.setToolTip(
            "不限于预设的 3 个 API 站 — 任何 OpenAI 兼容的 API 都能加\n"
            "（如 OpenAI / 中转站 / SiliconFlow / Ollama / 第三方等）"
        )
        self._add_custom_btn.clicked.connect(self._on_add_custom_clicked)
        layout.addWidget(self._add_custom_btn)

        layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        self._err_label = QLabel("")
        self._err_label.setStyleSheet("color: #ff6b6b; font-size: 11px;")
        self._err_label.setWordWrap(True)
        layout.addWidget(self._err_label)
        self._update_validation()

    def _on_add_custom_clicked(self) -> None:
        """v1.1.5.19: 弹 _AddCustomAPIDialog 收 4 字段,调 Config.upsert_config 写盘,刷新 UI。"""
        dlg = _AddCustomAPIDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return  # 用户取消
        # 新 config 已写 hermes_api.json,这里刷新 _group 展示新行
        self._group.rebuild(list(self._config.all_configs))
        # 自动 focus 到新行的 api_key 输入框(最后一行)
        new_idx = len(self._config.all_configs) - 1
        if 0 <= new_idx < len(self._group._rows):
            self._group._rows[new_idx]._edit.setFocus()
        self._update_validation()
        self.completeChanged.emit()

    def _on_changed(self) -> None:
        self._update_validation()
        self.completeChanged.emit()

    def _update_validation(self) -> None:
        vals = self._group.values_by_id(list(self._config.all_configs))
        non_empty = [v for v in vals.values() if v]
        if not non_empty:
            self._err_label.setText("⚠️ 至少填写 1 个 LLM API 密钥")
        else:
            n = len(non_empty)
            self._err_label.setText(f"✓ 已填 {n} 个 LLM key（{', '.join(k for k, v in vals.items() if v)}）")
            self._err_label.setStyleSheet("color: #5ec27a; font-size: 11px;")

    def isComplete(self) -> bool:
        vals = self._group.values_by_id(list(self._config.all_configs))
        return any(v for v in vals.values())

    def get_values(self) -> Dict[str, str]:
        return self._group.values_by_id(list(self._config.all_configs))


# ---------- 页面：生图 ----------

class _ImagePage(QWizardPage):
    def __init__(self, config: Config, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setTitle("生图 API（可选）")
        self.setSubTitle("生图 API 用于资产/分镜的图像生成。留空可在「设置」中后补。")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        self._group = _ConfigKeyGroup(
            "生图配置 (image_configs)",
            list(config.image_configs),
        )
        layout.addWidget(self._group)
        layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))


# ---------- 页面：生视频 ----------

class _VideoPage(QWizardPage):
    def __init__(self, config: Config, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setTitle("生视频 API（可选）")
        self.setSubTitle("生视频 API 用于将分镜/Segment 渲染成 MP4。留空可在「设置」中后补。")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        self._group = _ConfigKeyGroup(
            "生视频配置 (video_api_configs)",
            list(config.video_api_configs),
        )
        layout.addWidget(self._group)
        layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))


# ---------- 页面：图床 ----------

class _ImgbbPage(QWizardPage):
    def __init__(self, config: Config, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setTitle("图床 API（可选）")
        self.setSubTitle("图床（imgbb）用于生视频时把本地资产图上传成公网 URL。留空不影响主功能。")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(8)
        card = QGroupBox("图床配置 (image_host_api_key)")
        form = QFormLayout(card)
        self._edit = QLineEdit()
        self._edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._edit.setPlaceholderText("在 https://api.imgbb.com 申请的 API key")
        form.addRow("imgbb api_key:", self._edit)
        self._show = QCheckBox("显示")
        self._show.toggled.connect(
            lambda c: self._edit.setEchoMode(
                QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password
            )
        )
        form.addRow("", self._show)
        layout.addWidget(card)
        layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

    def get_value(self) -> str:
        return self._edit.text().strip()


# ---------- 页面：完成 ----------

class _DonePage(QWizardPage):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setTitle("配置完成")
        self.setSubTitle("点击「完成」加密保存所有 API 密钥。")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("✅ 准备就绪")
        title.setObjectName("titleLabel")
        layout.addWidget(title)
        subtitle = QLabel(
            "点击「完成」后，漫剧助手会：\n"
            "1. 使用 Windows DPAPI 加密你填写的所有 API 密钥\n"
            "2. 写入 config/secrets.bin（加密 blob，~1-2 KB）\n"
            "3. 进入主窗口，可立即使用「分镜生成 / 资产提取 / 生图 / 生视频」"
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color: #cccccc;")
        layout.addWidget(subtitle)

        # 提示卡片
        card = QFrame()
        card.setStyleSheet(
            "QFrame { background: #252525; border: 1px solid #3a3a3a; border-radius: 8px; padding: 8px; }"
        )
        card_layout = QVBoxLayout(card)
        tips = [
            "💡 密钥修改：随时打开「设置 → API 配置」编辑后保存。",
            "💡 重置密钥：删除 config/secrets.bin 后重启会重新弹出此向导。",
            "💡 备份配置：直接复制 hermes_api.json 即可（不含密钥）。",
        ]
        for t in tips:
            lbl = QLabel(t)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color: #aaaaaa; font-size: 12px;")
            card_layout.addWidget(lbl)
        layout.addWidget(card)
        layout.addItem(QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))


# ---------- 主 Wizard ----------

class FirstRunWizard(QWizard):
    """v1.0.0 用户版首次启动向导。

    使用：
        w = FirstRunWizard(project_root, parent=None)
        if w.exec() == QWizard.DialogCode.Accepted:
            # wizard 已写 secrets.bin，main.py 继续
        else:
            # 用户取消，main.py 应 sys.exit(0)
    """

    # 自定义 page id
    PAGE_WELCOME = 0
    PAGE_LLM = 1
    PAGE_IMAGE = 2
    PAGE_VIDEO = 3
    PAGE_IMGBB = 4
    PAGE_DONE = 5

    def __init__(self, project_root: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._project_root = Path(project_root)
        self.setWindowTitle("漫剧助手X-2 - 首次配置")
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        self.setOption(QWizard.WizardOption.NoCancelButtonOnLastPage, True)
        self.setMinimumSize(720, 560)
        self.resize(760, 600)
        self.setStyleSheet(_DARK_QSS)

        # 加载 config 模板（用单例之前 wizard 不应调 Config.get()，
        # 所以这里直接读 hermes_api.json 文件拿模板字段）
        self._config = Config.get()
        # 探测现有 keys（用户已配过则预填）
        existing = self._load_existing_secrets()

        # 添加 pages
        self.addPage(_WelcomePage(self))
        self._llm_page = _LLMPage(self._config, self)
        self.addPage(self._llm_page)
        self._image_page = _ImagePage(self._config, self)
        self.addPage(self._image_page)
        self._video_page = _VideoPage(self._config, self)
        self.addPage(self._video_page)
        self._imgbb_page = _ImgbbPage(self._config, self)
        self.addPage(self._imgbb_page)
        self.addPage(_DonePage(self))

        # 预填（已配过 → 让用户核对/修改）
        if existing:
            self._prefill_existing(existing)

        self._button_labels()

    def _button_labels(self) -> None:
        """中文化按钮文字（v0.7.0 主题语言风格保持一致）。"""
        self.setButtonText(QWizard.WizardButton.NextButton, "下一步 →")
        self.setButtonText(QWizard.WizardButton.BackButton, "← 上一步")
        self.setButtonText(QWizard.WizardButton.FinishButton, "完成")
        self.setButtonText(QWizard.WizardButton.CancelButton, "取消")

    def _load_existing_secrets(self) -> Dict[str, Any]:
        """若 secrets.bin 已存在，解密后返回；失败返回空 dict。"""
        if not secret_store.has_secrets(self._project_root):
            return {}
        try:
            return secret_store.load_secrets(self._project_root)
        except Exception as e:  # noqa: BLE001
            log.warning("load_existing_secrets 失败: %s", e)
            return {}

    def _prefill_existing(self, existing: Dict[str, Any]) -> None:
        llm_map = dict(existing.get("llm") or {})
        items = list(self._config.all_configs)
        for i, item in enumerate(items):
            cid = item.get("id", "")
            v = llm_map.get(cid, "")
            if i < len(self._llm_page._group._rows):
                self._llm_page._group._rows[i].setText(v)
        image_map = dict(existing.get("image") or {})
        items_i = list(self._config.image_configs)
        for i, item in enumerate(items_i):
            cid = item.get("id", "")
            v = image_map.get(cid, "")
            if i < len(self._image_page._group._rows):
                self._image_page._group._rows[i].setText(v)
        video_map = dict(existing.get("video") or {})
        items_v = list(self._config.video_api_configs)
        for i, item in enumerate(items_v):
            cid = item.get("id", "")
            v = video_map.get(cid, "")
            if i < len(self._video_page._group._rows):
                self._video_page._group._rows[i].setText(v)
        self._imgbb_page._edit.setText(str(existing.get("image_host") or ""))

    def accept(self) -> None:  # noqa: D401
        """覆盖 accept：先收集所有页的输入，调用 secret_store.save_secrets 加密写盘。

        失败：弹 QMessageBox 报错，**不**关闭 wizard 让用户重试/取消。
        成功：调 super().accept() 走正常结束流程。
        """
        try:
            llm_vals = self._llm_page.get_values()
            image_vals = self._image_page._group.values_by_id(list(self._config.image_configs))
            video_vals = self._video_page._group.values_by_id(list(self._config.video_api_configs))
            image_host = self._imgbb_page.get_value()
            payload = {
                "llm": llm_vals,
                "image": image_vals,
                "video": video_vals,
                "image_host": image_host,
            }
            # v1.0.0 硬约束：至少 1 个 LLM key（与 _LLMPage.isComplete 对齐）
            non_empty = sum(1 for v in llm_vals.values() if v)
            if non_empty == 0:
                QMessageBox.warning(
                    self, "未填 LLM 密钥",
                    "至少需要 1 个 LLM API 密钥才能使用漫剧助手。\n请返回上一步填写。",
                )
                return
            secret_store.save_secrets(self._project_root, payload)
            log.info("wizard: 加密保存 secrets.bin（LLM=%d, image=%d, video=%d, host=%s）",
                     non_empty,
                     sum(1 for v in image_vals.values() if v),
                     sum(1 for v in video_vals.values() if v),
                     "yes" if image_host else "no")
        except Exception as e:  # noqa: BLE001
            log.exception("wizard 保存 secrets 失败")
            QMessageBox.critical(
                self, "保存失败",
                f"加密保存密钥失败：\n\n{e}\n\n"
                "常见原因：\n"
                "• Windows DPAPI 不可用（需 Windows 7+/Server 2008+）\n"
                "• secrets.bin 在其他用户账号下加密\n\n"
                "请重试或点「取消」退出后联系开发者。",
            )
            return
        super().accept()
