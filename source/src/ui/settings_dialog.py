"""设置对话框：编辑 config/hermes_api.json 里的 API 配置 + Hermes 设置 + 视频 API。

可编辑内容：
- Tab "🔑 API 配置"：list / set_active / name / provider / model / base_url / api_key / 加/复制/删
- Tab "⚙️ Hermes 设置"（v0.6.25 #17）：hermes_exe / outputs_dir / HERMES_HOME / timeout / 3 profiles
- Tab "🎬 视频 API"（v0.7.8.38）：
  - Web 生成（dreamina.exe + OAuth 登录）
  - API 生成（中转 API 多 config，复刻生图 API 多 config 结构）

「保存」按钮 → 把当前表单写回 json（保留未编辑字段）。
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QVBoxLayout, QFormLayout, QListWidget,
    QListWidgetItem, QLineEdit, QPushButton, QLabel, QDialogButtonBox,
    QMessageBox, QWidget, QApplication, QTabWidget, QSpinBox, QFileDialog,
    QFrame, QComboBox, QStackedWidget, QGroupBox, QSizePolicy,
)
from PySide6.QtCore import Qt, Slot, QUrl, QTimer
from PySide6.QtGui import QDesktopServices

log = logging.getLogger("manju.settings")


# ============ v0.7.8.38 dreamina.exe 辅助函数 ============
# 复刻自 D:\剧本分镜助手\server.py:3114-3267
# _dreamina_run_to_file / _dreamina_logged_in / login start/poll/logout 端点
# 精简到 settings_dialog 内联使用（避免新建文件）


def _dreamina_find_bin(explicit_path: str = "") -> Optional[str]:
    """v0.7.8.38：查找 dreamina CLI 二进制文件（仿 server.py:2015-2037）。

    优先级：用户显式配 > 项目目录 > ~/.local/bin > PATH
    """
    import shutil as _shutil
    candidates = []
    if explicit_path:
        candidates.append(explicit_path)
    if os.name == "nt":
        candidates += [
            os.path.expanduser("~/dreamina.exe"),
            os.path.join(os.path.dirname(__file__), "..", "..", "dreamina.exe"),
            os.path.expanduser("~/.local/bin/dreamina.exe"),
        ]
    else:
        candidates += [
            os.path.join(os.path.dirname(__file__), "..", "..", "dreamina"),
            os.path.expanduser("~/.local/bin/dreamina"),
        ]
    for c in candidates:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    which = _shutil.which("dreamina.exe" if os.name == "nt" else "dreamina")
    return which


def _dreamina_run_to_file(bin_path: str, args: str, timeout: float = 30.0) -> str:
    """v0.7.8.38：运行 dreamina 命令，输出重定向到临时文件（避免 Windows PIPE 缓冲问题）。
    复刻 server.py:3114-3139 _dreamina_run_to_file。"""
    if not bin_path or not os.path.exists(bin_path):
        return ""
    base = os.path.join(tempfile.gettempdir(), f"_dm_{uuid.uuid4().hex[:8]}")
    tp = base + ".txt"
    bat = base + ".bat"
    try:
        bat_enc = "gbk" if os.name == "nt" else "utf-8"
        with open(bat, "w", encoding=bat_enc) as f:
            f.write(f'@"{bin_path}" {args} > "{tp}" 2>&1\n')
        # CREATE_NO_WINDOW 抑制 dreamina 子进程黑框（manju 自己也是 GUI 工具）
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        p = subprocess.Popen(
            f'cmd.exe /c "{bat}"',
            shell=True,
            creationflags=creationflags,
        )
        dl = time.time() + timeout
        while time.time() < dl:
            if p.poll() is not None:
                break
            time.sleep(0.2)
        if p.poll() is None:
            p.kill()
        time.sleep(0.3)
        if not os.path.exists(tp):
            return ""
        with open(tp, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        log.warning("_dreamina_run_to_file 异常: %s", e)
        return ""
    finally:
        for f in (tp, bat):
            try:
                if os.path.exists(f):
                    os.unlink(f)
            except OSError:
                pass


def _dreamina_logged_in(bin_path: str) -> bool:
    """v0.7.8.38：检查 dreamina 是否已登录（复刻 server.py:3142-3169）。"""
    if not bin_path or not os.path.exists(bin_path):
        return False
    tf = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    tp = tf.name
    tf.close()
    bat = tp + ".bat"
    try:
        bat_enc = "gbk" if os.name == "nt" else "utf-8"
        with open(bat, "w", encoding=bat_enc) as f:
            f.write(f'@"{bin_path}" user_credit > "{tp}" 2>&1\n')
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        p = subprocess.Popen(
            f'cmd.exe /c "{bat}"',
            shell=True,
            creationflags=creationflags,
        )
        dl = time.time() + 8
        while time.time() < dl:
            if p.poll() is not None:
                break
            time.sleep(0.2)
        if p.poll() is None:
            p.kill()
        time.sleep(0.2)
        return p.poll() == 0
    except Exception as e:
        log.warning("_dreamina_logged_in 异常: %s", e)
        return False
    finally:
        for f in (tp, bat):
            try:
                if os.path.exists(f):
                    os.unlink(f)
            except OSError:
                pass


def _dreamina_start_login(bin_path: str) -> Tuple[bool, Dict[str, Any]]:
    """v0.7.8.38：启动 OAuth Device Flow（复刻 server.py:3190-3232）。

    返回 (ok, info)：
        ok=True, info={"verification_uri": ..., "user_code": ..., "device_code": ...,
                       "already_logged_in": bool}
    """
    if not bin_path or not os.path.exists(bin_path):
        return False, {"error": "dreamina CLI 未找到（请先在 Web 生成里配 dreamina.exe 路径）"}
    output = _dreamina_run_to_file(bin_path, "login --headless", timeout=15.0)
    if not output:
        return False, {"error": "无法获取登录码，请确认 dreamina.exe 路径正确且网络正常"}
    # 已登录（"已复用当前本地 OAuth 登录态"）
    if "已复用" in output or "已登录" in output:
        return True, {
            "already_logged_in": True,
            "verification_uri": "",
            "user_code": "",
            "device_code": "",
        }
    import re as _re
    verification_uri = ""
    user_code = ""
    device_code = ""
    for line in output.split("\n"):
        line = line.strip()
        if line.startswith("verification_uri:"):
            verification_uri = line.split(":", 1)[1].strip()
        elif line.startswith("user_code:"):
            user_code = line.split(":", 1)[1].strip()
        elif line.startswith("device_code:"):
            device_code = line.split(":", 1)[1].strip()
    if not device_code:
        return False, {"error": "无法获取 device_code", "raw": output}
    return True, {
        "already_logged_in": False,
        "verification_uri": verification_uri,
        "user_code": user_code,
        "device_code": device_code,
    }


def _dreamina_poll_login(bin_path: str) -> Tuple[bool, str]:
    """v0.7.8.38：检查登录是否完成（复刻 server.py:3235-3245 user_credit 检测）。"""
    if not bin_path or not os.path.exists(bin_path):
        return False, ""
    output = _dreamina_run_to_file(bin_path, "user_credit", timeout=10.0)
    success = "credit" in output.lower() or "余额" in output
    return success, output[:500]


def _dreamina_logout_paths() -> list:
    """v0.7.8.38：可能的 dreamina token 文件路径（复刻 server.py:3248-3267）。"""
    return [
        os.path.expanduser("~/.local/share/dreamina/byted_cli_user_token.json"),
        os.path.expanduser("~/.dreamina_cli/byted_cli_user_token.json"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "dreamina", "byted_cli_user_token.json"),
        os.path.join(os.environ.get("APPDATA", ""), "dreamina", "byted_cli_user_token.json"),
    ]


def _dreamina_logout() -> list:
    """v0.7.8.38：删除 dreamina 登录 token 文件，返回删除的文件路径列表。"""
    removed = []
    for p in _dreamina_logout_paths():
        try:
            if os.path.exists(p):
                os.remove(p)
                removed.append(p)
        except OSError:
            pass
    return removed


class SettingsDialog(QDialog):
    """编辑 hermes_api.json 的 API 配置项。

    内存流程：
    1. 构造时 deep-copy 当前 json 的 configs + active 到 self._data
    2. 用户切列表 → 右侧表单刷新为该 config 的内容
    3. 用户改表单 → 仅改 self._data 内存对象
    4. 取消 → 直接关闭
    5. 保存 → 把 self._data 写回原 json 路径
    """

    # json 里可编辑的字段
    EDITABLE_FIELDS = ("name", "provider", "model", "base_url", "api_key")

    def __init__(self, config_path: Path, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("设置 · API 配置")
        # v0.7.7 重打 17：上下布局需要更高，加到 820
        self.setMinimumSize(820, 820)
        self._path = Path(config_path)
        # 读盘 + 深拷贝（避免直接改共享 dict）
        with open(self._path, "r", encoding="utf-8") as f:
            self._raw: Dict[str, Any] = json.load(f)
        self._data: Dict[str, Any] = {
            "configs": [dict(c) for c in self._raw.get("configs", [])],
            "active": self._raw.get("active", ""),
        }
        self._active_id: str = self._data["active"]
        self._current_idx: int = self._resolve_initial_index()

        # v0.7.7：生图 API 多 config 内存结构（仿 LLM `configs/active`）
        self._image_data: Dict[str, Any] = self._init_image_data()
        self._image_active_id: str = self._image_data["active"]
        self._image_current_idx: int = self._image_resolve_initial_index()

        # v0.7.8.38：视频 API 多 config 内存结构（仿生图 API + LLM `configs/active`）
        self._video_api_data: Dict[str, Any] = self._init_video_api_data()
        self._video_api_active_id: str = self._video_api_data["active"]
        self._video_api_current_idx: int = self._video_api_resolve_initial_index()

        # v0.7.7 重打 15：_loading 守卫。_refresh_list 会调 setCurrentRow(idx)
        # → currentRowChanged → _on_row_changed → _commit_form_to_data()。
        # 但此时 form 字段还是空（_load_form_for_index 还没跑），
        # 空字符串会被写回 _data[configs][idx]，紧接着 _load_form_for_index
        # 从被清空的 _data 读 → form 全空。
        # 同样的路径也存在于 _refresh_image_list → _commit_image_form_to_data。
        # _loading=True 时两个 _commit_* 直接 return。
        self._loading: bool = True
        self._build_ui()
        self._refresh_list()
        self._load_form_for_index(self._current_idx)
        # 刷新生图列表 + 加载初始 form
        self._refresh_image_list()
        self._load_image_form_for_index(self._image_current_idx)
        # v0.7.8.38：刷新视频 API 列表 + 加载初始 form
        self._refresh_video_api_list()
        self._load_video_api_form_for_index(self._video_api_current_idx)
        # v0.7.8.50:Web 生成(dreamina)状态异步刷新 —— 原同步调 _refresh_dreamina_status
        # 会跑 subprocess 启动 dreamina.exe 探测登录状态(2-5s),严重卡设置 dialog 打开。
        # 推到下个 event loop tick,UI 先显示,后台慢慢查。
        QTimer.singleShot(0, self._refresh_dreamina_status)
        self._loading = False

    # ---------- 内部 ----------

    def _resolve_initial_index(self) -> int:
        """默认选中当前 active。"""
        for i, c in enumerate(self._data["configs"]):
            if c.get("id") == self._active_id:
                return i
        return 0 if self._data["configs"] else -1

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        # ---- v0.6.25：包一层 QTabWidget（"API 配置" / "Hermes 设置"） ----
        self.tabs = QTabWidget()

        # ============ Tab 1: API 配置 ============
        # v0.7.7 重打 17：上下布局
        # 上半：推理 API（list + form 并列）
        # 下半：生图 API（list + form 并列）
        # 每段都是 [List | Form] 横向布局，不再用 QStackedWidget 切换。
        api_page = QWidget()
        api_root = QVBoxLayout(api_page)
        api_root.setContentsMargins(8, 8, 8, 8)
        api_root.setSpacing(10)

        # ---- 上半：推理 API 段 ----
        # 1) 左侧 list + 按钮
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        self.btn_activate = QPushButton("● 设为当前激活")
        self.btn_activate.clicked.connect(self._on_activate_clicked)
        self.btn_add = QPushButton("➕ 加")
        self.btn_add.setToolTip("新增一个空白推理 API 配置")
        self.btn_add.clicked.connect(self._on_add_clicked)
        self.btn_duplicate = QPushButton("📋 复制")
        self.btn_duplicate.setToolTip("复制当前选中的推理配置（追加到末尾，name 加 '副本' 后缀）")
        self.btn_duplicate.clicked.connect(self._on_duplicate_clicked)
        self.btn_delete = QPushButton("🗑 删")
        self.btn_delete.setToolTip("删除当前选中的推理配置（删 active 时 fallback 到第一个剩余）")
        self.btn_delete.clicked.connect(self._on_delete_clicked)
        # 2) 右侧 form
        llm_form_widget = self._build_llm_form_widget()
        # 3) 拼成一段
        llm_section = self._build_api_section(
            title="🔤 推理 API 配置（LLM 推理）",
            list_widget=self.list_widget,
            btn_activate=self.btn_activate,
            row_buttons=[self.btn_add, self.btn_duplicate, self.btn_delete],
            form_widget=llm_form_widget,
        )
        api_root.addLayout(llm_section, 1)

        # 分隔线
        sep_mid = QFrame()
        sep_mid.setFrameShape(QFrame.Shape.HLine)
        sep_mid.setFrameShadow(QFrame.Shadow.Sunken)
        api_root.addWidget(sep_mid)

        # ---- 下半：生图 API 段 ----
        # 1) 左侧 list + 按钮
        self.image_list_widget = QListWidget()
        self.image_list_widget.currentRowChanged.connect(self._on_image_row_changed)
        self.btn_image_activate = QPushButton("● 设为当前激活")
        self.btn_image_activate.clicked.connect(self._on_image_activate_clicked)
        self.btn_image_add = QPushButton("➕ 加")
        self.btn_image_add.setToolTip("新增生图 API 配置")
        self.btn_image_add.clicked.connect(self._on_image_add_clicked)
        self.btn_image_duplicate = QPushButton("📋 复制")
        self.btn_image_duplicate.setToolTip("复制当前选中的生图配置")
        self.btn_image_duplicate.clicked.connect(self._on_image_duplicate_clicked)
        self.btn_image_delete = QPushButton("🗑 删")
        self.btn_image_delete.setToolTip("删除当前选中的生图配置")
        self.btn_image_delete.clicked.connect(self._on_image_delete_clicked)
        # 2) 右侧 form
        image_form_widget = self._build_image_form_widget()
        # 3) 拼成一段
        image_section = self._build_api_section(
            title="🖼 生图 API 配置（多 config）",
            list_widget=self.image_list_widget,
            btn_activate=self.btn_image_activate,
            row_buttons=[self.btn_image_add, self.btn_image_duplicate, self.btn_image_delete],
            form_widget=image_form_widget,
        )
        api_root.addLayout(image_section, 1)

        # 视频 API 占位信息放到 tabs 标题 tooltip
        self.tabs.setTabToolTip(0, "🔑 API 配置 · 复刻自老 software index.html:1824-1855\n"
                                "上半：推理 API（LLM 推理）多 config\n"
                                "下半：生图 API 多 config，v0.7.8 计划加视频 API")

        self.tabs.addTab(api_page, "🔑 API 配置")

        # ============ Tab 2: Hermes 设置（v0.6.25 #17） ============
        hermes_page = QWidget()
        hermes_root = QVBoxLayout(hermes_page)
        hermes_root.setContentsMargins(12, 12, 12, 12)

        hermes_root.addWidget(QLabel(
            "<b>Hermes 调用配置</b><br>"
            "这些字段写到 hermes_api.json，保存后重新启动 App 生效。"
        ))

        hermes_form = QFormLayout()
        hermes_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        # hermes.exe
        hermes_exe_row = QHBoxLayout()
        self.hermes_exe_edit = QLineEdit(str(self._raw.get("hermes_exe", "")))
        self.hermes_exe_edit.setPlaceholderText("例如 D:/hermes/hermes-agent/hermes.exe")
        hermes_exe_row.addWidget(self.hermes_exe_edit, 1)
        self.btn_browse_hermes_exe = QPushButton("📂 浏览")
        self.btn_browse_hermes_exe.clicked.connect(self._on_browse_hermes_exe)
        hermes_exe_row.addWidget(self.btn_browse_hermes_exe)
        hermes_form.addRow("Hermes 可执行文件:", hermes_exe_row)

        # outputs_dir
        outputs_dir_row = QHBoxLayout()
        self.outputs_dir_edit = QLineEdit(str(self._raw.get("outputs_dir", "outputs")))
        self.outputs_dir_edit.setPlaceholderText("例如 D:/漫剧助手/outputs")
        outputs_dir_row.addWidget(self.outputs_dir_edit, 1)
        self.btn_browse_outputs_dir = QPushButton("📂 浏览")
        self.btn_browse_outputs_dir.clicked.connect(self._on_browse_outputs_dir)
        outputs_dir_row.addWidget(self.btn_browse_outputs_dir)
        hermes_form.addRow("Outputs 目录:", outputs_dir_row)

        # HERMES_HOME（v0.6.25 持久化字段，未设时让 detector 自动探）
        hermes_home_row = QHBoxLayout()
        self.hermes_home_edit = QLineEdit(str(self._raw.get("hermes_home", "")))
        self.hermes_home_edit.setPlaceholderText("（留空则自动检测 ~/.hermes / 临时目录）")
        hermes_home_row.addWidget(self.hermes_home_edit, 1)
        self.btn_browse_hermes_home = QPushButton("📂 浏览")
        self.btn_browse_hermes_home.clicked.connect(self._on_browse_hermes_home)
        hermes_home_row.addWidget(self.btn_browse_hermes_home)
        hermes_form.addRow("HERMES_HOME:", hermes_home_row)

        # timeout_seconds
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(60, 86400)
        self.timeout_spin.setSuffix(" 秒")
        self.timeout_spin.setValue(int(self._raw.get("timeout_seconds", 7200) or 7200))
        hermes_form.addRow("调用超时:", self.timeout_spin)

        hermes_root.addLayout(hermes_form)

        # Profiles 列表
        hermes_root.addWidget(QLabel(""))
        hermes_root.addWidget(QLabel(
            "<b>Hermes Profiles 目录名</b><br>"
            "对应 HERMES_HOME 下的 profiles/&lt;name&gt;/ 子目录，hermes 启动时按这里写的名字找 config.yaml。"
        ))
        # v0.6.25 #17 bug fix：按原始 config 里的 profiles 字段建表（不要硬编码，
        # 否则会插入新 key 把老结构破坏。原 config 里有 "video_prompt" 不是 "video"）
        profiles = self._raw.get("profiles") or {}
        self.profile_edits: Dict[str, QLineEdit] = {}
        profile_form = QFormLayout()
        profile_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        for key in profiles.keys():
            edit = QLineEdit(str(profiles.get(key, "")))
            edit.setPlaceholderText(f"profiles/{key}/ 子目录名")
            self.profile_edits[key] = edit
            profile_form.addRow(f"{key}:", edit)
        hermes_root.addLayout(profile_form)

        # auto-detect 按钮
        self.btn_detect_hermes = QPushButton("🔍 自动检测 HERMES_HOME")
        self.btn_detect_hermes.setToolTip(
            "扫 ~/.hermes / 临时目录 MSI* / hermes_exe.parent.parent，找包含 profiles/<name>/ 的目录"
        )
        self.btn_detect_hermes.clicked.connect(self._on_detect_hermes_home)
        hermes_root.addWidget(self.btn_detect_hermes)

        hermes_root.addStretch(1)
        self.tabs.addTab(hermes_page, "⚙️ Hermes 设置")

        # ============ Tab 3: 视频 API（v0.7.8.38）============
        # 与 "🔑 API 配置" / "⚙️ Hermes 设置" 平级。
        # tab 内分两部分：
        #   A. Web 生成（dreamina.exe，OAuth 登录）—— 复刻老 software
        #      D:\剧本分镜助手\server.py:3174-3267 dreamina login-status/start/poll/logout
        #   B. API 生成（中转 API 多 config，仿生图 API 段）——
        #      OpenAI 兼容 HTTP /v1/videos/generations 类接口
        video_page = QWidget()
        video_root = QVBoxLayout(video_page)
        video_root.setContentsMargins(8, 8, 8, 8)
        video_root.setSpacing(10)

        # ---- A. Web 生成（dreamina.exe） ----
        web_group = QGroupBox("🌐 Web 生成（dreamina.exe）")
        web_root = QVBoxLayout(web_group)
        web_root.setContentsMargins(10, 14, 10, 10)
        web_root.setSpacing(8)

        # 路径
        web_form = QFormLayout()
        web_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        web_form.setSpacing(6)
        exe_row = QHBoxLayout()
        self.dreamina_exe_edit = QLineEdit(str(self._raw.get("dreamina_exe", "") or ""))
        self.dreamina_exe_edit.setPlaceholderText("例如 D:/hermes/dreamina.exe（留空会自动检测 PATH / ~/dreamina.exe）")
        self.dreamina_exe_edit.editingFinished.connect(self._on_dreamina_exe_changed)
        exe_row.addWidget(self.dreamina_exe_edit, 1)
        self.btn_browse_dreamina = QPushButton("📂 浏览")
        self.btn_browse_dreamina.clicked.connect(self._on_browse_dreamina_exe)
        exe_row.addWidget(self.btn_browse_dreamina)
        self.btn_test_dreamina = QPushButton("🔍 测试")
        self.btn_test_dreamina.setToolTip("检查 dreamina.exe 是否能找到 / 可执行")
        self.btn_test_dreamina.clicked.connect(self._on_test_dreamina)
        exe_row.addWidget(self.btn_test_dreamina)
        web_form.addRow("dreamina.exe:", exe_row)
        web_root.addLayout(web_form)

        # 状态条 + 登录/登出
        status_row = QHBoxLayout()
        self.dreamina_status_dot = QLabel("●")
        self.dreamina_status_dot.setStyleSheet("color: #888; font-size: 16px;")
        self.dreamina_status_dot.setFixedWidth(20)
        status_row.addWidget(self.dreamina_status_dot)
        self.dreamina_status_label = QLabel("未检测")
        self.dreamina_status_label.setStyleSheet("font-size: 12px;")
        status_row.addWidget(self.dreamina_status_label, 1)
        self.btn_dreamina_refresh = QPushButton("🔄 刷新状态")
        self.btn_dreamina_refresh.clicked.connect(self._refresh_dreamina_status)
        status_row.addWidget(self.btn_dreamina_refresh)
        self.btn_dreamina_login = QPushButton("🔐 登录")
        self.btn_dreamina_login.setToolTip("启动 OAuth Device Flow 登录 dreamina")
        self.btn_dreamina_login.clicked.connect(self._on_dreamina_login)
        status_row.addWidget(self.btn_dreamina_login)
        self.btn_dreamina_logout = QPushButton("🚪 登出")
        self.btn_dreamina_logout.setToolTip("删除 dreamina 登录 token（下次需要重新登录）")
        self.btn_dreamina_logout.clicked.connect(self._on_dreamina_logout)
        status_row.addWidget(self.btn_dreamina_logout)
        web_root.addLayout(status_row)

        video_root.addWidget(web_group)

        # ---- B. API 生成（中转 API 多 config） ----
        api_group = QGroupBox("📡 API 生成（中转 OpenAI 兼容 HTTP）")
        api_group_root = QVBoxLayout(api_group)
        api_group_root.setContentsMargins(10, 14, 10, 10)
        api_group_root.setSpacing(8)

        # 列表 + 按钮
        self.video_api_list_widget = QListWidget()
        self.video_api_list_widget.currentRowChanged.connect(self._on_video_api_row_changed)
        self.btn_video_api_activate = QPushButton("● 设为当前激活")
        self.btn_video_api_activate.clicked.connect(self._on_video_api_activate_clicked)
        self.btn_video_api_add = QPushButton("➕ 加")
        self.btn_video_api_add.setToolTip("新增视频 API 配置")
        self.btn_video_api_add.clicked.connect(self._on_video_api_add_clicked)
        self.btn_video_api_duplicate = QPushButton("📋 复制")
        self.btn_video_api_duplicate.setToolTip("复制当前选中的视频 API 配置")
        self.btn_video_api_duplicate.clicked.connect(self._on_video_api_duplicate_clicked)
        self.btn_video_api_delete = QPushButton("🗑 删")
        self.btn_video_api_delete.setToolTip("删除当前选中的视频 API 配置")
        self.btn_video_api_delete.clicked.connect(self._on_video_api_delete_clicked)
        # v0.7.8.47：图床 API 独立 section（imgbb）— 用于把本地资产图上传成公网 URL
        # 触发 API 链路的"参考生视频"模式（agnes image 字段）。
        # 独立于视频 API 多 config，单一 key（imgbb 注册送的免费 key 够用）。
        image_host_section = self._build_image_host_section()
        # v0.7.8.47：图床 key 从 raw 填到 UI（不写死，user 自己的 key）
        self._load_image_host_form()
        # form
        video_api_form_widget = self._build_video_api_form_widget()
        # 复用 _build_api_section 模板（list | form 横向）
        video_api_section = self._build_api_section(
            title="🎥 视频 API 多 config",
            list_widget=self.video_api_list_widget,
            btn_activate=self.btn_video_api_activate,
            row_buttons=[self.btn_video_api_add, self.btn_video_api_duplicate, self.btn_video_api_delete],
            form_widget=video_api_form_widget,
        )
        # v0.7.8.47：图床 section 加在视频 API section 上面（最高优先级，
        # 配 API 链路前先配图床 key）
        api_group_root.addLayout(image_host_section)
        api_group_root.addLayout(video_api_section, 1)

        video_root.addWidget(api_group, 1)

        self.tabs.setTabToolTip(2, "🎬 视频 API · v0.7.8.38\n"
                                  "Web 生成：dreamina.exe + OAuth 登录\n"
                                  "API 生成：中转 API 多 config")
        self.tabs.addTab(video_page, "🎬 视频 API")

        # v0.7.7：🖼 生图 API 不再是独立 tab —— 完全复刻老 software
        # D:\剧本分镜助手\templates\index.html:1824-1905 showApiSettingsModal，
        # 生图配置在 🔑 API 配置 tab 的 right panel 下方独立 group（apiUrl/apiKey/model
        # /resolution/ratio/negative/timeout），跟 LLM 推理 API 完全分开。

        root.addWidget(self.tabs)

        # 底部保存/取消按钮（v0.7.7 重打 14：移到外层，不再嵌在 form 里）
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Save).setText("💾 保存")
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        root.addWidget(btn_box)

    # v0.7.7 重打 17：把 form 构建拆成 3 个辅助方法，支撑上下布局
    # 上下两段共用 _build_api_section 模板（[List | Form] 横向）
    def _build_api_section(
        self,
        title: str,
        list_widget,
        btn_activate: "QPushButton",
        row_buttons: list,
        form_widget,
    ) -> "QVBoxLayout":
        """构造一段 API 配置：[List 列表 | Form 表单] 横向布局。

        title: 段标题（"🔤 推理 API 配置" / "🖼 生图 API 配置"）
        list_widget: 左侧列表（已 connect currentRowChanged）
        btn_activate: "● 设为当前激活" 按钮
        row_buttons: 一行小按钮列表（[加, 复制, 删]）
        form_widget: 右侧表单 widget（已 connect editingFinished 等）
        """
        section = QVBoxLayout()
        section.setContentsMargins(0, 0, 0, 0)
        section.setSpacing(6)

        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #6366f1;")
        section.addWidget(title_label)

        body = QHBoxLayout()
        body.setSpacing(12)

        # 左侧：list + 激活按钮 + 行内小按钮
        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(list_widget, 1)
        left.addWidget(btn_activate)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        for btn in row_buttons:
            btn_row.addWidget(btn)
        left.addLayout(btn_row)
        body.addLayout(left, 1)

        # 右侧：form
        body.addWidget(form_widget, 2)

        section.addLayout(body, 1)
        return section

    def _build_llm_form_widget(self) -> "QWidget":
        """构造推理 API 段右侧的 form widget（5 字段）。"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.form_title = QLabel("")
        self.form_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.form_title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(6)

        self.name_edit = QLineEdit()
        self.provider_edit = QLineEdit()
        # v0.7.8.10：推理 model 改 QComboBox + setEditable，跟生图段保持一致。
        # 拉取按钮拉到模型后，列表填到下拉框；用户既可下拉选，也可手动输入新模型名。
        self.model_edit = QComboBox()
        self.model_edit.setEditable(True)
        self.model_edit.setToolTip("下拉选已拉取的模型，或自己输入新模型名")
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_edit, 1)
        self.btn_fetch_models = QPushButton("🔄 拉取")
        self.btn_fetch_models.setFixedWidth(72)
        self.btn_fetch_models.setToolTip("从当前 Base URL 拉取可用模型列表")
        self.btn_fetch_models.clicked.connect(self._on_fetch_models)
        model_row.addWidget(self.btn_fetch_models)
        self.base_url_edit = QLineEdit()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        api_key_row = QHBoxLayout()
        api_key_row.addWidget(self.api_key_edit, 1)
        self.btn_toggle_key = QPushButton("👁")
        self.btn_toggle_key.setFixedWidth(36)
        self.btn_toggle_key.setCheckable(True)
        self.btn_toggle_key.toggled.connect(self._on_toggle_key)
        api_key_row.addWidget(self.btn_toggle_key)
        form.addRow("名称", self.name_edit)
        form.addRow("Provider", self.provider_edit)
        form.addRow("Model", model_row)
        form.addRow("Base URL", self.base_url_edit)
        form.addRow("API Key", api_key_row)
        layout.addLayout(form)

        # v0.7.8.10：QLineEdit 用 editingFinished；QComboBox(setEditable=True) 用 editTextChanged
        for w in (
            self.name_edit, self.provider_edit, self.base_url_edit, self.api_key_edit,
        ):
            w.editingFinished.connect(self._commit_form_to_data)
        self.model_edit.editTextChanged.connect(self._commit_form_to_data)
        return widget

    def _build_image_form_widget(self) -> "QWidget":
        """构造生图 API 段右侧的 form widget（名称 / Base URL / API Key / Model / 清晰度 / 宽高比 / 超时）。"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.image_form_title = QLabel("")
        self.image_form_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.image_form_title)

        img_form_layout = QFormLayout()
        img_form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        img_form_layout.setSpacing(6)

        self.image_name_edit = QLineEdit()
        self.image_name_edit.setPlaceholderText("例如 Agnes / OpenAI / 自建")
        img_form_layout.addRow("名称", self.image_name_edit)
        self.image_api_url_edit = QLineEdit()
        self.image_api_url_edit.setPlaceholderText("例如 https://apihub.agnes-ai.com/v1")
        img_form_layout.addRow("Base URL", self.image_api_url_edit)
        img_key_row = QHBoxLayout()
        self.image_api_key_edit = QLineEdit()
        self.image_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.image_api_key_edit.setPlaceholderText("sk-...")
        img_key_row.addWidget(self.image_api_key_edit, 1)
        self.btn_toggle_image_key = QPushButton("👁")
        self.btn_toggle_image_key.setFixedWidth(36)
        self.btn_toggle_image_key.setCheckable(True)
        self.btn_toggle_image_key.toggled.connect(self._on_toggle_image_key)
        img_key_row.addWidget(self.btn_toggle_image_key)
        img_form_layout.addRow("API Key", img_key_row)
        model_row2 = QHBoxLayout()
        self.image_model_combo = QComboBox()
        self.image_model_combo.setEditable(True)
        self.image_model_combo.setToolTip("下拉选已拉取的模型，或自己输入新模型名")
        model_row2.addWidget(self.image_model_combo, 1)
        self.btn_fetch_image_models = QPushButton("🔄 拉取")
        self.btn_fetch_image_models.setToolTip("从当前 Base URL + API Key 拉模型列表")
        self.btn_fetch_image_models.clicked.connect(self._on_fetch_image_models)
        model_row2.addWidget(self.btn_fetch_image_models)
        img_form_layout.addRow("Model", model_row2)
        self.image_resolution_combo = QComboBox()
        for r in ("1K", "2K", "4K"):
            self.image_resolution_combo.addItem(r + ("（推荐）" if r == "2K" else ""))
        img_form_layout.addRow("清晰度", self.image_resolution_combo)
        self.image_ratio_combo = QComboBox()
        for r in ("1:1", "16:9", "9:16", "4:3", "3:4"):
            self.image_ratio_combo.addItem(r)
        img_form_layout.addRow("宽高比", self.image_ratio_combo)
        self.image_timeout_spin = QSpinBox()
        # v0.7.7 重打 21：user 反馈"600 秒超时限制要去掉"，
        # 上限从 7200（2 小时）拉到 86400（1 天），让创维这种慢 provider 能跑长 prompt
        self.image_timeout_spin.setRange(30, 86400)
        self.image_timeout_spin.setSuffix(" 秒")
        self.image_timeout_spin.setToolTip("单张生图 API 超时（秒）")
        img_form_layout.addRow("超时", self.image_timeout_spin)
        layout.addLayout(img_form_layout)

        for w in (
            self.image_name_edit, self.image_api_url_edit, self.image_api_key_edit,
        ):
            w.editingFinished.connect(self._commit_image_form_to_data)
        self.image_model_combo.currentTextChanged.connect(self._commit_image_form_to_data)
        self.image_resolution_combo.currentTextChanged.connect(self._commit_image_form_to_data)
        self.image_ratio_combo.currentTextChanged.connect(self._commit_image_form_to_data)
        self.image_timeout_spin.valueChanged.connect(self._commit_image_form_to_data)
        return widget

    def _build_image_host_section(self) -> "QVBoxLayout":
        """v0.7.8.47：构造"☁ 图床 API (imgbb)"独立 section。

        用于把本地资产图上传成公网 URL，触发 API 链路的"参考生视频"模式
        （agnes image 字段）。单一 key（imgbb 免费 key 即可），独立于视频 API 多 config。
        """
        section = QVBoxLayout()
        section.setContentsMargins(0, 0, 0, 0)
        section.setSpacing(6)

        title_label = QLabel("☁ 图床 API (imgbb)")
        title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #6366f1;")
        section.addWidget(title_label)

        body = QHBoxLayout()
        body.setSpacing(8)

        # API Key 输入（Password 模式 + 👁 切换）
        self._image_host_key_edit = QLineEdit()
        self._image_host_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self._image_host_key_edit.setPlaceholderText("imgbb API key")
        self._image_host_key_edit.setToolTip(
            "imgbb 图床 API key。\n"
            "申请地址：https://api.imgbb.com/ （注册后 Get API key 即可，免费）\n"
            "用途：API 链路『参考生视频』模式时，把本地资产图上传到 imgbb 拿公网 URL，"
            "塞进 agnes 视频 API 的 image 字段。"
        )
        body.addWidget(self._image_host_key_edit, 1)

        self._btn_toggle_image_host_key = QPushButton("👁")
        self._btn_toggle_image_host_key.setFixedWidth(36)
        self._btn_toggle_image_host_key.setCheckable(True)
        self._btn_toggle_image_host_key.setToolTip("显示/隐藏 API Key")
        self._btn_toggle_image_host_key.toggled.connect(self._on_toggle_image_host_key)
        body.addWidget(self._btn_toggle_image_host_key)

        # 测试连接按钮
        self._btn_test_image_host = QPushButton("🔌 测试")
        self._btn_test_image_host.setToolTip("上传 1x1 透明 PNG 测试 imgbb key 是否可用")
        self._btn_test_image_host.clicked.connect(self._on_test_image_host)
        body.addWidget(self._btn_test_image_host)

        section.addLayout(body)

        return section

    def _on_toggle_image_host_key(self, checked: bool) -> None:
        """v0.7.8.47：👁 切换 API Key 显示/隐藏。"""
        self._image_host_key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _load_image_host_form(self) -> None:
        """v0.7.8.47：启动时从 raw 读取 image_host_api_key 填到 UI。

        硬约束：user 自己的 key 存 config/hermes_api.json 顶层 image_host_api_key 字段，
        绝不写进代码。raw 缺字段时 UI 留空（不兜底）。
        """
        self._image_host_key_edit.setText(str(self._raw.get("image_host_api_key", "") or ""))

    def _on_test_image_host(self) -> None:
        """v0.7.8.47：测试 imgbb API key 是否可用。"""
        key = self._image_host_key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "提示", "请先填 imgbb API key 再测试")
            return
        from core.generators import _upload_to_imgbb
        from pathlib import Path as _P
        import base64 as _b64
        # 1x1 透明 PNG（89 字节）
        tiny_png_b64 = (
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgAAIAAAUAAen63NgAAAAASUVORK5CYII="
        )
        tmp_path = _P.cwd() / "_imgbb_test_tmp.png"
        try:
            tmp_path.write_bytes(_b64.b64decode(tiny_png_b64))
            url = _upload_to_imgbb(tmp_path, key)
            QMessageBox.information(
                self, "测试成功",
                f"imgbb API key 可用 ✅\n\n返回 URL：\n{url}"
            )
        except Exception as e:
            QMessageBox.critical(self, "测试失败", f"imgbb API key 不可用 ❌\n\n{e}")
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except Exception:
                pass

    def _build_video_api_form_widget(self) -> "QWidget":
        """v0.7.8.38：构造视频 API 段右侧的 form widget。
        仿 _build_image_form_widget 结构（name / base_url / api_key / model / ratio / duration / resolution / timeout）。
        """
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        self.video_api_form_title = QLabel("")
        self.video_api_form_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(self.video_api_form_title)

        vform = QFormLayout()
        vform.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        vform.setSpacing(6)

        self.video_api_name_edit = QLineEdit()
        self.video_api_name_edit.setPlaceholderText("例如 创维 / Agnes / OpenAI / 自建")
        vform.addRow("名称", self.video_api_name_edit)
        self.video_api_base_url_edit = QLineEdit()
        self.video_api_base_url_edit.setPlaceholderText("例如 https://chuangwei.cyou/v1")
        vform.addRow("Base URL", self.video_api_base_url_edit)
        vkey_row = QHBoxLayout()
        self.video_api_key_edit = QLineEdit()
        self.video_api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.video_api_key_edit.setPlaceholderText("sk-...")
        vkey_row.addWidget(self.video_api_key_edit, 1)
        self.btn_toggle_video_api_key = QPushButton("👁")
        self.btn_toggle_video_api_key.setFixedWidth(36)
        self.btn_toggle_video_api_key.setCheckable(True)
        self.btn_toggle_video_api_key.toggled.connect(self._on_toggle_video_api_key)
        vkey_row.addWidget(self.btn_toggle_video_api_key)
        vform.addRow("API Key", vkey_row)
        model_row3 = QHBoxLayout()
        self.video_api_model_combo = QComboBox()
        self.video_api_model_combo.setEditable(True)
        self.video_api_model_combo.setToolTip("下拉选已拉取的模型，或自己输入新模型名")
        model_row3.addWidget(self.video_api_model_combo, 1)
        self.btn_fetch_video_api_models = QPushButton("🔄 拉取")
        self.btn_fetch_video_api_models.setToolTip("从当前 Base URL + API Key 拉视频模型列表")
        self.btn_fetch_video_api_models.clicked.connect(self._on_fetch_video_api_models)
        model_row3.addWidget(self.btn_fetch_video_api_models)
        vform.addRow("Model", model_row3)
        # v0.7.8.38.2【下放硬约束】：ratio / duration / resolution **不**在 settings
        # 页面里配置，完全由"生视频界面"决定。每次生视频时按用户当时选的来。
        # timeout（API 请求超时）保留在 settings
        self.video_api_timeout_spin = QSpinBox()
        self.video_api_timeout_spin.setRange(30, 86400)
        self.video_api_timeout_spin.setSuffix(" 秒")
        self.video_api_timeout_spin.setToolTip("单条视频 API 超时（秒）")
        vform.addRow("超时", self.video_api_timeout_spin)
        layout.addLayout(vform)

        for w in (
            self.video_api_name_edit, self.video_api_base_url_edit, self.video_api_key_edit,
        ):
            w.editingFinished.connect(self._commit_video_api_form_to_data)
        self.video_api_model_combo.currentTextChanged.connect(self._commit_video_api_form_to_data)
        # v0.7.8.38.2【下放硬约束】：ratio / duration / resolution **不**在 settings 配，
        # 所以没有对应控件，也就不需要 connect 提交信号。
        self.video_api_timeout_spin.valueChanged.connect(self._commit_video_api_form_to_data)
        return widget

    def _refresh_list(self) -> None:
        """把 self._data['configs'] 渲染到列表。

        v0.7.7 重打 17：上下布局后没有 right_stack 了，
        currentRowChanged 仍触发 _on_row_changed 加载 form 即可。
        """
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for c in self._data["configs"]:
            marker = "● " if c.get("id") == self._active_id else "  "
            item = QListWidgetItem(f"{marker}{c.get('name', c.get('id', '?'))}")
            item.setData(Qt.ItemDataRole.UserRole, c.get("id", ""))
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)
        if 0 <= self._current_idx < self.list_widget.count():
            self.list_widget.setCurrentRow(self._current_idx)
        self._update_activate_button()

    def _update_activate_button(self) -> None:
        """当前选中是否就是 active，决定按钮是否可用。"""
        if not (0 <= self._current_idx < len(self._data["configs"])):
            self.btn_activate.setEnabled(False)
            return
        cur_id = self._data["configs"][self._current_idx].get("id", "")
        self.btn_activate.setEnabled(cur_id != self._active_id)

    def _on_row_changed(self, row: int) -> None:
        """切列表项前，先把旧表单刷回 _data，再加载新的。"""
        self._commit_form_to_data()
        self._load_form_for_index(row)

    def _load_form_for_index(self, idx: int) -> None:
        self._current_idx = idx
        if not (0 <= idx < len(self._data["configs"])):
            self.form_title.setText("（无配置）")
            for w in (
                self.name_edit, self.provider_edit, self.model_edit,
                self.base_url_edit, self.api_key_edit,
            ):
                w.blockSignals(True)
                w.clear()
                w.setEnabled(False)
                w.blockSignals(False)
            self.btn_activate.setEnabled(False)
            return
        c = self._data["configs"][idx]
        self.form_title.setText(
            f"{c.get('name', '?')}  ({c.get('id', '?')})"
            + ("  · 当前激活" if c.get("id") == self._active_id else "")
        )
        for w, key in (
            (self.name_edit, "name"),
            (self.provider_edit, "provider"),
            (self.model_edit, "model"),
            (self.base_url_edit, "base_url"),
            (self.api_key_edit, "api_key"),
        ):
            w.blockSignals(True)
            # v0.7.8.10：QComboBox(setEditable=True) 用 setEditText，QLineEdit 用 setText
            if isinstance(w, QComboBox):
                w.setEditText(str(c.get(key, "")))
            else:
                w.setText(str(c.get(key, "")))
            w.setEnabled(True)
            w.blockSignals(False)
        self._update_activate_button()

    def _commit_form_to_data(self) -> None:
        """把当前表单内容写回 self._data。"""
        if getattr(self, "_loading", False):
            return
        if not (0 <= self._current_idx < len(self._data["configs"])):
            return
        c = self._data["configs"][self._current_idx]
        c["name"] = self.name_edit.text().strip()
        c["provider"] = self.provider_edit.text().strip()
        # v0.7.8.10：QComboBox(setEditable=True) 用 currentText() 代替 text()
        c["model"] = self.model_edit.currentText().strip()
        c["base_url"] = self.base_url_edit.text().strip()
        c["api_key"] = self.api_key_edit.text()

    def _on_toggle_key(self, checked: bool) -> None:
        self.api_key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _on_toggle_image_key(self, checked: bool) -> None:
        """v0.7.7：生图 API Key 显示/隐藏切换。"""
        self.image_api_key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    @Slot()
    def _on_fetch_image_models(self) -> None:
        """v0.7.7：从当前**活跃生图 config** 的 base_url/api_key 拉模型列表。

        复刻自老 software D:\\剧本分镜助手\\templates\\index.html:1912-1945
        `refreshModelList` —— 调 GET {apiUrl}/v1/models (OpenAI 兼容)。
        拉到的模型写到当前活跃 config 的 `saved_models` 历史列表（仅该 config 受益），
        失败时兜底 1 个 gpt-image-2-reverse（老 software 默认）+ 历史保存列表。
        """
        from core.image_models import (
            fetch_image_models, merge_with_image_fallback,
        )
        # 先把当前表单刷回 _image_data，再读活跃 config
        self._commit_image_form_to_data()
        if not (0 <= self._image_current_idx < len(self._image_data["configs"])):
            QMessageBox.warning(self, "无法拉取", "请先在生图 API 列表里选一个 config。")
            return
        cur_cfg = self._image_data["configs"][self._image_current_idx]
        base_url = str(cur_cfg.get("base_url", "") or "").strip()
        api_key = str(cur_cfg.get("api_key", "") or "").strip()
        if not base_url or not api_key:
            QMessageBox.warning(
                self, "无法拉取",
                "请先填写生图 API 的 Base URL 和 API Key。\n\n"
                "（拉取会调 {base_url}/v1/models）",
            )
            return
        self.btn_fetch_image_models.setEnabled(False)
        self.btn_fetch_image_models.setText("⏳ 拉取中…")
        try:
            QApplication.processEvents()
            try:
                fetched = fetch_image_models(base_url, api_key, timeout=15.0)
            except Exception as e:
                saved = list(cur_cfg.get("saved_models", []) or [])
                merged = merge_with_image_fallback(fetched=None, saved=saved)
                cur_cfg["saved_models"] = merged
                QMessageBox.warning(
                    self, "拉取失败",
                    f"拉取生图模型列表失败：\n{e}\n\n"
                    f"已用兜底 1 个 gpt-image-2-reverse + 历史保存列表（{len(merged)} 个）：\n"
                    + "、".join(merged[:8]) + ("..." if len(merged) > 8 else ""),
                )
                return
            saved = list(cur_cfg.get("saved_models", []) or [])
            merged = merge_with_image_fallback(fetched=fetched, saved=saved)
            cur_cfg["saved_models"] = merged
            # 刷新当前下拉框
            cur_sel = self.image_model_combo.currentText()
            self.image_model_combo.blockSignals(True)
            self.image_model_combo.clear()
            for m in merged:
                self.image_model_combo.addItem(m)
            if cur_sel and cur_sel in merged:
                self.image_model_combo.setCurrentText(cur_sel)
            elif cur_cfg.get("model") in merged:
                self.image_model_combo.setCurrentText(cur_cfg.get("model", ""))
            else:
                self.image_model_combo.setCurrentIndex(0)
            self.image_model_combo.blockSignals(False)
            preview = "、".join(merged[:8]) + ("..." if len(merged) > 8 else "")
            QMessageBox.information(
                self, "拉取成功",
                f"✓ 拉到 {len(fetched)} 个生图模型\n"
                f"+ 历史 {len(saved)} 个 + 兜底 1 个 gpt-image-2-reverse = {len(merged)} 个：\n"
                f"{preview}\n\n"
                f"点击【保存】后写入 hermes_api.json。",
            )
        finally:
            self.btn_fetch_image_models.setEnabled(True)
            self.btn_fetch_image_models.setText("🔄 拉取")

    def _on_fetch_models(self) -> None:
        """v0.6.21 + v0.7.8.11：拉取模型列表（从当前表单的 base_url + api_key）。

        复刻自原软件 D:\\剧本分镜助手\\server.py:1581-1603 `POST /api/list-models`。
        拉取结果写到 `self._raw["dreamina_models"]`，所有 config 共用。

        v0.7.8.11【无兜底硬约束】：
        - 拉取失败：直接报错弹窗，**不**弹"已用兜底 4 个 seedance"
        - 下拉项 = 拉取到的 + 用户保存过的历史，**不**拼 4 个 seedance
        - 用户当前选中的 model **永远保留**（即使不在拉取列表里也用 setEditText 显示），
          **不**用 setCurrentIndex(0) 覆盖成列表第一个
        """
        from core.dreamina_models import DreaminaModelsError, fetch_models
        # 先把当前表单刷回 _data（拿到最新的 base_url/api_key）
        self._commit_form_to_data()
        if not (0 <= self._current_idx < len(self._data["configs"])):
            return
        c = self._data["configs"][self._current_idx]
        base_url = c.get("base_url", "").strip()
        api_key = c.get("api_key", "").strip()
        if not base_url or not api_key:
            QMessageBox.warning(
                self, "无法拉取",
                "请先填写 Base URL 和 API Key。\n\n（拉取会调 {base_url}/v1/models）",
            )
            return
        # 关掉按钮 + 改文案（防双击）
        self.btn_fetch_models.setEnabled(False)
        self.btn_fetch_models.setText("⏳ 拉取中…")
        try:
            QApplication.processEvents()
            try:
                fetched = fetch_models(base_url, api_key, timeout=15.0)
            except DreaminaModelsError as e:
                # v0.7.8.11【无兜底】：失败直接报错，不弹"兜底"对话框
                QMessageBox.warning(
                    self, "拉取失败",
                    f"拉取模型列表失败：\n{e}\n\n"
                    f"（请检查 Base URL 和 API Key 是否正确）",
                )
                log.warning("fetch_models failed: %s", e)
                return
            # v0.7.8.11【无兜底】：下拉项 = fetched + saved 去重，**不**拼 4 个 seedance
            saved = self._raw.get("dreamina_models", []) or []
            seen: set = set()
            merged: list[str] = []
            for m in (fetched + saved):
                if m and m not in seen:
                    seen.add(m)
                    merged.append(m)
            self._raw["dreamina_models"] = merged
            # 填下拉框 + **永远保留**用户当前选中的 model
            cur_sel = self.model_edit.currentText().strip()
            self.model_edit.blockSignals(True)
            self.model_edit.clear()
            for m in merged:
                self.model_edit.addItem(m)
            # v0.7.8.11【无兜底】：不管 cur_sel 是否在 merged，都 setEditText 保留
            # ——绝不能**用 setCurrentIndex(0) 覆盖
            if cur_sel:
                self.model_edit.setEditText(cur_sel)
            self.model_edit.blockSignals(False)
            preview = "、".join(merged[:8]) + ("..." if len(merged) > 8 else "")
            QMessageBox.information(
                self, "拉取成功",
                f"✓ 拉到 {len(fetched)} 个模型\n"
                f"+ 历史 {len(saved)} 个 = {len(merged)} 个：\n"
                f"{preview}\n\n"
                f"（下拉项不包含任何兜底；选什么用什么）\n"
                f"点击【保存】后写入 hermes_api.json。",
            )
            log.info("fetch_models ok: %d models", len(fetched))
        finally:
            self.btn_fetch_models.setEnabled(True)
            self.btn_fetch_models.setText("🔄 拉取")

    def _on_activate_clicked(self) -> None:
        if not (0 <= self._current_idx < len(self._data["configs"])):
            return
        self._commit_form_to_data()
        new_id = self._data["configs"][self._current_idx].get("id", "")
        if new_id == self._active_id:
            return
        self._active_id = new_id
        self._data["active"] = new_id
        self._refresh_list()

    @Slot()
    def _on_add_clicked(self) -> None:
        """v0.6.24：新增一个空白 API 配置（id 自动生成）。"""
        import uuid
        new_cfg = {
            "id": uuid.uuid4().hex[:8],
            "name": "新配置",
            "provider": "custom",
            "model": "",
            "base_url": "",
            "api_key": "",
        }
        self._commit_form_to_data()  # 提交当前表单再追加，避免丢改动
        self._data["configs"].append(new_cfg)
        self._current_idx = len(self._data["configs"]) - 1
        self._refresh_list()
        self._load_form_for_index(self._current_idx)
        self.name_edit.setFocus()
        self.name_edit.selectAll()

    @Slot()
    def _on_duplicate_clicked(self) -> None:
        """v0.6.24：复制当前选中的 config（追加到末尾，name 加 '副本' 后缀）。"""
        if not (0 <= self._current_idx < len(self._data["configs"])):
            return
        self._commit_form_to_data()
        import copy, uuid
        cur = self._data["configs"][self._current_idx]
        new_cfg = copy.deepcopy(cur)
        new_cfg["id"] = uuid.uuid4().hex[:8]
        base_name = new_cfg.get("name", "未命名")
        if "副本" not in base_name:
            new_cfg["name"] = f"{base_name} (副本)"
        self._data["configs"].append(new_cfg)
        self._current_idx = len(self._data["configs"]) - 1
        self._refresh_list()
        self._load_form_for_index(self._current_idx)

    # ============ v0.6.25 Hermes 设置 tab handlers ============
    @Slot()
    def _on_browse_hermes_exe(self) -> None:
        """v0.6.25：浏览 hermes.exe 路径。"""
        start = self.hermes_exe_edit.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 hermes.exe", start,
            "可执行文件 (*.exe);;所有文件 (*.*)",
        )
        if path:
            self.hermes_exe_edit.setText(path)

    @Slot()
    def _on_browse_outputs_dir(self) -> None:
        """v0.6.25：浏览 outputs 目录。"""
        start = self.outputs_dir_edit.text().strip() or str(Path.cwd())
        path = QFileDialog.getExistingDirectory(
            self, "选择 outputs 目录", start,
        )
        if path:
            self.outputs_dir_edit.setText(path)

    @Slot()
    def _on_browse_hermes_home(self) -> None:
        """v0.6.25：浏览 HERMES_HOME 目录（profiles/ 的父目录）。"""
        start = self.hermes_home_edit.text().strip() or str(Path.home())
        path = QFileDialog.getExistingDirectory(
            self, "选择 HERMES_HOME 目录（含 profiles/ 子目录）", start,
        )
        if path:
            self.hermes_home_edit.setText(path)

    @Slot()
    def _on_detect_hermes_home(self) -> None:
        """v0.6.25：自动检测 HERMES_HOME。

        复刻原软件 server.py:3040-3075 `_find_profiles_base` 的检测顺序：
        1) config.hermes_home 显式设置（v0.6.25 新加）
        2) ~/.hermes 存在
        3) hermes_exe.parent.parent 含 profiles/
        4) 临时目录 MSI* 模式（含 profiles/<name>/config.yaml）
        5) HERMES_HOME env var（last resort）
        """
        candidates: list[tuple[str, str]] = []  # (path, source)
        # 1) config 显式
        cfg_home = self.hermes_home_edit.text().strip()
        if cfg_home and Path(cfg_home).is_dir():
            if (Path(cfg_home) / "profiles").is_dir():
                candidates.append((cfg_home, "config.hermes_home + profiles/"))
        # 2) ~/.hermes
        home_dot = Path.home() / ".hermes"
        if home_dot.is_dir() and (home_dot / "profiles").is_dir():
            candidates.append((str(home_dot), "~/.hermes + profiles/"))
        # 3) hermes_exe.parent.parent
        exe_str = self.hermes_exe_edit.text().strip()
        if exe_str:
            exe = Path(exe_str)
            if exe.exists():
                pp = exe.parent.parent
                if (pp / "profiles").is_dir():
                    candidates.append((str(pp), f"hermes_exe.parent.parent ({pp})"))
        # 4) 临时目录 MSI*
        import tempfile
        for d in Path(tempfile.gettempdir()).iterdir():
            if d.is_dir() and d.name.startswith("MSI"):
                if (d / "profiles").is_dir():
                    candidates.append((str(d), f"temp MSI ({d.name})"))
        # 5) HERMES_HOME env
        import os
        env_home = os.environ.get("HERMES_HOME", "")
        if env_home and Path(env_home).is_dir():
            if (Path(env_home) / "profiles").is_dir():
                candidates.append((env_home, "$HERMES_HOME env"))

        if not candidates:
            QMessageBox.warning(
                self, "未找到", "未检测到含 profiles/ 的 HERMES_HOME，请手动指定。",
            )
            return
        if len(candidates) == 1:
            self.hermes_home_edit.setText(candidates[0][0])
            QMessageBox.information(
                self, "检测到", f"找到: {candidates[0][1]}\n已填入。",
            )
            return
        # 多个：列给用户选
        msg = "找到多个候选，请选一个：\n\n" + "\n".join(
            f"  {i + 1}. {c[0]}\n     来源: {c[1]}" for i, c in enumerate(candidates)
        )
        ret = QMessageBox.question(
            self, "多个候选", msg + "\n是否用第 1 个？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            self.hermes_home_edit.setText(candidates[0][0])

    @Slot()
    def _on_delete_clicked(self) -> None:
        """v0.6.24：删除当前选中的 config。"""
        if not (0 <= self._current_idx < len(self._data["configs"])):
            return
        if len(self._data["configs"]) <= 1:
            QMessageBox.warning(
                self, "提示", "至少保留一个配置，无法删除最后一个。",
            )
            return
        cur = self._data["configs"][self._current_idx]
        cur_name = cur.get("name", cur.get("id", "?"))
        is_active = cur.get("id") == self._active_id
        warn = "（这是当前激活配置，删除后会 fallback 到第一个剩余）" if is_active else ""
        ret = QMessageBox.question(
            self, "确认删除",
            f"确定删除配置 [{cur_name}]？{warn}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        del self._data["configs"][self._current_idx]
        if is_active:
            self._active_id = self._data["configs"][0]["id"]
            self._data["active"] = self._active_id
        # 把 _current_idx 夹到合法范围
        if self._current_idx >= len(self._data["configs"]):
            self._current_idx = len(self._data["configs"]) - 1
        self._refresh_list()
        self._load_form_for_index(self._current_idx)

    def _on_save(self) -> None:
        # 1. 先把当前表单刷回 _data
        self._commit_form_to_data()
        # 2. 校验：active config 必填字段非空（**不**遍历所有 config —
        #    跟视频 API 行为一致：非 active 允许空,用户可同时维护
        #    多个未完成的 config;真要调用时再报错）。
        # v1.1.1【无字段硬约束】：保存时**不**检查 active config 字段是否
        # 填齐。理由:用户可能暂时不需要某个 API section(比如刚装软件还没
        # 配视频 API,只想配 LLM),这时不能因为视频 API 缺 api_key 就
        # 拒绝保存 LLM 设置。校验下放到实际调用 API 时(真要生成视频才报错)。
        active_id = self._data.get("active", "")
        if not active_id:
            QMessageBox.warning(self, "校验失败", "未选择 active 配置")
            return
        if not any(c.get("id") == self._data["active"] for c in self._data["configs"]):
            QMessageBox.warning(
                self,
                "校验失败",
                f"active='{self._data['active']}' 在 configs 里找不到对应项",
            )
            return
        # v1.1.1【下放硬约束】：视频 API active config 不再保存时校验。
        # 缺字段时直接保存,等到用户真正点"生成视频"时再弹错。
        # 生图 API 同样下放(本来就不校验)。
        # 3. 写盘：保留未编辑的字段
        new_raw = dict(self._raw)
        new_raw["configs"] = self._data["configs"]
        new_raw["active"] = self._data["active"]
        # v0.6.25 #17：Hermes 设置 tab 字段也一并写
        if hasattr(self, "hermes_exe_edit"):
            new_raw["hermes_exe"] = self.hermes_exe_edit.text().strip()
        if hasattr(self, "outputs_dir_edit"):
            new_raw["outputs_dir"] = self.outputs_dir_edit.text().strip() or "outputs"
        if hasattr(self, "hermes_home_edit"):
            new_raw["hermes_home"] = self.hermes_home_edit.text().strip()
        if hasattr(self, "timeout_spin"):
            new_raw["timeout_seconds"] = int(self.timeout_spin.value())
        if hasattr(self, "profile_edits"):
            # v0.6.25 #17 bug fix：只更新原 config 里已有的 key，
            # 不要因为表单有 video 就插入空 "video" 字段破坏老 profiles 结构
            profiles = dict(new_raw.get("profiles") or {})
            for key, edit in self.profile_edits.items():
                if key in profiles:
                    profiles[key] = edit.text().strip()
            new_raw["profiles"] = profiles
        # v0.7.7：生图 API 多 config 模式（仿 LLM `configs/active` 结构）
        # 1) 写新结构 image_configs + active_image_config
        # 2) 删老结构顶层 image_api_url / image_api_key / image_model / image_resolution /
        #    image_ratio / image_timeout / image_saved_models（迁移到 image_configs[0] 后就没用了）
        if hasattr(self, "image_list_widget"):
            self._commit_image_form_to_data()  # 提交当前 form 改动
            new_raw["image_configs"] = self._image_data["configs"]
            new_raw["active_image_config"] = self._image_data["active"]
            # 删老字段
            for legacy_k in (
                "image_api_url", "image_api_key", "image_model",
                "image_resolution", "image_ratio", "image_timeout",
                "image_saved_models", "image_name",
            ):
                new_raw.pop(legacy_k, None)
        # v0.7.8.38：视频 API 多 config 模式 + dreamina.exe 路径
        if hasattr(self, "video_api_list_widget"):
            self._commit_video_api_form_to_data()  # 提交当前 form 改动
            # v0.7.8.38.2【下放硬约束】：从每个 config 里清理掉 ratio / duration /
            # resolution（settings 永远不写它们，遗留值也得清掉，免得下次 reload
            # 又被读回来）
            # v0.7.8.42【不保存硬约束】：saved_models **完全不写盘**，
            # 拉取时只 fill 内存下拉框，关闭/重启后丢弃
            for c in self._video_api_data["configs"]:
                for k in ("ratio", "duration", "resolution", "saved_models"):
                    c.pop(k, None)
            new_raw["video_api_configs"] = self._video_api_data["configs"]
            new_raw["active_video_api_config"] = self._video_api_data["active"]
            # 删老字段（迁移到 video_api_configs[0] 后就没用了）
            for legacy_k in (
                "video_api_url", "video_api_key", "video_api_model",
                # v0.7.8.38.2【下放硬约束】：ratio / duration / resolution 老字段
                # 也清掉，它们在生视频界面已经独立管理。
                "video_api_ratio", "video_api_duration", "video_api_resolution",
                "video_api_timeout", "video_api_saved_models",
            ):
                new_raw.pop(legacy_k, None)
        # v0.7.8.38:dreamina.exe 路径（web 视频生成用）
        if hasattr(self, "dreamina_exe_edit"):
            new_raw["dreamina_exe"] = self.dreamina_exe_edit.text().strip()
        # v0.7.8.47：图床 API key（imgbb）写回 raw——user 自己填，**不**写进代码
        if hasattr(self, "_image_host_key_edit"):
            new_raw["image_host_api_key"] = self._image_host_key_edit.text().strip()
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(new_raw, f, ensure_ascii=False, indent=2)
        except OSError as e:
            QMessageBox.critical(self, "保存失败", f"写盘失败: {e}")
            log.exception("settings: write json failed")
            return
        log.info("settings: saved %s", self._path)

        # v0.7.8.3:同步更新内存中的 self._raw。否则重开 SettingsDialog 时
        # __init__ 用 _raw 重新初始化 _data,会看到"老 model/老 base_url"
        # (用户反馈:"换模型后点保存,再进设置还是更换前的模型")。
        # new_raw 是新写盘的完整内容,直接替换 _raw 引用。
        self._raw = new_raw

        # 4. 同步到 hermes profiles（用户主动行为，不是后台偷偷做）
        # 用户点"保存" = 明确同意把 active 配置写到 hermes 的 profiles/<name>/config.yaml
        # hermes 启动时只读 profile 的 config.yaml，不读 hermes_api.json
        # 所以**这是用户必须做的步骤**，不是可选项
        self._apply_to_hermes_profiles(new_raw)

        self.accept()

    def _apply_to_hermes_profiles(self, raw: Dict[str, Any]) -> None:
        """把 active 配置写入 hermes 每个业务 profile（asset/storyboard/video_prompt）。

        这步是必要的：hermes 启动时只读 profile 的 config.yaml，**不会**回看
        hermes_api.json。所以用户在我们的设置面板改了 active，必须同步到 profile。
        """
        try:
            # 用 reload 拿最新的 in-memory Config（包含新保存的 active）
            from core.config import Config  # 局部 import：避免循环
            Config.reload(self._path)
            cfg = Config.get()
            profiles_map: Dict[str, str] = cfg.profiles  # {"asset": "asset-designer", ...}
            active = cfg.active_config
            log.info(
                "settings: 准备同步 active='%s' 到 %d 个 profile: %s",
                active.get("id"), len(profiles_map), list(profiles_map.values()),
            )
            ok = []
            failed = []
            for key, prof_name in profiles_map.items():
                try:
                    cfg.inject_api_to_profile(prof_name)
                    ok.append(prof_name)
                except Exception as e:
                    log.warning("settings: 注入 %s 失败: %s", prof_name, e)
                    failed.append((prof_name, str(e)))
            if failed:
                QMessageBox.warning(
                    self,
                    "部分同步失败",
                    "已保存到 hermes_api.json，但同步到 hermes profile 失败：\n"
                    + "\n".join(f"  - {n}: {e}" for n, e in failed)
                    + "\n\nhermes 仍会调旧模型/旧 key。\n"
                    "请检查日志或手动编辑 profiles/<name>/config.yaml。",
                )
            else:
                log.info("settings: 同步成功: %s", ok)
        except Exception as e:
            log.exception("settings: 同步 hermes profiles 失败")
            QMessageBox.critical(
                self,
                "同步失败",
                f"已保存到 hermes_api.json，但同步到 hermes profile 整体失败：{e}\n\n"
                f"hermes 仍会调旧模型/旧 key。\n"
                f"请检查日志或手动编辑 profiles/<name>/config.yaml。",
            )

    # ---------- 测试辅助 ----------

    def get_active_id(self) -> str:
        return self._active_id

    def get_config(self, idx: int) -> Dict[str, Any]:
        return dict(self._data["configs"][idx])

    # ============ v0.7.7：生图 API 多 config 辅助方法（仿 LLM）============

    def _init_image_data(self) -> Dict[str, Any]:
        """从 raw 构造 image_data；老结构自动迁移到 image_configs[0]。"""
        # 优先用新结构 image_configs + active_image_config
        if self._raw.get("image_configs"):
            return {
                "configs": [dict(c) for c in self._raw.get("image_configs", [])],
                "active": self._raw.get("active_image_config", ""),
            }
        # 老结构：顶层 image_api_url 等字段
        legacy_url = str(self._raw.get("image_api_url", "") or "").rstrip("/")
        legacy_key = str(self._raw.get("image_api_key", "") or "")
        if not legacy_url or not legacy_key:
            return {"configs": [], "active": ""}
        cid = "default"
        cfg = {
            "id": cid,
            "name": "默认生图 API",
            "base_url": legacy_url,
            "api_key": legacy_key,
            "model": str(self._raw.get("image_model", "gpt-image-2-reverse") or "gpt-image-2-reverse"),
            "resolution": str(self._raw.get("image_resolution", "2K") or "2K"),
            "ratio": str(self._raw.get("image_ratio", "1:1") or "1:1"),
            "timeout": int(self._raw.get("image_timeout", 600) or 600),
            "saved_models": list(self._raw.get("image_saved_models", []) or []),
        }
        return {"configs": [cfg], "active": cid}

    def _image_resolve_initial_index(self) -> int:
        """默认选中当前 active。"""
        for i, c in enumerate(self._image_data["configs"]):
            if c.get("id") == self._image_active_id:
                return i
        return 0 if self._image_data["configs"] else -1

    def _refresh_image_list(self) -> None:
        """重绘生图 config 列表（激活的项标 ●）。

        v0.7.7 重打 17：上下布局后没有 right_stack 了，
        currentRowChanged 仍触发 _on_image_row_changed 加载 form 即可。
        """
        if not hasattr(self, "image_list_widget"):
            return
        self.image_list_widget.blockSignals(True)
        self.image_list_widget.clear()
        for c in self._image_data["configs"]:
            mark = "● " if c.get("id") == self._image_data["active"] else "   "
            name = c.get("name") or c.get("id") or "(未命名)"
            self.image_list_widget.addItem(f"{mark}{name}")
        self.image_list_widget.blockSignals(False)
        if 0 <= self._image_current_idx < self.image_list_widget.count():
            self.image_list_widget.setCurrentRow(self._image_current_idx)
        self._refresh_image_form_title()

    def _refresh_image_form_title(self) -> None:
        if not hasattr(self, "image_form_title"):
            return
        if not (0 <= self._image_current_idx < len(self._image_data["configs"])):
            self.image_form_title.setText("（无配置）")
            return
        c = self._image_data["configs"][self._image_current_idx]
        is_active = " [激活]" if c.get("id") == self._image_data["active"] else ""
        self.image_form_title.setText(f"生图 config {self._image_current_idx + 1}{is_active}")

    def _load_image_form_for_index(self, idx: int) -> None:
        """把 image_data[idx] 的字段刷到 form。"""
        self._image_current_idx = idx
        if not hasattr(self, "image_name_edit"):
            return
        if not (0 <= idx < len(self._image_data["configs"])):
            for w in (
                self.image_name_edit, self.image_api_url_edit, self.image_api_key_edit,
            ):
                w.blockSignals(True)
                w.clear()
                w.blockSignals(False)
            self.image_model_combo.blockSignals(True)
            self.image_model_combo.clear()
            self.image_model_combo.blockSignals(False)
            return
        c = self._image_data["configs"][idx]
        # name / base_url / api_key
        for w, key in (
            (self.image_name_edit, "name"),
            (self.image_api_url_edit, "base_url"),
            (self.image_api_key_edit, "api_key"),
        ):
            w.blockSignals(True)
            w.setText(str(c.get(key, "") or ""))
            w.blockSignals(False)
        # model combo: populate saved_models + 当前 model
        self.image_model_combo.blockSignals(True)
        self.image_model_combo.clear()
        saved = list(c.get("saved_models", []) or [])
        model = str(c.get("model", "") or "")
        merged = []
        seen = set()
        for m in (saved + ([model] if model else [])):
            if m and m not in seen:
                seen.add(m)
                merged.append(m)
        for m in merged:
            self.image_model_combo.addItem(m)
        if model:
            self.image_model_combo.setCurrentText(model)
        elif merged:
            self.image_model_combo.setCurrentIndex(0)
        self.image_model_combo.blockSignals(False)
        # resolution
        res = str(c.get("resolution", "2K") or "2K")
        self.image_resolution_combo.blockSignals(True)
        idx_res = self.image_resolution_combo.findText(res, Qt.MatchFlag.MatchStartsWith)
        if idx_res >= 0:
            self.image_resolution_combo.setCurrentIndex(idx_res)
        self.image_resolution_combo.blockSignals(False)
        # ratio
        ratio = str(c.get("ratio", "1:1") or "1:1")
        self.image_ratio_combo.blockSignals(True)
        idx_ratio = self.image_ratio_combo.findText(ratio)
        if idx_ratio >= 0:
            self.image_ratio_combo.setCurrentIndex(idx_ratio)
        self.image_ratio_combo.blockSignals(False)
        # timeout
        self.image_timeout_spin.blockSignals(True)
        self.image_timeout_spin.setValue(int(c.get("timeout", 600) or 600))
        self.image_timeout_spin.blockSignals(False)
        self._refresh_image_form_title()

    def _commit_image_form_to_data(self) -> None:
        """把 form 当前值回写到 _image_data[_image_current_idx]。"""
        if getattr(self, "_loading", False):
            return
        if not (0 <= self._image_current_idx < len(self._image_data["configs"])):
            return
        c = self._image_data["configs"][self._image_current_idx]
        c["name"] = self.image_name_edit.text().strip()
        c["base_url"] = self.image_api_url_edit.text().strip()
        c["api_key"] = self.image_api_key_edit.text()
        c["model"] = self.image_model_combo.currentText().strip()
        res_text = self.image_resolution_combo.currentText().strip()
        c["resolution"] = res_text.replace("（推荐）", "").strip() or "2K"
        c["ratio"] = self.image_ratio_combo.currentText().strip() or "1:1"
        c["timeout"] = int(self.image_timeout_spin.value())

    def _on_image_row_changed(self, row: int) -> None:
        """切列表项前先把旧表单刷回 _image_data，再加载新的。"""
        self._commit_image_form_to_data()
        self._load_image_form_for_index(row)

    def _on_image_activate_clicked(self) -> None:
        """把当前选中的生图 config 设为 active。"""
        if not (0 <= self._image_current_idx < len(self._image_data["configs"])):
            return
        self._commit_image_form_to_data()
        self._image_data["active"] = self._image_data["configs"][self._image_current_idx]["id"]
        self._image_active_id = self._image_data["active"]
        self._refresh_image_list()

    def _on_image_add_clicked(self) -> None:
        """新增一个空白生图 config。"""
        import uuid as _uuid
        self._commit_image_form_to_data()
        new_id = _uuid.uuid4().hex[:8]
        self._image_data["configs"].append({
            "id": new_id,
            "name": f"生图 API {len(self._image_data['configs']) + 1}",
            "base_url": "",
            "api_key": "",
            "model": "gpt-image-2-reverse",
            "resolution": "2K",
            "ratio": "1:1",
            "timeout": 600,
            "saved_models": [],
        })
        self._image_current_idx = len(self._image_data["configs"]) - 1
        self._refresh_image_list()
        self._load_image_form_for_index(self._image_current_idx)

    def _on_image_duplicate_clicked(self) -> None:
        """复制当前选中的生图 config。"""
        if not (0 <= self._image_current_idx < len(self._image_data["configs"])):
            return
        import uuid as _uuid
        self._commit_image_form_to_data()
        src = dict(self._image_data["configs"][self._image_current_idx])
        src["id"] = _uuid.uuid4().hex[:8]
        src["name"] = (src.get("name") or "(未命名)") + " 副本"
        self._image_data["configs"].append(src)
        self._image_current_idx = len(self._image_data["configs"]) - 1
        self._refresh_image_list()
        self._load_image_form_for_index(self._image_current_idx)

    def _on_image_delete_clicked(self) -> None:
        """删除当前选中的生图 config（active 被删时 fallback 到第一个剩余）。"""
        if not (0 <= self._image_current_idx < len(self._image_data["configs"])):
            return
        if len(self._image_data["configs"]) <= 1:
            QMessageBox.warning(self, "无法删除", "至少保留 1 个生图 config。")
            return
        del_id = self._image_data["configs"][self._image_current_idx]["id"]
        is_active = del_id == self._image_data["active"]
        ret = QMessageBox.question(
            self, "确认删除",
            f"确定删除生图 config「{self._image_data['configs'][self._image_current_idx].get('name', del_id)}」？",
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        del self._image_data["configs"][self._image_current_idx]
        if is_active:
            self._image_active_id = self._image_data["configs"][0]["id"]
            self._image_data["active"] = self._image_active_id
        if self._image_current_idx >= len(self._image_data["configs"]):
            self._image_current_idx = len(self._image_data["configs"]) - 1
        self._refresh_image_list()
        self._load_image_form_for_index(self._image_current_idx)

    # ============ v0.7.8.38：视频 API 多 config 辅助方法（仿生图 API）============

    def _init_video_api_data(self) -> Dict[str, Any]:
        """v0.7.8.38：从 raw 构造 video_api_data；老结构自动迁移到 video_api_configs[0]。

        v0.7.8.38.1【无兜底硬约束】：所有字段（name / base_url / api_key / model /
        timeout）都从 raw 直读，**不**塞系统默认值。用户配什么用什么。
        v0.7.8.38.2【下放硬约束】：ratio / duration / resolution **不**在
        video_api_configs 里（也不读老字段），完全由"生视频界面"决定。
        v0.7.8.42【不保存硬约束】：saved_models 字段在加载时**不读**（如果有
        残留也直接清空），cfg 里**不应该**出现 saved_models。拉取时不写、
        加载时不读、迁移时不带。
        """
        if self._raw.get("video_api_configs"):
            # v0.7.8.42：清理老 saved_models 残留
            for c in self._raw.get("video_api_configs", []):
                c.pop("saved_models", None)
            return {
                "configs": [dict(c) for c in self._raw.get("video_api_configs", [])],
                "active": self._raw.get("active_video_api_config", ""),
            }
        # 老结构：顶层 video_api_url 等字段
        legacy_url = str(self._raw.get("video_api_url", "") or "").rstrip("/")
        legacy_key = str(self._raw.get("video_api_key", "") or "")
        if not legacy_url or not legacy_key:
            return {"configs": [], "active": ""}
        cid = "default"
        cfg = {
            "id": cid,
            "name": str(self._raw.get("video_api_name", "") or ""),  # 无兜底
            "base_url": legacy_url,
            "api_key": legacy_key,
            "model": str(self._raw.get("video_api_model", "") or ""),  # 无兜底
            "timeout": int(self._raw.get("video_api_timeout", 0) or 0),  # 无兜底
            # v0.7.8.38.2【下放硬约束】：ratio / duration / resolution 不进 video_api_configs
            # v0.7.8.42【不保存硬约束】：saved_models 不进 cfg
        }
        return {"configs": [cfg], "active": cid}

    def _video_api_resolve_initial_index(self) -> int:
        for i, c in enumerate(self._video_api_data["configs"]):
            if c.get("id") == self._video_api_active_id:
                return i
        return 0 if self._video_api_data["configs"] else -1

    def _refresh_video_api_list(self) -> None:
        if not hasattr(self, "video_api_list_widget"):
            return
        self.video_api_list_widget.blockSignals(True)
        self.video_api_list_widget.clear()
        for c in self._video_api_data["configs"]:
            mark = "● " if c.get("id") == self._video_api_data["active"] else "   "
            name = c.get("name") or c.get("id") or "(未命名)"
            self.video_api_list_widget.addItem(f"{mark}{name}")
        self.video_api_list_widget.blockSignals(False)
        if 0 <= self._video_api_current_idx < self.video_api_list_widget.count():
            self.video_api_list_widget.setCurrentRow(self._video_api_current_idx)
        self._refresh_video_api_form_title()

    def _refresh_video_api_form_title(self) -> None:
        if not hasattr(self, "video_api_form_title"):
            return
        if not (0 <= self._video_api_current_idx < len(self._video_api_data["configs"])):
            self.video_api_form_title.setText("（无配置）")
            return
        c = self._video_api_data["configs"][self._video_api_current_idx]
        is_active = " [激活]" if c.get("id") == self._video_api_data["active"] else ""
        self.video_api_form_title.setText(f"视频 API config {self._video_api_current_idx + 1}{is_active}")

    def _load_video_api_form_for_index(self, idx: int) -> None:
        """v0.7.8.38.1【无兜底】：从 _video_api_data[idx] 读字段填到 form。
        缺啥就空字符串/0，**不**预填默认值。
        v0.7.8.38.2【下放硬约束】：ratio / duration / resolution 不在 settings 配，
        所以 _video_api_data 也没这些字段，form 自然也没对应控件。
        v0.7.8.42【不保存硬约束】：下拉框**不**读 saved_models（v0.7.8.38.3
        之前会读 → 改成完全不读），打开 dialog 时下拉框 = 只显示 model 字段
        （用户手动填的那个），其他空。每次拉取的 fetched **只**本次 dialog 显示。
        """
        self._video_api_current_idx = idx
        if not hasattr(self, "video_api_name_edit"):
            return
        if not (0 <= idx < len(self._video_api_data["configs"])):
            for w in (
                self.video_api_name_edit, self.video_api_base_url_edit, self.video_api_key_edit,
            ):
                w.blockSignals(True)
                w.clear()
                w.blockSignals(False)
            self.video_api_model_combo.blockSignals(True)
            self.video_api_model_combo.clear()
            self.video_api_model_combo.blockSignals(False)
            return
        c = self._video_api_data["configs"][idx]
        # name / base_url / api_key
        for w, key in (
            (self.video_api_name_edit, "name"),
            (self.video_api_base_url_edit, "base_url"),
            (self.video_api_key_edit, "api_key"),
        ):
            w.blockSignals(True)
            w.setText(str(c.get(key, "") or ""))
            w.blockSignals(False)
        # v0.7.8.42【不保存硬约束】：下拉框**只**显示 model 字段（用户手动填的）
        # **不**读 saved_models（v0.7.8.38.3 之前会读 → 改成完全不读）。
        # 拉取时由 _on_fetch_video_api_models 临时填充 fetched（也不写盘）。
        self.video_api_model_combo.blockSignals(True)
        self.video_api_model_combo.clear()
        model = str(c.get("model", "") or "")
        if model:
            self.video_api_model_combo.addItem(model)
            self.video_api_model_combo.setCurrentText(model)
        self.video_api_model_combo.blockSignals(False)
        # v0.7.8.38.2【下放硬约束】：ratio / duration / resolution **不**在 settings 配
        # timeout（API 请求超时）
        self.video_api_timeout_spin.blockSignals(True)
        try:
            to_val = int(c.get("timeout", 0) or 0)
        except (TypeError, ValueError):
            to_val = 0
        self.video_api_timeout_spin.setValue(to_val)
        self.video_api_timeout_spin.blockSignals(False)
        self._refresh_video_api_form_title()

    def _commit_video_api_form_to_data(self) -> None:
        """v0.7.8.38.1【无兜底硬约束】：把 form 当前值回写到 _video_api_data。
        字段缺啥就空字符串/0，**不**补默认值。用户配什么用什么。
        v0.7.8.38.2【下放硬约束】：form 已删 ratio / duration / resolution 控件，
        所以 _video_api_data 不写这三个字段。
        """
        if getattr(self, "_loading", False):
            return
        if not (0 <= self._video_api_current_idx < len(self._video_api_data["configs"])):
            return
        c = self._video_api_data["configs"][self._video_api_current_idx]
        c["name"] = self.video_api_name_edit.text().strip()
        c["base_url"] = self.video_api_base_url_edit.text().strip()
        c["api_key"] = self.video_api_key_edit.text()
        # v0.7.8.38.1【无兜底】：model 直接读 currentText，**不**补默认值
        c["model"] = self.video_api_model_combo.currentText().strip()
        c["timeout"] = int(self.video_api_timeout_spin.value())
        # v0.7.8.38.2【下放硬约束】：ratio / duration / resolution **不**在这里写
        # （如果 c 里有遗留值，由 _on_save 末尾清理掉旧字段）

    def _on_video_api_row_changed(self, row: int) -> None:
        self._commit_video_api_form_to_data()
        self._load_video_api_form_for_index(row)

    def _on_toggle_video_api_key(self, checked: bool) -> None:
        self.video_api_key_edit.setEchoMode(
            QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
        )

    def _on_video_api_activate_clicked(self) -> None:
        if not (0 <= self._video_api_current_idx < len(self._video_api_data["configs"])):
            return
        self._commit_video_api_form_to_data()
        self._video_api_data["active"] = self._video_api_data["configs"][self._video_api_current_idx]["id"]
        self._video_api_active_id = self._video_api_data["active"]
        self._refresh_video_api_list()

    def _on_video_api_add_clicked(self) -> None:
        """v0.7.8.38.1【无兜底硬约束】：新增一个空白视频 API config。
        所有字段留空，**不**预填系统默认值。
        v0.7.8.38.2【下放硬约束】：ratio / duration / resolution 不在 cfg 里。
        """
        import uuid as _uuid
        self._commit_video_api_form_to_data()
        new_id = _uuid.uuid4().hex[:8]
        self._video_api_data["configs"].append({
            "id": new_id,
            "name": "",  # 无兜底
            "base_url": "",
            "api_key": "",
            "model": "",  # 无兜底（**不**用 "doubao-seedance-2.0-fast-face"）
            "timeout": 0,  # 无兜底（**不**用 1800）
            "saved_models": [],
            # v0.7.8.38.2【下放硬约束】：ratio / duration / resolution **不**进 cfg
        })
        self._video_api_current_idx = len(self._video_api_data["configs"]) - 1
        self._refresh_video_api_list()
        self._load_video_api_form_for_index(self._video_api_current_idx)

    def _on_video_api_duplicate_clicked(self) -> None:
        if not (0 <= self._video_api_current_idx < len(self._video_api_data["configs"])):
            return
        import uuid as _uuid
        self._commit_video_api_form_to_data()
        src = dict(self._video_api_data["configs"][self._video_api_current_idx])
        src["id"] = _uuid.uuid4().hex[:8]
        src["name"] = (src.get("name") or "(未命名)") + " 副本"
        self._video_api_data["configs"].append(src)
        self._video_api_current_idx = len(self._video_api_data["configs"]) - 1
        self._refresh_video_api_list()
        self._load_video_api_form_for_index(self._video_api_current_idx)

    def _on_video_api_delete_clicked(self) -> None:
        if not (0 <= self._video_api_current_idx < len(self._video_api_data["configs"])):
            return
        if len(self._video_api_data["configs"]) <= 1:
            QMessageBox.warning(self, "无法删除", "至少保留 1 个视频 API config。")
            return
        del_id = self._video_api_data["configs"][self._video_api_current_idx]["id"]
        is_active = del_id == self._video_api_data["active"]
        ret = QMessageBox.question(
            self, "确认删除",
            f"确定删除视频 API config「{self._video_api_data['configs'][self._video_api_current_idx].get('name', del_id)}」？",
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        del self._video_api_data["configs"][self._video_api_current_idx]
        if is_active:
            self._video_api_active_id = self._video_api_data["configs"][0]["id"]
            self._video_api_data["active"] = self._video_api_active_id
        if self._video_api_current_idx >= len(self._video_api_data["configs"]):
            self._video_api_current_idx = len(self._video_api_data["configs"]) - 1
        self._refresh_video_api_list()
        self._load_video_api_form_for_index(self._video_api_current_idx)

    def _on_fetch_video_api_models(self) -> None:
        """v0.7.8.38：从当前**活跃视频 API config** 的 base_url/api_key 拉模型列表。
        仿生图 API 段，复刻 server.py:1581-1603 POST /api/list-models 思路。

        v0.7.8.38.3【拉取列表硬约束】：
        - 下拉框只显示新拉取的 `fetched` 列表，**不**混 saved_models 历史
        - 用户当前选中的 model 用 `setEditText(cur_sel)` 写回，**不** addItem
        v0.7.8.42【不保存硬约束】：
        - 拉取完成后**不写** `cur_cfg["saved_models"]`，**完全不留盘**
        - 每次生视频前都要重新拉取（不存就拿不到）
        - 重新打开 dialog 时下拉框只有当前 model（拉取列表不留）
        - 视频 tab 卡片 api 模式 model_items 不依赖 saved_models，只用
          `api_cfg.model`（用户手动填的那个）
        """
        from core.dreamina_models import DreaminaModelsError, fetch_models
        # 先把当前表单刷回 _video_api_data
        self._commit_video_api_form_to_data()
        if not (0 <= self._video_api_current_idx < len(self._video_api_data["configs"])):
            QMessageBox.warning(self, "无法拉取", "请先在视频 API 列表里选一个 config。")
            return
        cur_cfg = self._video_api_data["configs"][self._video_api_current_idx]
        base_url = str(cur_cfg.get("base_url", "") or "").strip()
        api_key = str(cur_cfg.get("api_key", "") or "").strip()
        if not base_url or not api_key:
            QMessageBox.warning(
                self, "无法拉取",
                "请先填写视频 API 的 Base URL 和 API Key。\n\n"
                "（拉取会调 {base_url}/v1/models）",
            )
            return
        self.btn_fetch_video_api_models.setEnabled(False)
        self.btn_fetch_video_api_models.setText("⏳ 拉取中…")
        try:
            QApplication.processEvents()
            try:
                fetched = fetch_models(base_url, api_key, timeout=15.0)
            except DreaminaModelsError as e:
                QMessageBox.warning(
                    self, "拉取失败",
                    f"拉取视频模型列表失败：\n{e}\n\n"
                    f"（请检查 Base URL 和 API Key 是否正确）",
                )
                log.warning("fetch_video_api_models failed: %s", e)
                return
            # v0.7.8.38.3【拉取列表硬约束】：下拉框**只**显示新拉取的 fetched。
            # 不混 saved_models，**不**用 merged 方式。用户当前选中的 model
            # 用 setEditText 写回（不 addItem，避免"历史模型进拉取列表"）。
            # 无兜底硬约束：cur_sel 即便不在 fetched 里也强制保留。
            cur_sel = self.video_api_model_combo.currentText().strip()
            self.video_api_model_combo.blockSignals(True)
            self.video_api_model_combo.clear()
            for m in fetched:
                self.video_api_model_combo.addItem(m)
            if cur_sel:
                # setEditText → cur_sel 不在 fetched 时会以"自定义"模式显示
                self.video_api_model_combo.setEditText(cur_sel)
            self.video_api_model_combo.blockSignals(False)
            # v0.7.8.42【不保存硬约束】：**不**写 saved_models
            # 拉取的 fetched **只**用于本次 dialog 期间显示，**完全不留盘**
            # 每次生视频前都要重新拉取
            # 如果有遗留 saved_models（老版本数据），拉取后清空
            if cur_cfg.get("saved_models"):
                cur_cfg["saved_models"] = []
                log.info("拉取后清空 saved_models（v0.7.8.42 不保存硬约束）")
            preview = "、".join(fetched[:8]) + ("..." if len(fetched) > 8 else "")
            QMessageBox.information(
                self, "拉取成功",
                f"✓ 拉到 {len(fetched)} 个视频模型：\n"
                f"{preview}\n\n"
                f"（v0.7.8.42 不保存硬约束：拉取列表**不**写盘，只本次显示）\n"
                f"（用户当前选的 model 已用 setEditText 保留——即使不在新拉取列表里）\n"
                f"（关闭 dialog 或重启后拉取列表会消失，下次生视频前请重新拉取）\n"
                f"点击【保存】后写入 hermes_api.json（只写非拉取字段）。",
            )
            log.info(
                "fetch_video_api_models ok: %d models, cur_sel=%r, NOT saved (v0.7.8.42)",
                len(fetched), cur_sel,
            )
        finally:
            self.btn_fetch_video_api_models.setEnabled(True)
            self.btn_fetch_video_api_models.setText("🔄 拉取")

    # ============ v0.7.8.38：Web 生成（dreamina.exe）辅助方法 ============

    def _current_dreamina_bin(self) -> str:
        """v0.7.8.38：拿到当前 dreamina.exe 绝对路径（用户配的 + fallback 自动检测）。"""
        explicit = self.dreamina_exe_edit.text().strip() if hasattr(self, "dreamina_exe_edit") else ""
        return _dreamina_find_bin(explicit) or ""

    def _refresh_dreamina_status(self) -> None:
        """v0.7.8.38：检查 dreamina 是否已安装 / 已登录（仿 server.py:3174-3187）。"""
        if not hasattr(self, "dreamina_status_label"):
            return
        bin_path = self._current_dreamina_bin()
        if not bin_path or not os.path.exists(bin_path):
            self.dreamina_status_dot.setStyleSheet("color: #888; font-size: 16px;")
            self.dreamina_status_label.setText(
                f"未安装（未找到 dreamina.exe，请先在上方配路径）"
            )
            self.btn_dreamina_login.setEnabled(False)
            self.btn_dreamina_logout.setEnabled(False)
            return
        try:
            logged_in = _dreamina_logged_in(bin_path)
        except Exception as e:
            logged_in = False
            log.warning("dreamina login check failed: %s", e)
        if logged_in:
            self.dreamina_status_dot.setStyleSheet("color: #10b981; font-size: 16px;")
            credit = _dreamina_run_to_file(bin_path, "user_credit", timeout=10.0).strip()
            credit = credit[:80] if credit else ""
            self.dreamina_status_label.setText(
                f"已登录 ({os.path.basename(bin_path)})"
                + (f" · {credit}" if credit else "")
            )
            self.btn_dreamina_login.setEnabled(True)
            self.btn_dreamina_login.setText("🔄 重新登录")
            self.btn_dreamina_logout.setEnabled(True)
        else:
            self.dreamina_status_dot.setStyleSheet("color: #f59e0b; font-size: 16px;")
            self.dreamina_status_label.setText(
                f"未登录 ({os.path.basename(bin_path)}) · 点击【🔐 登录】登录"
            )
            self.btn_dreamina_login.setEnabled(True)
            self.btn_dreamina_login.setText("🔐 登录")
            self.btn_dreamina_logout.setEnabled(False)
        self.btn_dreamina_refresh.setEnabled(True)

    def _on_dreamina_exe_changed(self) -> None:
        """v0.7.8.38：dreamina.exe 路径改动后自动刷新状态。"""
        self._refresh_dreamina_status()

    def _on_browse_dreamina_exe(self) -> None:
        """v0.7.8.38：浏览 dreamina.exe 路径。"""
        start = self.dreamina_exe_edit.text().strip() or str(Path.home())
        path, _ = QFileDialog.getOpenFileName(
            self, "选择 dreamina.exe", start,
            "可执行文件 (*.exe);;所有文件 (*.*)",
        )
        if path:
            self.dreamina_exe_edit.setText(path)
            self._refresh_dreamina_status()

    def _on_test_dreamina(self) -> None:
        """v0.7.8.38：测试 dreamina.exe 是否可用。"""
        bin_path = self._current_dreamina_bin()
        if not bin_path or not os.path.exists(bin_path):
            QMessageBox.warning(
                self, "未找到",
                "未找到 dreamina.exe：\n"
                f"  • 用户显式配的路径：{self.dreamina_exe_edit.text().strip() or '(空)'}\n"
                f"  • 探测位置：~/dreamina.exe / 项目目录 / ~/.local/bin / PATH",
            )
            return
        # 跑 user_credit 试一下（不需要登录也能跑，只是返回 failed）
        output = _dreamina_run_to_file(bin_path, "user_credit", timeout=10.0)
        QMessageBox.information(
            self, "测试通过",
            f"dreamina.exe 已找到：\n  {bin_path}\n\n"
            f"user_credit 输出：\n{output[:300] if output else '(无输出)'}",
        )

    def _on_dreamina_login(self) -> None:
        """v0.7.8.38：启动 OAuth Device Flow 登录。
        复刻老 software D:\\剧本分镜助手\\templates\\index.html:2708-2825
        startDreaminaLogin + startLoginPolling。
        """
        bin_path = self._current_dreamina_bin()
        if not bin_path or not os.path.exists(bin_path):
            QMessageBox.warning(self, "无法登录", "dreamina.exe 路径无效，请先在上方配路径。")
            return
        # 已登录 → 直接提示
        try:
            if _dreamina_logged_in(bin_path):
                ret = QMessageBox.question(
                    self, "已登录",
                    "dreamina 当前已登录。\n是否仍要重新登录？",
                )
                if ret != QMessageBox.StandardButton.Yes:
                    return
        except Exception:
            pass
        # 启动 OAuth 流程
        self.btn_dreamina_login.setEnabled(False)
        self.btn_dreamina_login.setText("⏳ 获取中…")
        try:
            QApplication.processEvents()
            ok, info = _dreamina_start_login(bin_path)
        finally:
            self.btn_dreamina_login.setEnabled(True)
            self.btn_dreamina_login.setText("🔐 登录")
        if not ok:
            QMessageBox.critical(
                self, "登录失败",
                f"启动登录失败：\n{info.get('error', '?')}\n\n"
                f"原始输出：\n{info.get('raw', '')[:300]}",
            )
            return
        # 已登录（"已复用"）
        if info.get("already_logged_in"):
            QMessageBox.information(self, "已登录", "dreamina 当前已登录。")
            self._refresh_dreamina_status()
            return
        # 弹 OAuth Device Flow 弹窗
        dlg = _DreaminaLoginDialog(bin_path, info, parent=self)
        dlg.exec()
        self._refresh_dreamina_status()

    def _on_dreamina_logout(self) -> None:
        """v0.7.8.38：登出 dreamina（复刻 server.py:3248-3267）。"""
        ret = QMessageBox.question(
            self, "确认登出",
            "确定要登出 dreamina 吗？\n登出后需要重新登录才能生成视频。",
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        removed = _dreamina_logout()
        if removed:
            QMessageBox.information(
                self, "已登出",
                f"已删除 {len(removed)} 个 token 文件：\n" + "\n".join(removed),
            )
        else:
            QMessageBox.information(self, "已登出", "未找到 token 文件（可能未登录）。")
        self._refresh_dreamina_status()

    # ============ v0.7.8.39：供 main_window 跳到指定 tab ============

    # tab key → index 映射（保持单点维护，免得 tab 顺序改时漏更新）
    _TAB_KEYS: Dict[str, int] = {
        "api": 0,         # 🔑 API 配置
        "hermes": 1,      # ⚙️ Hermes 设置
        "video_api": 2,   # 🎬 视频 API
    }

    def jump_to_tab(self, key: str) -> None:
        """v0.7.8.39：主窗口【🔗 视频 API 设置】按钮调用，弹窗后切到指定 tab。

        关键 key：
        - "api" / "hermes" / "video_api"
        - 未知 key → 不切（弹窗兜底信息）
        """
        if not hasattr(self, "tabs"):
            return
        idx = self._TAB_KEYS.get(key)
        if idx is None or idx < 0 or idx >= self.tabs.count():
            QMessageBox.information(
                self, "跳转失败",
                f"未知 tab key：{key!r}\n（支持的 key: {list(self._TAB_KEYS.keys())}）",
            )
            return
        self.tabs.setCurrentIndex(idx)


class _DreaminaLoginDialog(QDialog):
    """v0.7.8.38：dreamina OAuth Device Flow 登录弹窗。
    复刻老 software D:\\剧本分镜助手\\templates\\index.html:351-371
    loginStep1/2/3 三个步骤 + startLoginPolling 自动轮询。
    """

    def __init__(self, bin_path: str, info: Dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Dreamina 登录")
        self.setModal(True)
        self.setMinimumSize(480, 360)
        self._bin_path = bin_path
        self._poll_count = 0
        self._max_poll = 40  # 40 * 4s = 160s 超时

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # 步骤 1：未开始（隐藏）
        # 步骤 2：显示 verification_uri + user_code + 轮询状态
        # 步骤 3：登录成功

        self.lbl_step2 = QLabel()
        self.lbl_step2.setWordWrap(True)
        self.lbl_step2.setStyleSheet("font-size: 12px;")
        root.addWidget(self.lbl_step2)

        # verification_uri（链接）
        self.lbl_uri = QLabel()
        self.lbl_uri.setTextFormat(Qt.TextFormat.RichText)
        self.lbl_uri.setOpenExternalLinks(True)
        self.lbl_uri.setStyleSheet("font-size: 13px; padding: 8px; background: #1f2937; border-radius: 4px;")
        root.addWidget(self.lbl_uri)

        # user_code（大字）
        self.lbl_user_code_title = QLabel("👇 在浏览器里输入以下 user_code：")
        self.lbl_user_code_title.setStyleSheet("font-size: 12px; color: #888;")
        root.addWidget(self.lbl_user_code_title)
        self.lbl_user_code = QLabel(info.get("user_code", ""))
        self.lbl_user_code.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_user_code.setStyleSheet(
            "font-size: 28px; font-weight: bold; letter-spacing: 4px; "
            "padding: 16px; background: #111827; color: #10b981; "
            "border: 2px dashed #4b5563; border-radius: 6px;"
        )
        self.lbl_user_code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        root.addWidget(self.lbl_user_code)

        # 轮询状态
        self.lbl_poll = QLabel("⏳ 等待授权…")
        self.lbl_poll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_poll.setStyleSheet("font-size: 13px; padding: 8px;")
        root.addWidget(self.lbl_poll)

        # 步骤 3：登录成功（默认隐藏）
        self.lbl_step3 = QLabel("✅ 登录成功！")
        self.lbl_step3.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_step3.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #10b981; padding: 16px;"
        )
        self.lbl_step3.setVisible(False)
        root.addWidget(self.lbl_step3)

        root.addStretch(1)

        # 按钮
        btn_row = QHBoxLayout()
        self.btn_open = QPushButton("🌐 打开验证页面")
        self.btn_open.clicked.connect(self._on_open_uri)
        btn_row.addWidget(self.btn_open)
        btn_row.addStretch(1)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)
        self.btn_close = QPushButton("关闭")
        self.btn_close.setVisible(False)
        self.btn_close.clicked.connect(self.accept)
        btn_row.addWidget(self.btn_close)
        root.addLayout(btn_row)

        # 填充步骤 2 文案
        uri = info.get("verification_uri", "")
        if uri:
            self.lbl_step2.setText(
                f"请在 <b>{info.get('device_code', '')[:8] or ''}</b> 设备上完成登录："
            )
            self.lbl_uri.setText(
                f'<a href="{uri}" style="color: #60a5fa;">{uri}</a>'
            )
        else:
            self.lbl_step2.setText("已获取登录码，请在浏览器中完成登录。")
            self.lbl_uri.setVisible(False)
            self.lbl_user_code_title.setVisible(False)
            self.lbl_user_code.setVisible(False)
            self.btn_open.setEnabled(False)

        # 自动打开浏览器（复刻 index.html:2780-2782）
        if uri:
            QDesktopServices.openUrl(QUrl(uri))

        # 启动轮询
        self._timer = QTimer(self)
        self._timer.setInterval(4000)  # 4s
        self._timer.timeout.connect(self._on_poll)
        self._timer.start()

    @Slot()
    def _on_open_uri(self) -> None:
        """v0.7.8.38：打开 verification_uri。"""
        uri = self.lbl_uri.text()
        # 从 rich text 里抠出 href（简单处理：直接从 info 重读）
        # 这里更稳：直接拼一个 openUrl 调父类的 _bin_path + info
        # 但 info 没存——改成从 lbl_step2 附近用 thread local 保留
        # 简化：调 user_credit 拿 device_code 重新构造
        try:
            from PySide6.QtGui import QGuiApplication
            QGuiApplication.clipboard().setText(self.lbl_user_code.text())
        except Exception:
            pass
        # 重新触发一次 start_login 拿 uri
        ok, info = _dreamina_start_login(self._bin_path)
        if ok and info.get("verification_uri"):
            QDesktopServices.openUrl(QUrl(info["verification_uri"]))

    @Slot()
    def _on_poll(self) -> None:
        """v0.7.8.38：每 4s 轮询 user_credit（复刻 index.html:2793-2825 startLoginPolling）。"""
        self._poll_count += 1
        self.lbl_poll.setText(f"⏳ 等待授权… ({self._poll_count * 4}s)")
        try:
            ok, output = _dreamina_poll_login(self._bin_path)
        except Exception as e:
            log.warning("dreamina poll failed: %s", e)
            ok = False
        if ok:
            self._timer.stop()
            self.lbl_poll.setVisible(False)
            self.lbl_user_code.setVisible(False)
            self.lbl_user_code_title.setVisible(False)
            self.lbl_uri.setVisible(False)
            self.lbl_step2.setVisible(False)
            self.lbl_step3.setVisible(True)
            self.btn_open.setVisible(False)
            self.btn_cancel.setVisible(False)
            self.btn_close.setVisible(True)
            log.info("dreamina login success: %s", output[:100])
        elif self._poll_count >= self._max_poll:
            self._timer.stop()
            self.lbl_poll.setText("❌ 登录超时，请重试")
            self.lbl_poll.setStyleSheet("font-size: 13px; color: #ef4444; padding: 8px;")

    def reject(self) -> None:
        """v0.7.8.38：取消时关掉 timer。"""
        try:
            self._timer.stop()
        except Exception:
            pass
        super().reject()

