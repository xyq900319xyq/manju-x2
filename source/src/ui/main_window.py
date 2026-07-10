"""主窗口。"""
import json
import logging
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QSplitter,
    QTabWidget, QLabel, QStatusBar, QMessageBox, QToolBar,
    QPlainTextEdit, QGroupBox, QPushButton, QScrollArea,
    QFrame, QCheckBox, QFileDialog, QSizePolicy, QDialog,
    QLineEdit, QComboBox, QRadioButton, QButtonGroup,
    QProgressDialog, QApplication,
)
from PySide6.QtCore import Qt, Slot, QTimer, QThread, Signal
from PySide6.QtGui import QAction

from core.config import Config
from core.database import Database
from core.generators import (
    AssetExtractTask, AssetImageTask, BatchAssetImageTask,
    StoryboardTask, VideoPromptTask, VideoTask, VideoRequest,
)
from core.migration import open_db, get_meta
from core.models import Project, Episode
from core.task_queue import Task, TaskQueue
from core.video_segments import (  # v0.6.19
    VIDEO_STATUS_READY, add_segment, dump_video_segments, empty_envelope,
    parse_video_segments, remove_segment, split_segment_by_marker,
    update_segment_video,
)
from core.web_video import (  # v0.6.22
    WebVideoRequest, safe_web_video_filename, validate_cmd_template,
)

from ui.asset_panel import AssetListWidget
from ui.dialogs import NewProjectDialog, NewEpisodeDialog
from ui.log_dialog import LogBuffer, LogDialog
from ui.project_tree import ProjectTree
from ui.settings_dialog import SettingsDialog
from ui.task_status import TaskStatusWidget

# v1.1.0 一键更新
from core.updater import UpdateDownloader

APP_TITLE = "漫剧助手X-2"
# ROOT 由 main.py 显式传入（支持 EXE 和源码两种模式）
# 保留模块级占位，避免循环引用
ROOT: Path = Path(__file__).resolve().parent.parent

log = logging.getLogger("manju.main")


class _WebVideoWorker(QThread):
    """v0.6.22：web 视频生成后台线程。

    跑 run_web_video（写 prompt 文件 + 调用户命令 + 等产物）。
    完成发 finished_ok(str video_path) 或 failed(str error) 信号。
    """
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, request, timeout: float = 600.0, parent=None) -> None:
        super().__init__(parent)
        self._request = request
        self._timeout = timeout

    def run(self) -> None:
        try:
            from core.web_video import run_web_video
            result = run_web_video(self._request, timeout=self._timeout)
        except Exception as e:  # noqa: BLE001
            log.exception("web video worker crash")
            self.failed.emit(f"线程异常: {e}")
            return
        if result.error:
            self.failed.emit(result.error)
        elif result.video_path:
            self.finished_ok.emit(result.video_path)
        else:
            self.failed.emit("未知失败：result 既无 error 也无 video_path")


class MainWindow(QMainWindow):
    def __init__(self, root: Optional[Path] = None):
        super().__init__()
        if root is not None:
            globals()["ROOT"] = root
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 800)
        # v0.7.8.39【视频生成链路】：默认 "web"（走 dreamina.exe）。用户每次
        # 切换到 api 时被覆盖；存在 ep 内存（不落 db，因为是临时偏好）。
        # 链路决定 _on_generate_single_video / _on_generate_video 调哪个 task
        # 以及 model combobox 默认值从 dreamina_models 还是 video_api_config.model 来。
        self._video_link_mode: str = "web"  # "web" | "api"

        # 加载配置
        try:
            config_path = ROOT / "config" / "hermes_api.json"
            # v0.7.7 重打 10：把 ROOT 显式传给 Config，让 EXE 模式（_internal/core/config.py
            # → parent.parent.parent = dist/漫剧助手X-1）下 _project_root 也用真正的项目根
            # D:\漫剧助手，跟源码模式一致，outputs/.. 路径统一。
            self.config = Config.get(config_path, project_root=ROOT)
        except Exception as e:
            # 用 print 不用 QMessageBox，避免无 GUI 环境时阻塞
            log.error("配置加载失败: %s", e)
            print(f"FATAL: 配置加载失败: {e}", file=sys.stderr)
            print(f"      项目根: {ROOT}", file=sys.stderr)
            print(f"      期望配置文件: {ROOT / 'config' / 'hermes_api.json'}", file=sys.stderr)
            raise

        # 打开 db
        try:
            self.con = open_db(ROOT)
        except FileNotFoundError as e:
            log.error("数据库文件不存在: %s", e)
            print(f"FATAL: 数据库文件不存在: {e}", file=sys.stderr)
            raise
        except Exception as e:
            log.exception("打开数据库失败")
            print(f"FATAL: 打开数据库失败: {e}", file=sys.stderr)
            raise
        self.db = Database(self.con)

        # 任务队列
        self.task_queue = TaskQueue(self)
        self._connect_task_queue()

        # v0.7.8.12：启动时把 db 里已有的 storyboard / prompt 补写磁盘，
        # 保证历史生成的剧集"打开文件"按钮可用（旧版只写 db 没落盘）
        try:
            n = self.dump_all_episodes_to_disk()
            if n:
                log.info("启动补写：%d 个分镜/prompt 文件已落盘", n)
        except Exception as e:
            log.warning("启动补写失败（不影响使用）: %s", e)

        # 中心：左树 + 右 Tab
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.tree = ProjectTree()
        # v0.7.8.37b fix2:强制 Expanding —— QTreeWidget 默认 Preferred/
        # Preferred,在水平 splitter 里 vertical 方向可能不被拉满,跟 tab
        # 一起挤成一行 → 看起来"项目树也空白"。
        self.tree.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(False)
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 980])
        self.setCentralWidget(splitter)
        log.info("__init__: splitter + centralWidget 设好")

        # v0.7.8.37d fix:下面这段之前被错误剪切到 _set_tab_content 方法里,
        # __init__ 实际上没执行任何 UI 初始化 + 树信号 + _reload_projects,
        # 导致项目树永远是空的,看起来"UI 全坏"。现在搬回 __init__ 末尾。
        # 状态栏
        # v0.7.8.37l/m:用户反馈"点生成后界面变长 —— 是最下面的日志运行栏撑高
        # 把整个窗口拉大"。多次 setFixedHeight 锁高度 + setSizeConstraint
        # 都没完全解决 —— 根因更深:
        # 1) 任务运行时 _on_task_output 频繁 setText 改 _phase 文字(~每秒多次)
        #    → QLabel 文字宽度变化 → QStatusBar 内部 QHBoxLayout 重新 layout
        #    → QStatusBar sizeHint 变化 → QMainWindowLayout 响应 → 整个
        #    QMainWindow 重新算 sizeHint + 调整 geometry。
        # 2) addWidget/addPermanentWidget 的 widget setVisible 切换时
        #    QStatusBar sizeHint 也跟着变(visible→0 hidden→32)。
        # 3) 修 setSizeConstraint(SetFixedSize) 不够 —— QLayout::SetFixedSize
        #    只锁住 children 撑大,但不阻止 QStatusBar sizeHint 在 setText
        #    时变化。
        # v0.7.8.37n 终极修复:不用 QStatusBar 的 addWidget/addPermanentWidget,
        # 改用一个 QFrame(固定 30px)自己布局 —— 完全绕开 QStatusBar 的
        # 内部 layout 监听机制,让 QStatusBar 只有一个固定 30px 子 widget,
        # QStatusBar sizeHint 永远 = 30px。QMainWindow 永远不 resize。
        from PySide6.QtWidgets import QFrame
        self.status = QStatusBar()
        self.status.setFixedHeight(30)  # 锁死
        self.status.setSizeGripEnabled(False)
        # v0.7.8.37n:不调 setStatusBar 内部的 addWidget/addPermanentWidget
        # —— QStatusBar 内置一个 QHBoxLayout,我们直接把 status_frame add 进去,
        # 不用 statusBar 自带的 addWidget API。
        status_frame = QFrame()
        status_frame.setFixedHeight(30)  # 锁死
        # 内部 layout 也锁死,防止 children 撑大
        from PySide6.QtWidgets import QHBoxLayout
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(8, 3, 8, 3)
        status_layout.setSpacing(8)
        from PySide6.QtWidgets import QLayout
        status_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        self.status_msg = QLabel("就绪")
        self.status_msg.setFixedHeight(24)
        from PySide6.QtCore import Qt as _Qt
        self.status_msg.setTextFormat(_Qt.TextFormat.PlainText)
        self.status_msg.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        status_layout.addWidget(self.status_msg, 1)  # stretch=1 占满

        self.status_migration = QLabel("")
        self.status_migration.setStyleSheet("color: #666;")
        self.status_migration.setFixedHeight(24)
        status_layout.addWidget(self.status_migration, 0)

        self.task_status_widget = TaskStatusWidget()
        self.task_status_widget.setFixedHeight(24)
        self.task_status_widget.setFixedWidth(220)  # 锁宽 220px,文字变不撑宽
        self.task_status_widget.cancel_requested.connect(self._on_cancel_current_task)
        status_layout.addWidget(self.task_status_widget, 0)

        self.btn_open_log = QPushButton("📋 日志")
        self.btn_open_log.setFixedHeight(24)
        status_layout.addWidget(self.btn_open_log, 0)
        self.log_buffer = LogBuffer(max_lines=5000, parent=self)
        self.btn_open_log.clicked.connect(self._on_open_log)

        self.btn_open_project_dir = QPushButton("📁 打开项目目录")
        self.btn_open_project_dir.setFixedHeight(24)
        self.btn_open_project_dir.setToolTip("打开当前项目输出目录（outputs/<项目名>/）")
        self.btn_open_project_dir.clicked.connect(self._on_open_project_dir)
        self.btn_open_project_dir.setEnabled(False)
        status_layout.addWidget(self.btn_open_project_dir, 0)

        # v0.7.8.37n:直接 addPermanentWidget status_frame(QFrame 30px) ——
        # QStatusBar sizeHint = max(current children, 30) 永远 30。
        self.status.addPermanentWidget(status_frame, 1)
        self.setStatusBar(self.status)
        self._refresh_migration_label()
        # v0.7.8.2：日志 Tab 填上真实视图（之前是"待迁移"占位）
        self._show_log_tab()

        # 菜单 / 工具栏
        self._build_menus()

        # 树信号
        self.tree.project_selected.connect(self._on_project_selected)
        self.tree.episode_selected.connect(self._on_episode_selected)
        self.tree.context_new_episode.connect(self._on_new_episode)
        self.tree.context_rename_project.connect(self._on_rename_project)
        self.tree.context_delete_project.connect(self._on_delete_project)
        self.tree.context_edit_episode.connect(self._on_edit_episode)
        self.tree.context_delete_episode.connect(self._on_delete_episode)
        # v0.6.18 #8：📋 导出整剧集 prompts 菜单
        self.tree.context_export_prompts.connect(self._on_export_all_prompts)

        # 当前选中的剧集（生成按钮用到）
        self._current_episode: Optional[Episode] = None
        self._current_project: Optional[Project] = None

        # v0.7.8.37i:视频 / 提示词 tab widget 缓存,避免 23 段卡片的 700
        # widget + prompt 大文本框每次切剧集都全量重建(卡 + scroll 跳顶)。
        self._video_tab_cache: Optional[tuple] = None  # (cache_key, w)
        self._prompt_tab_cache: Optional[tuple] = None  # (cache_key, w)
        # v0.7.8.49:分镜 / 资产 tab widget 缓存,跟 prompt/video 同模式
        self._episode_detail_cache: Optional[tuple] = None  # (ep_id, w)
        self._asset_tab_cache: Optional[tuple] = None  # (project_id, panel)
        # v0.7.8.49:项目概览缓存
        self._project_overview_cache: Optional[tuple] = None  # ((project_id, n_eps), w)
        # v0.7.8.49:点剧集时把 4 个 tab 重建推到下个 event loop tick,
        # click 立刻响应(状态栏先变),tab 异步刷新
        self._pending_episode_update: Optional[str] = None
        self._pending_episode_timer: Optional[QTimer] = None
        # v0.7.8.50:切新 ep 时 4 个 tab cache 全失效 → 每个 tab 都要重建(700 widget 同步创建 200-800ms)
        # 一次只重建 1 个 tab,分 4 帧走完,用户先看到分镜 tab,其他 tab 后台慢慢补。
        # 切同 ep(全部 cache 命中)不走这条路径,仍然是 0ms
        self._pending_episode_tab_index: int = 0
        self._pending_episode_tab_timer: Optional[QTimer] = None
        self._pending_episode_tab_ep: Optional[Episode] = None
        self._pending_episode_tab_project: Optional[Project] = None

        # 加载数据
        self._reload_projects()
        log.info("__init__: 完成, tree.topLevelItemCount=%d, status_msg=%s",
                 self.tree.topLevelItemCount(), self.status_msg.text())

    def _dev_autotest_v07871(self) -> None:
        """v0.7.8.71 dev autotest: 模拟 user 点 #2 段「▶ 生成」按钮(已禁用)"""
        pass  # v0.7.8.72: 移除 dev autotest,只保留作 stub 避免 import 错误

    @staticmethod
    def _make_tab_holder() -> tuple:
        """v0.7.8.37 (废弃):旧 holder 模式已回退(v0.7.8.37d)。

        保留是为了避免外部调用报错(目前没外部调用,但防御性)。
        返回 (QWidget, QVBoxLayout) 备用,不会被 _replace_tab 用到。
        """
        inner = QWidget()
        inner_layout = QVBoxLayout(inner)
        inner_layout.setContentsMargins(0, 0, 0, 0)
        inner_layout.setSpacing(0)
        return (inner, inner_layout)

    # ---------- UI 构造 ----------
    def _placeholder_tab(self, text: str) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab = QLabel(text)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setStyleSheet("color: #888; font-size: 14px;")
        l.addWidget(lab)
        return w

    def _build_menus(self) -> None:
        tb = QToolBar("主工具栏")
        tb.setMovable(False)
        self.addToolBar(tb)

        act_new = QAction("➕ 新建项目", self)
        act_new.setShortcut("Ctrl+N")
        act_new.triggered.connect(self._on_new_project)
        tb.addAction(act_new)

        # v0.6.27：toolbar 加 ➕ 新建剧集 按钮（复刻老软件"+"按钮显眼入口）
        # 没选项目时灰着；选了项目就启用。
        self._act_new_episode = QAction("➕ 新建剧集", self)
        self._act_new_episode.setShortcut("Ctrl+Shift+N")
        self._act_new_episode.setToolTip("为当前选中的项目新建一个剧集（需先选项目）")
        self._act_new_episode.setEnabled(False)  # 默认灰着
        self._act_new_episode.triggered.connect(self._on_new_episode_toolbar)
        tb.addAction(self._act_new_episode)

        tb.addSeparator()

        act_refresh = QAction("🔄 刷新", self)
        act_refresh.setShortcut("F5")
        act_refresh.triggered.connect(self._reload_projects)
        tb.addAction(act_refresh)

        tb.addSeparator()
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy(),
                             spacer.sizePolicy().verticalPolicy())
        tb.addWidget(spacer)
        tb.addWidget(QLabel(f"  {APP_TITLE}  "))

        mb = self.menuBar()
        m_file = mb.addMenu("文件(&F)")
        m_file.addAction(act_new)
        m_file.addAction(act_refresh)
        m_file.addSeparator()
        act_quit = QAction("退出(&X)", self)
        act_quit.setShortcut("Ctrl+Q")
        act_quit.triggered.connect(self.close)
        m_file.addAction(act_quit)

        m_settings = mb.addMenu("设置(&S)")
        act_settings = QAction("⚙ API 配置…(&A)", self)
        act_settings.setShortcut("Ctrl+,")
        act_settings.triggered.connect(self._on_settings)
        m_settings.addAction(act_settings)

        m_help = mb.addMenu("帮助(&H)")
        # v1.0.0 用户版：检查更新菜单项（带红点）
        self._act_check_update = QAction("🔔 检查更新(&U)", self)
        self._act_check_update.setToolTip("点击立即检查 GitHub releases 上的最新版")
        self._act_check_update.triggered.connect(self._on_check_update_manual)
        m_help.addAction(self._act_check_update)
        # 红点 badge（v1.1.0 一键更新：点击直接弹"立即更新?"对话框）
        self._update_badge = QAction("🔴", self)
        self._update_badge.setToolTip("有可用的新版本！点击「立即更新」")
        self._update_badge.setVisible(False)
        self._update_badge.triggered.connect(self._on_badge_clicked)
        m_help.addAction(self._update_badge)
        act_about = QAction("关于(&A)", self)
        act_about.triggered.connect(self._on_about)
        m_help.addAction(act_about)
        act_db = QAction("数据库信息(&D)", self)
        act_db.triggered.connect(self._show_db_info)
        m_help.addAction(act_db)
        act_open_outputs = QAction("打开 outputs 目录(&O)", self)
        act_open_outputs.triggered.connect(self._open_outputs_dir)
        m_help.addAction(act_open_outputs)

    # ---------- v1.0.0 用户版：更新检查 ----------
    @Slot(object)
    def _on_update_available(self, info) -> None:
        """updater 检测到新版 → 显示红点 + 状态栏提示。"""
        try:
            latest = info.latest_version if info else "?"
        except Exception:
            latest = "?"
        self._update_badge.setVisible(True)
        self._update_badge.setText(f"🔴 新版 {latest}")
        self.status_msg.setText(
            f"🔔 发现新版本 {latest}，点击「帮助 → 检查更新」查看详情"
        )
        log.info("_on_update_available: 显示红点 latest=%s", latest)

    @Slot(object)
    def _on_no_update(self, info) -> None:
        """updater 拉到结果但无新版 / 拉取失败 → 隐藏红点，不打扰用户。"""
        self._update_badge.setVisible(False)
        # 失败也静默（只 log），不弹错
        if info and info.error_msg:
            log.info("updater: %s（已静默）", info.error_msg)
        # 注：有新版时 _on_update_available 会覆盖 status_msg，
        # 无新版时不强改状态栏文字（避免盖住用户当前上下文）

    @Slot()
    def _on_badge_clicked(self) -> None:
        """v1.1.0 一键更新：用户点红点 → 弹"立即更新?"对话框。"""
        info = None
        if hasattr(self, "_updater") and self._updater is not None:
            info = self._updater.latest_info
        if info is None or not info.has_update:
            QMessageBox.information(self, "提示", "暂无可用更新信息，请先点「检查更新」。")
            return
        self._show_update_dialog(info)

    def _show_update_dialog(self, info) -> None:
        """v1.1.0 一键更新：弹"立即更新?" → 启动后台下载 + 进度条。"""
        if not info.asset_url:
            QMessageBox.information(
                self, "提示",
                f"新版本 v{info.latest_version} 暂未提供 EXE 安装包，\n"
                f"请前往 GitHub release 页面下载：\n{info.html_url}",
            )
            return
        size_mb = (info.asset_size or 0) / (1024 * 1024)
        size_text = f"{size_mb:.1f} MB" if size_mb > 0 else "未知大小"
        ret = QMessageBox.question(
            self, "发现新版本",
            f"当前版本: v{info.current_version}\n"
            f"最新版本: v{info.latest_version}\n"
            f"安装包大小: {size_text}\n\n"
            "是否立即下载并自动安装？\n"
            "（下载完成后软件将自动关闭并启动安装程序）",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if ret != QMessageBox.Yes:
            return
        # 选个临时目录（v1.1.0【硬约束】:不用 EXE 同目录,避免被反病毒扫描）
        try:
            temp_dir = os.environ.get("TEMP") or os.environ.get("TMP") or str(Path.home())
        except Exception:
            temp_dir = str(Path.home())
        dest = os.path.join(temp_dir, f"manju-x2-v{info.latest_version}-Setup.exe")
        # 起下载器
        self._downloader = UpdateDownloader(self)
        dlg = QProgressDialog(
            f"正在下载 v{info.latest_version} 安装包…", "取消", 0, 100, self,
        )
        dlg.setWindowTitle("一键更新")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setValue(0)

        def _on_progress(pct: int, received: int, total: int) -> None:
            if pct < 0:
                # 未知总大小时,显示已下载
                dlg.setLabelText(f"已下载 {received / (1024 * 1024):.1f} MB…")
            else:
                dlg.setValue(pct)

        def _on_finished(path: str) -> None:
            dlg.close()
            self.status_msg.setText(f"✅ v{info.latest_version} 下载完成,准备安装…")
            log.info("下载完成 %s,准备启动静默安装", path)
            self._launch_setup_silent(path, info.latest_version)

        def _on_error(msg: str) -> None:
            dlg.close()
            log.warning("下载失败: %s", msg)
            # v1.1.3【防 UnicodeEncodeError】:info.html_url 在 v1.1.2
            # 之前的 update.json 是 ".../docs/更新日志.md"(中文路径)。
            # QMessageBox.critical 在 Windows native MessageBox 转换时
            # 触发 ascii encode,position 51-54 爆 "UnicodeEncodeError"。
            # 防御:html_url 段强制 ascii safe(中文 → '?')。
            safe_url = info.html_url.encode("ascii", "replace").decode("ascii")
            QMessageBox.critical(
                self, "下载失败",
                f"下载安装包失败：\n{msg}\n\n可前往 {safe_url} 手动下载。",
            )

        self._downloader.progress.connect(_on_progress)
        self._downloader.finished.connect(_on_finished)
        self._downloader.error.connect(_on_error)
        dlg.canceled.connect(self._downloader.cancel)
        ok = self._downloader.start(info.asset_url, dest)
        if not ok:
            QMessageBox.warning(self, "提示", "已有下载任务在跑,请稍候。")
            return
        dlg.exec()

    def _launch_setup_silent(self, setup_path: str, new_version: str) -> None:
        """v1.1.0 一键更新:启动 Setup.exe 静默装,然后关主窗口让位给安装器。"""
        if not os.path.exists(setup_path):
            QMessageBox.critical(self, "安装失败", f"找不到安装包:\n{setup_path}")
            return
        ret = QMessageBox.question(
            self, "开始安装",
            f"v{new_version} 安装包已就绪,点击「是」立即安装。\n"
            "安装过程中软件将自动关闭,新版本会自动启动。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if ret != QMessageBox.Yes:
            return
        try:
            # Inno Setup 6.x 静默装参数: /VERYSILENT /SUPPRESSMSGBOXES /SP- /NORESTART
            # /CLOSEAPPLICATIONS 让安装器自动关掉 manju-x2.exe
            subprocess.Popen(
                [setup_path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/SP-",
                 "/CLOSEAPPLICATIONS", "/NORESTART"],
                close_fds=True,
            )
            log.info("已启动 Setup.exe 静默装: %s", setup_path)
        except OSError as e:
            QMessageBox.critical(self, "启动安装器失败", str(e))
            return
        # 给安装器一点时间启动再关自己(避免安装器还没起就被关)
        QTimer.singleShot(500, QApplication.quit)

    def _on_check_update_manual(self) -> None:
        """用户主动点「检查更新」→ 强制拉取（跳过缓存）+ 有新版直接进一键更新流程。"""
        from core.updater import fetch_latest_release, has_newer_version
        log.info("用户主动检查更新")
        # 同步拉(用户主动行为,等他 1-2s 比弹"正在查"更直接)
        info = fetch_latest_release()
        info.current_version = "1.1.4"
        if not info.error_msg and info.latest_version:
            info.has_update = has_newer_version(info.current_version, info.latest_version)
        # 同步把结果塞给 self._updater.latest_info(让红点逻辑也走通)
        if hasattr(self, "_updater") and self._updater is not None:
            self._updater._latest_info = info
        if info.error_msg:
            QMessageBox.warning(self, "检查更新失败",
                                f"无法连接到 GitHub：\n\n{info.error_msg}\n\n请稍后重试。")
        elif info.has_update:
            # v1.1.0:有新版 → 直接进一键更新流程,不弹只读对话框
            self._show_update_dialog(info)
        else:
            QMessageBox.information(self, "已是最新版",
                                    f"当前版本: v{info.current_version}\n"
                                    f"最新版本: {info.latest_version or '（API 无数据）'}\n\n"
                                    "无需更新。")

    # ---------- 加载 / 刷新 ----------
    def _reload_projects(self) -> None:
        projects = self.db.list_projects()
        log.info("_reload_projects: db.list_projects() 返回 %d 个: %s",
                 len(projects), [(p.id, p.name) for p in projects])
        self.tree.load_projects(projects)
        log.info("_reload_projects: tree.load_projects 调完, tree.topLevelItemCount=%d",
                 self.tree.topLevelItemCount())
        self.status_msg.setText(f"就绪 — 共 {len(projects)} 个项目")
        self._refresh_migration_label()

    def _refresh_migration_label(self) -> None:
        try:
            at = get_meta(self.con, "migrated_at")
            sp = get_meta(self.con, "source_path")
            rows = get_meta(self.con, "source_rows")
            if at:
                self.status_migration.setText(
                    f"已从 {sp} 迁移 ({at})  {rows or ''}"
                )
        except Exception as e:
            # v1.1.5【C10 修复】:数据迁移失败时留 log,user 反映"迁移没显示"
            # 至少能从 logs/manju.log 看到为啥失败
            log.debug("migrate status check failed: %s", e)

    # ---------- 选择事件 ----------
    @Slot(str)
    def _on_project_selected(self, project_id: Optional[str]) -> None:
        if not project_id:
            self.btn_open_project_dir.setEnabled(False)
            # v0.6.27：没选项目 → 灰着 toolbar 按钮
            if hasattr(self, "_act_new_episode"):
                self._act_new_episode.setEnabled(False)
            return
        project = self.db.get_project(project_id)
        if not project:
            self.btn_open_project_dir.setEnabled(False)
            if hasattr(self, "_act_new_episode"):
                self._act_new_episode.setEnabled(False)
            return
        eps = self.db.list_episodes(project_id)
        self.tree.set_episodes(project_id, eps)
        self.tabs.setCurrentIndex(0)
        self._current_project = project
        self._current_episode = None
        self._show_project_overview(project, eps)
        self._show_asset_tab(project, switch=False)  # v0.7.8.20:只刷新资产 tab,不切过去
        self.btn_open_project_dir.setEnabled(True)
        # v0.6.27：选了项目 → 启用 toolbar 的"新建剧集"按钮
        if hasattr(self, "_act_new_episode"):
            self._act_new_episode.setEnabled(True)
        self.status_msg.setText(f"项目: {project.name}    剧集: {len(eps)}")
        # v0.7.8.20:再次强制切回概览,覆盖后续 _replace_tab 的 setCurrentIndex 副作用
        self.tabs.setCurrentIndex(0)

    @Slot(str)
    def _on_episode_selected(self, episode_id: Optional[str]) -> None:
        if not episode_id:
            return
        # v0.7.8.49:点击剧集时只更新轻量状态(项目指针 + 状态栏),把
        # 4 个 tab 重建推到下个 event loop tick。click 立刻响应,tab
        # 异步刷新(700 widget 不阻塞 UI 线程)。
        # 同 ep_id 多次连点:先 cancel 上一个 timer,只跑最后一次
        if self._pending_episode_timer is not None:
            self._pending_episode_timer.stop()
            self._pending_episode_timer = None
        ep = self.db.get_episode(episode_id)
        if not ep:
            return
        project = self.db.get_project(ep.project_id) if self._current_project is None or self._current_project.id != ep.project_id else self._current_project
        if project is None:
            project = self.db.get_project(ep.project_id)
        self._current_project = project
        self._current_episode = ep
        # 状态栏立即更新(轻量),click 感觉有响应
        self.status_msg.setText(f"剧集: 第{ep.episode_num}集 - {ep.title}  ·  加载中…")
        self.tabs.setCurrentIndex(1)
        # 重 tab 内容异步刷新
        self._pending_episode_update = episode_id
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._flush_pending_episode_update)
        self._pending_episode_timer = timer
        timer.start(0)

    def _flush_pending_episode_update(self) -> None:
        """v0.7.8.49:执行 _on_episode_selected 推迟的 tab 重建。
        v0.7.8.50:4 tab 分 4 帧走,每帧 1 tab,用户先看到分镜 tab,其他 tab 后续补。
        """
        ep_id = self._pending_episode_update
        self._pending_episode_update = None
        self._pending_episode_timer = None
        if not ep_id:
            return
        ep = self.db.get_episode(ep_id)
        if not ep:
            return
        project = self._current_project
        if project is None or project.id != ep.project_id:
            project = self.db.get_project(ep.project_id)
            self._current_project = project
        self._current_episode = ep
        # v0.7.8.32：历史 prompt 静默补偿。如果 prompt 已生成但 video_segments
        # 还是空(老数据 / 之前版本没自动推送),自动补推一次,不去切 tab 也不弹窗,
        # 状态栏给个轻提示。如果用户已手动编辑过 segments(非空),不动,避免覆盖。
        if ep.prompt and not ep.video_segments:
            ep_after = self.db.get_episode(ep.id)
            if ep_after and ep_after.prompt and not ep_after.video_segments:
                n = self._auto_push_prompt_to_segments(ep_after, ep_after.prompt)
                if n > 0:
                    self.status_msg.setText(
                        f"剧集: 第{ep.episode_num}集 - {ep.title}  ·  已为历史 prompt 补推 {n} 段到视频页"
                    )
                    ep = self.db.get_episode(ep.id) or ep
                    self._current_episode = ep
        # v0.7.8.50:把 4 个 tab 重建拆成 4 帧(frame 0/1/2/3)
        # frame 0 现在跑(同 tick):最关键的分镜 tab + 状态栏
        # frame 1/2/3 下个 tick:提示词 / 视频 / 资产
        self._show_episode_detail(ep, project)
        if not (ep.prompt and not ep.video_segments):
            # 仅当没触发自动补推时显示剧集信息(避免覆盖补推状态)
            self.status_msg.setText(f"剧集: 第{ep.episode_num}集 - {ep.title}")
        # v0.7.8.20:再次强制切回分镜,覆盖后续 _replace_tab 的 setCurrentIndex 副作用
        self.tabs.setCurrentIndex(1)

        # v0.7.8.50:启动分帧异步 —— 剩下 3 tab 一帧一个
        self._pending_episode_tab_ep = ep
        self._pending_episode_tab_project = project
        self._pending_episode_tab_index = 1  # 下次跑第 1 步(提示词)
        self._schedule_next_pending_episode_tab()

    def _schedule_next_pending_episode_tab(self) -> None:
        """v0.7.8.50:递归调度下个 pending tab。3 步走完即停。"""
        if self._pending_episode_tab_timer is not None:
            self._pending_episode_tab_timer.stop()
            self._pending_episode_tab_timer = None
        ep = self._pending_episode_tab_ep
        project = self._pending_episode_tab_project
        idx = self._pending_episode_tab_index
        if ep is None or idx >= 3:
            # 走完 3 步(提示词/视频/资产) → 清场
            self._pending_episode_tab_ep = None
            self._pending_episode_tab_project = None
            self._pending_episode_tab_index = 0
            return
        # 同步跑当前 step(单 tab 200-400ms 不会卡顿感知,用户已看到分镜 tab)
        try:
            if idx == 1:
                self._show_prompt_tab(ep, project)
            elif idx == 2:
                # v0.7.8.30:视频 tab 跟分镜/提示词一样在选剧集时同步刷新
                self._show_video_tab(ep, project)
            elif idx == 3:
                # 资产 tab 跟着项目更新
                if project is not None:
                    self._show_asset_tab(project, switch=False)
        except Exception as e:
            log.exception("_pending_episode_tab step %d failed: %s", idx, e)
        # 推进到下个 step,推到下个 event loop tick
        self._pending_episode_tab_index = idx + 1
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(self._schedule_next_pending_episode_tab)
        self._pending_episode_tab_timer = timer
        timer.start(0)

    # ---------- 详情面板 ----------
    def _show_project_overview(self, project: Project, eps) -> None:
        # v0.7.8.49:cache 命中(同 project_id + 剧集数)→ 复用
        cache_key = (project.id, len(eps))
        if (
            self._project_overview_cache
            and self._project_overview_cache[0] == cache_key
        ):
            self._replace_tab(0, self._project_overview_cache[1], "📁 项目")
            return
        w = QWidget()
        outer = QVBoxLayout(w)

        title_box = QGroupBox()
        tlay = QVBoxLayout(title_box)
        tlay.addWidget(QLabel(f"<h2 style='margin:0'>{project.name}</h2>"))
        if project.description:
            tlay.addWidget(QLabel(f"<i>{project.description}</i>"))
        meta = QLabel(
            f"<span style='color:#888'>创建: {project.created_at}    "
            f"更新: {project.updated_at or '-'}    "
            f"剧集: {len(eps)}</span>"
        )
        tlay.addWidget(meta)
        outer.addWidget(title_box)

        eps_box = QGroupBox("剧集")
        elay = QVBoxLayout(eps_box)
        # v0.6.27：剧集面板顶部显眼位置加"新建剧集"按钮（复刻老软件
        # index.html:179 的 "+ 新增剧集" 按钮）。之前只在项目树右键菜单里有，
        # 用户找不到入口。
        ep_btn_row = QHBoxLayout()
        self._btn_new_episode_overview = QPushButton("➕ 新建剧集")
        self._btn_new_episode_overview.setFixedHeight(32)
        # v0.7.0：跟随主题强调色（橙 #FF8C42），不再用绿
        self._btn_new_episode_overview.setStyleSheet(
            "QPushButton { background: #FF8C42; color: white; font-weight: bold; border: 1px solid #FF8C42; }"
            "QPushButton:hover { background: #FFA260; border: 1px solid #FFA260; }"
            "QPushButton:pressed { background: #E07A30; border: 1px solid #E07A30; }"
        )
        self._btn_new_episode_overview.clicked.connect(
            lambda checked=False, pid=project.id: self._on_new_episode(pid)
        )
        ep_btn_row.addWidget(self._btn_new_episode_overview)
        ep_btn_row.addStretch()
        ep_count_lbl = QLabel(f"共 {len(eps)} 集")
        ep_count_lbl.setStyleSheet("color: #888;")
        ep_btn_row.addWidget(ep_count_lbl)
        elay.addLayout(ep_btn_row)
        if eps:
            for ep in eps:
                # v0.6.27：点击剧集行也可切换到该剧集
                row = QHBoxLayout()
                line = QLabel(
                    f"<b>第{ep.episode_num}集</b> · {ep.title or '（无标题）'} "
                    f"<span style='color:#888'>"
                    f"[{ep.status}] 提示词:{ep.prompt_status or '-'} "
                    f"资产:{ep.asset_status or '-'}</span>"
                )
                line.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                row.addWidget(line, 1)
                btn_open = QPushButton("打开")
                btn_open.setFixedHeight(24)
                btn_open.clicked.connect(
                    lambda checked=False, eid=ep.id: self._on_episode_selected(eid)
                )
                row.addWidget(btn_open)
                wrap = QWidget()
                wrap.setLayout(row)
                elay.addWidget(wrap)
        else:
            empty = QLabel("<i>暂无剧集 — 点击上方 [➕ 新建剧集] 添加第一集</i>")
            empty.setStyleSheet("color: #888; padding: 12px;")
            elay.addWidget(empty)
        outer.addWidget(eps_box, 1)

        outer.addStretch(1)
        # v0.7.8.49:cache miss → 把新 widget 存进 cache
        self._project_overview_cache = (cache_key, w)
        self._replace_tab(0, w, "📋 概览")

    def _show_episode_detail(self, ep: Episode, project: Optional[Project]) -> None:
        """分镜 Tab 内容。

        v0.7.8.19:左右对称布局 — 剧本左,分镜右。
        v0.7.8.20:改用 QSplitter 替代 QScrollArea+QHBoxLayout。QPlainTextEdit
        的 sizeHint 是文档全高,QScrollArea container 高度 = max(文档全高, viewport),
        文档短时 container 比 viewport 小,空白留底。QSplitter 让两个 panel 跟窗口
        等高同步拉伸,QPlainTextEdit 内部自带滚动条处理长内容。
        v0.7.8.49:cache 命中(同 ep_id)→ 直接复用旧 widget,不重建。
        """
        # v0.7.8.49:cache 命中 → 复用(走 _replace_tab 防止重复 remove/insert)
        if self._episode_detail_cache and self._episode_detail_cache[0] == ep.id:
            self._replace_tab(1, self._episode_detail_cache[1], "🎬 分镜")
            return
        w = QWidget()  # 不用 QScrollArea
        outer = QVBoxLayout(w)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # 标题
        head = QGroupBox()
        hlay = QVBoxLayout(head)
        hlay.addWidget(QLabel(f"<h2 style='margin:0'>第{ep.episode_num}集：{ep.title}</h2>"))
        meta = QLabel(
            f"<span style='color:#888'>id: {ep.id}    "
            f"状态: {ep.status}    模式: {ep.mode}    "
            f"提示词: {ep.prompt_status or '-'}    资产: {ep.asset_status or '-'}</span>"
        )
        meta.setWordWrap(True)
        hlay.addWidget(meta)
        outer.addWidget(head)

        # v0.7.8.20:左右对称布局用 QSplitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)
        splitter.setChildrenCollapsible(False)

        # ============ 左：剧本 ============
        sbox = QGroupBox("剧本")
        slay = QVBoxLayout(sbox)
        script = QPlainTextEdit(ep.script or "（暂无剧本）")
        script.setReadOnly(True)
        script.setStyleSheet("background: #1E1E1E;")
        script.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        slay.addWidget(script, 1)
        # 导入剧本键放在剧本框下方
        self._btn_import_script = QPushButton("📥 导入剧本")
        self._btn_import_script.setFixedHeight(32)
        self._btn_import_script.setToolTip(
            "从本地文件加载剧本到当前剧集\n"
            "支持 .txt / .md / .docx\n"
            "可多选，多个文件内容会依次追加"
        )
        self._btn_import_script.clicked.connect(self._on_import_script_file)
        slay.addWidget(self._btn_import_script)
        splitter.addWidget(sbox)

        # ============ 右：分镜 ============
        sb_box = QGroupBox("分镜")
        sb_lay = QVBoxLayout(sb_box)
        self._storyboard_view = QPlainTextEdit(ep.storyboard or "（暂无分镜，点击【生成分镜】按钮生成）")
        self._storyboard_view.setReadOnly(True)
        self._storyboard_view.setStyleSheet("background: #1E1E1E;")
        self._storyboard_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        sb_lay.addWidget(self._storyboard_view, 1)
        # 状态行
        self._sb_status = QLabel(self._storyboard_status_text(ep))
        self._sb_status.setStyleSheet("color: #666;")
        # 4 个操作键放在分镜下方
        self._btn_gen_storyboard = QPushButton("🎬 生成分镜")
        self._btn_gen_storyboard.setFixedHeight(32)
        self._btn_open_storyboard = QPushButton("📄 打开文件")
        self._btn_open_storyboard.setFixedHeight(32)
        self._btn_reextract_storyboard = QPushButton("♻️ 重新生成分镜")
        self._btn_reextract_storyboard.setFixedHeight(32)
        self._btn_reextract_storyboard.setToolTip(
            "用同一剧本重新跑一次 LLM，覆盖当前分镜。"
        )
        self._btn_clear_storyboard = QPushButton("🗑️ 清空分镜")
        self._btn_clear_storyboard.setFixedHeight(32)
        self._btn_clear_storyboard.setToolTip(
            "只清空当前剧集的分镜（不动剧集本身、不重跑 LLM）。\n"
            "复刻自原软件 /clear-storyboard 接口。"
        )
        sb_btn_row = QHBoxLayout()
        sb_btn_row.addWidget(self._btn_gen_storyboard)
        sb_btn_row.addWidget(self._btn_reextract_storyboard)
        sb_btn_row.addWidget(self._btn_open_storyboard)
        sb_btn_row.addWidget(self._btn_clear_storyboard)
        sb_btn_row.addStretch()
        sb_btn_row.addWidget(self._sb_status)
        sb_lay.addLayout(sb_btn_row)
        splitter.addWidget(sb_box)

        # 等宽,跟窗口同步
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([1, 1])
        outer.addWidget(splitter, 1)

        # 信号
        self._btn_gen_storyboard.clicked.connect(self._on_generate_storyboard)
        self._btn_reextract_storyboard.clicked.connect(self._on_generate_storyboard)
        self._btn_open_storyboard.clicked.connect(self._on_open_storyboard_file)
        self._btn_clear_storyboard.clicked.connect(self._on_clear_storyboard)

        # v0.7.8.49:cache 分镜 tab,同 ep 切回直接复用 widget
        self._episode_detail_cache = (ep.id, w)
        self._replace_tab(1, w, "🎬 分镜")

    def _show_prompt_tab(self, ep: Episode, project: Optional[Project]) -> None:
        """提示词 Tab 内容。

        v0.7.8.37:自己套 QScrollArea(避免 holder 双层)。
        v0.7.8.37i:cache 复用,避免 prompt 文本(QPlainTextEdit)
        每次切回都重建(scroll 跳顶,编辑位置丢失)。
        v0.7.8.49:cache 命中 → _replace_tab(已判断"同 widget 不重建")。
        """
        # v0.7.8.37i:cache 命中 → 复用
        cache_key = (ep.id, hash(ep.prompt or ""))
        if self._prompt_tab_cache and self._prompt_tab_cache[0] == cache_key:
            self._replace_tab(2, self._prompt_tab_cache[1], "📝 提示词")
            return

        w = QScrollArea()
        w.setWidgetResizable(True)
        w.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        outer = QVBoxLayout(container)

        head = QGroupBox()
        hlay = QVBoxLayout(head)
        hlay.addWidget(QLabel(f"<h2 style='margin:0'>第{ep.episode_num}集：视频提示词</h2>"))
        hint = QLabel("<i>需要先生成分镜，然后才能生成视频提示词</i>")
        hint.setStyleSheet("color: #888;")
        hlay.addWidget(hint)
        outer.addWidget(head)

        # 提示词操作区
        box = QGroupBox("视频提示词")
        lay = QVBoxLayout(box)
        btn_row = QHBoxLayout()
        self._btn_gen_prompt = QPushButton("📝 生成视频提示词")
        self._btn_gen_prompt.setFixedHeight(32)
        self._btn_open_prompt = QPushButton("📄 打开文件")
        self._btn_open_prompt.setFixedHeight(32)
        # v0.6.18 #6：🗑️ 清空 prompt 按钮（一键清空当前提示词，便于重新生成）
        self._btn_clear_prompt = QPushButton("🗑️ 清空 prompt")
        self._btn_clear_prompt.setFixedHeight(32)
        self._btn_clear_prompt.setToolTip(
            "清空当前剧集的提示词（连同文件 + db 字段），便于重新生成。"
        )
        # v0.7.8.32：取消手动"📤 推送提示词到视频"按钮,改为新生成 prompt 时
        # 自动推送(在 VideoPromptTask 完成回调里调 _auto_push_prompt_to_segments),
        # 用户无需再手动点。按钮区也清爽。
        self._prompt_status = QLabel(self._prompt_status_text(ep))
        self._prompt_status.setStyleSheet("color: #666;")
        btn_row.addWidget(self._btn_gen_prompt)
        btn_row.addWidget(self._btn_open_prompt)
        btn_row.addWidget(self._btn_clear_prompt)
        btn_row.addStretch()
        btn_row.addWidget(self._prompt_status)
        lay.addLayout(btn_row)
        self._prompt_view = QPlainTextEdit(ep.prompt or "（暂无提示词）")
        self._prompt_view.setReadOnly(True)
        self._prompt_view.setStyleSheet("background: #1E1E1E;")  # v0.7.0：跟随暗色主题
        self._prompt_view.setMinimumHeight(320)
        lay.addWidget(self._prompt_view, 1)
        outer.addWidget(box, 1)

        self._btn_gen_prompt.clicked.connect(self._on_generate_prompt)
        self._btn_open_prompt.clicked.connect(self._on_open_prompt_file)
        self._btn_clear_prompt.clicked.connect(self._on_clear_prompt)

        outer.addStretch(1)
        w.setWidget(container)
        # v0.7.8.37i:存 cache
        self._prompt_tab_cache = (cache_key, w)
        self._replace_tab(2, w, "📝 提示词")

    def _storyboard_status_text(self, ep: Episode) -> str:
        if not ep.storyboard:
            return "状态: 未生成"
        return f"状态: 已生成 ({len(ep.storyboard)} 字)"

    def _prompt_status_text(self, ep: Episode) -> str:
        if not ep.prompt:
            return "状态: 未生成"
        return f"状态: 已生成 ({len(ep.prompt)} 字)"

    def _video_status_text(self, ep: Episode) -> str:
        """v0.6.19：解析 video_segments JSON 字段统计段数。"""
        if not ep.video_segments:
            return "状态: 未生成"
        env = parse_video_segments(ep.video_segments, ep_num=ep.episode_num, ep_title=ep.title)
        segs = env.get("segments", [])
        if not segs:
            return "状态: 未生成"
        n_ready = sum(1 for s in segs if s.get("video_status") == VIDEO_STATUS_READY)
        return f"状态: 共 {len(segs)} 段，已生成 {n_ready} 段"

    def _show_video_tab(self, ep: Episode, project: Optional[Project]) -> None:
        """视频 Tab 内容（剧集级，第 3 个 Tab）。

        v0.7.8.37:自己套 QScrollArea(避免 holder 双层)。
        v0.7.8.37i:缓存 widget —— 23 段 × 30 widget/段 ≈ 700 widget,
        每次 _show_video_tab 都新建 + deleteLater 会非常卡,
        且 _replace_tab removeTab+insertTab 会让 QStackedWidget 整个
        重建,scroll 跳顶,tab 看起来"变形"。

        策略:cache key = (ep.id, video_segments 字符串 hash)。
        切回同一剧集 / 同段数据 → 直接复用旧 QScrollArea,
        不重建 700 widget,scroll 位置也保留。
        """
        # v0.7.8.37i:cache 命中 → 复用
        # cache_key 用 hash 而不是完整字符串,避免 39KB 字符串每次
        # _show_video_tab 都复制进 tuple。
        cache_key = (ep.id, hash(ep.video_segments or ""), hash(ep.prompt or ""))
        if self._video_tab_cache and self._video_tab_cache[0] == cache_key:
            self._replace_tab(3, self._video_tab_cache[1], "🎥 视频")
            return

        w = QScrollArea()
        w.setWidgetResizable(True)
        w.setFrameShape(QFrame.Shape.NoFrame)
        container = QWidget()
        outer = QVBoxLayout(container)

        # 标题
        head = QGroupBox()
        hlay = QVBoxLayout(head)
        hlay.addWidget(QLabel(f"<h2 style='margin:0'>第{ep.episode_num}集：视频生成</h2>"))
        hint = QLabel("<i>需要先生成视频提示词，然后才能生成视频。产物落盘到 outputs/&lt;项目名&gt;/。</i>")
        hint.setStyleSheet("color: #888;")
        hint.setWordWrap(True)
        hlay.addWidget(hint)
        outer.addWidget(head)

        # 视频操作区
        box = QGroupBox("视频")
        lay = QVBoxLayout(box)
        # v0.7.8.39【视频生成链路 RadioButton】：二选一互斥
        #  - API 生成（走 video_api_configs[active] 的 OpenAI 兼容 HTTP）
        #  - 浏览器生成（走 dreamina.exe + OAuth 登录）
        # 选哪条链路，_on_generate_single_video 调对应 task（VideoTask 路由）
        link_row = QHBoxLayout()
        link_row.addWidget(QLabel("<b>生成链路：</b>"))
        self._rb_link_api = QRadioButton("📡 API 生成")
        self._rb_link_web = QRadioButton("🖥 浏览器生成")
        # 互斥：同 QButtonGroup
        self._link_btn_group = QButtonGroup(self)
        self._link_btn_group.addButton(self._rb_link_api, 1)  # id=1 → api
        self._link_btn_group.addButton(self._rb_link_web, 2)  # id=2 → web
        # 默认 web（兼容 v0.7.8.38 之前行为）
        if self._video_link_mode == "api":
            self._rb_link_api.setChecked(True)
        else:
            self._rb_link_web.setChecked(True)
        self._rb_link_api.toggled.connect(self._on_link_mode_changed)
        self._rb_link_web.toggled.connect(self._on_link_mode_changed)
        link_row.addWidget(self._rb_link_api)
        link_row.addWidget(self._rb_link_web)
        link_row.addStretch()
        # v0.7.8.43：删状态标签 + ⚙ API 设置按钮（用户反馈"多余、点也没用、视频 API
        # 设置界面已经有相关功能"）
        lay.addLayout(link_row)

        btn_row = QHBoxLayout()
        self._btn_gen_video = QPushButton("🎥 生成视频")
        self._btn_gen_video.setFixedHeight(32)
        self._btn_open_video_dir = QPushButton("📂 打开视频目录")
        self._btn_open_video_dir.setFixedHeight(32)
        # v0.6.19：3 个段操作按钮
        self._btn_split_segment = QPushButton("✂️ 按分镜切")
        self._btn_split_segment.setFixedHeight(32)
        self._btn_split_segment.setToolTip("把第 1 段按「## 分镜N」标记切分成多段")
        self._btn_add_segment = QPushButton("➕ 加空段")
        self._btn_add_segment.setFixedHeight(32)
        # v0.7.8.77【提取提示词到视频按钮】:新生成的 prompt 因 v0.7.8.34
        # 保护不会自动 push 到 video_segments,user 主动按这个按钮时强制
        # 覆盖(v0.7.8.34 保护跳过)。user 主动行为 = 显式同意覆盖,不算
        # 误冲手动编辑。
        self._btn_extract_prompt = QPushButton("📥 提取提示词到视频")
        self._btn_extract_prompt.setFixedHeight(32)
        self._btn_extract_prompt.setToolTip(
            "把当前剧集的提示词(已生成)按 🎞️ Segment 切分,覆盖到视频页。\n"
            "适用场景:重新生成提示词后,想用新提示词替换当前视频页内容。\n"
            "注意:会覆盖当前 video_segments(包括已生成的视频段卡 text),"
            "已生成的 video 文件不会被删除,但段卡 text 会被新提示词替换。"
        )
        self._btn_extract_prompt.clicked.connect(self._on_extract_prompt_to_video)
        # v0.7.8.40【删冗余按钮】：v0.6.22 的 🌐 浏览器生成按钮跟 v0.7.8.39
        # 新加的【🖥 浏览器生成】RadioButton 重复（链路选择器是统一入口），
        # web_video_cmd_template 留作 web 链路的兜底命令模板，但入口被
        # RadioButton 接管。**删**这个按钮，按链路选择器走。
        self._video_status = QLabel(self._video_status_text(ep))
        self._video_status.setStyleSheet("color: #666;")
        btn_row.addWidget(self._btn_gen_video)
        btn_row.addWidget(self._btn_split_segment)
        btn_row.addWidget(self._btn_add_segment)
        btn_row.addWidget(self._btn_extract_prompt)
        btn_row.addWidget(self._btn_open_video_dir)
        btn_row.addStretch()
        btn_row.addWidget(self._video_status)
        lay.addLayout(btn_row)

        # v0.6.19：段列表（取代旧的纯文本列表）
        env = parse_video_segments(ep.video_segments, ep_num=ep.episode_num, ep_title=ep.title)
        segs = env.get("segments", [])
        if segs:
            seg_box = QGroupBox(f"已生成的视频  ({len(segs)} 段)")
            seg_lay = QVBoxLayout(seg_box)
            # v0.7.8.36:移除换位(↑↓)/合并(checkbox) — 视频没什么可合并/换位的
            for idx, s in enumerate(segs):
                seg_lay.addWidget(self._build_segment_card(s, idx, len(segs)))
            seg_lay.addStretch(1)
            lay.addWidget(seg_box)
        else:
            empty_lbl = QLabel("<i>暂无视频段。先点【生成视频】或【➕ 加空段】开始。</i>")
            empty_lbl.setStyleSheet("color: #888; padding: 12px;")
            lay.addWidget(empty_lbl)

        outer.addWidget(box, 1)

        # 信号
        self._btn_gen_video.clicked.connect(self._on_generate_video)
        self._btn_open_video_dir.clicked.connect(self._on_open_video_dir)
        self._btn_split_segment.clicked.connect(self._on_split_first_segment)
        self._btn_add_segment.clicked.connect(self._on_add_empty_segment)
        # v0.7.8.40：删 _btn_web_video 信号（按钮已删，避免 AttributeError）

        outer.addStretch(1)
        w.setWidget(container)
        # v0.7.8.37i:存 cache(下次切回同剧集复用)
        self._video_tab_cache = (cache_key, w)
        log.info("_show_video_tab: 重建 23 段卡片, w_id=%s", id(w))
        self._replace_tab(3, w, "🎥 视频")

    def _build_segment_card(self, seg: dict, idx: int, total: int) -> QWidget:
        """v0.7.8.36:段卡片 5 列大块布局,移除换位/合并(用户要求)。

        列布局:
          [1] 序号 (60px) - #N + 🗑删除
          [2] 提示词 (350px 可伸展) - 标题(可编辑) + prompt 文本(可滚动)
          [3] 资产 (160px) - 该段 @xxx 引用列表
          [4] 参数 (140px) - 4 个 QComboBox: model / duration / ratio / quality
          [5] 生成 (180px) - 状态 + ▶ 生成按钮 + 视频缩略图(内嵌)+ 打开 + 音频

        段高约 220px,每段是一张大块卡片。
        """
        seg_id = seg.get("id", "")
        title = seg.get("title") or f"段{idx + 1}"
        # v0.7.8.60:老数据兼容 — 如果 title 没有 🎞️ Segment 前缀,根据 idx
        # 自动补。v0.7.8.58 之前生成的 video_segments 没带前缀,渲染时
        # 用户看不到段序号。这里补完后下次 _on_update_seg_prop 保存时
        # 自动持久化带前缀的 title
        if not (title.startswith("🎞️ Segment") or title.startswith("🎞️Segment")):
            title = f"🎞️ Segment {idx + 1} - {title}"
        text = seg.get("text", "")
        status = seg.get("video_status", "pending")
        duration = seg.get("duration", 8)
        model = seg.get("model", "seedance2.0fast")
        ratio = seg.get("ratio", "16:9")
        quality = seg.get("quality", "720p")
        video_path = seg.get("video_path", "")

        # ---------- 外层卡片 ----------
        card = QFrame()
        card.setFrameShape(QFrame.Shape.StyledPanel)
        card.setStyleSheet(
            "QFrame { background: #2A2A2A; border: 1px solid #3F3F46;"
            " border-radius: 6px; padding: 0; margin: 4px 0; }"
            "QFrame:hover { border-color: #5B9BFF; }"
        )
        # v0.7.8.60【段卡高度 + 缩略图调整】:v0.7.8.37k 改回 220 防止 tab 太长,
        # 但 220 装不下 status(24) + 缩略图(160) + 三个按钮(28+24+24)+ spacing
        # ≈ 264px,导致按钮压到缩略图上。提到 280,缩略图缩到 220x124(16:9)
        # 总高度 ≈ 24+124+28+24+4*4 = 216 < 280,留余量。
        # 23 段 tab 高度 = 23*280 = 6440px(用户能接受,先解决遮挡)
        card.setMinimumHeight(280)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        outer = QHBoxLayout(card)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        # ========== [1] 序号/操作列 60px ==========
        col1 = QVBoxLayout()
        col1.setSpacing(4)
        col1.setAlignment(Qt.AlignmentFlag.AlignTop)
        # 序号
        n_lbl = QLabel(f"<b>#{idx + 1}</b>")
        n_lbl.setStyleSheet("color: #5B9BFF; font-size: 18px;")
        n_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col1.addWidget(n_lbl, 0, Qt.AlignmentFlag.AlignHCenter)
        col1.addStretch()
        # 删除按钮
        btn_del = QPushButton("🗑")
        btn_del.setFixedSize(28, 24)
        btn_del.setToolTip("删除段")
        btn_del.clicked.connect(lambda _checked=False, _id=seg_id: self._on_remove_segment(_id))
        col1.addWidget(btn_del, 0, Qt.AlignmentFlag.AlignHCenter)

        col1_w = QWidget()
        col1_w.setLayout(col1)
        col1_w.setFixedWidth(60)
        outer.addWidget(col1_w)

        # 分隔线
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: #3F3F46;")
        outer.addWidget(sep1)

        # ========== [2] 提示词列 350px(可伸展) ==========
        col2 = QVBoxLayout()
        col2.setSpacing(4)
        # v0.7.8.78【删段卡标题栏】:user 反馈段卡顶部的 QLineEdit 标题栏
        # ("Segment N · xxx") 不需要,直接看 prompt text 即可。标题字段
        # (seg.title) 仍保留在 db 里,只是不在 UI 显示 + 不再可编辑。
        # 后续 user 想恢复标题编辑,解注释下面 title_edit 块即可。
        #
        # title_edit = QLineEdit(title)
        # title_edit.setStyleSheet(
        #     "QLineEdit { background: #1E1E1E; color: #e0e0e0;"
        #     " border: 1px solid #3F3F46; border-radius: 3px; padding: 4px;"
        #     " font-size: 13px; font-weight: 600; }"
        #     "QLineEdit:focus { border-color: #5B9BFF; }"
        # )
        # title_edit.setPlaceholderText("段标题(可编辑)")
        # title_edit.editingFinished.connect(
        #     lambda _id=seg_id, _w=title_edit: self._on_update_seg_prop(_id, "title", _w.text().strip())
        # )
        # col2.addWidget(title_edit)
        # v0.7.8.37k:回退到 v0.7.8.36 的 QPlainTextEdit(内嵌显示完整 prompt,
        # 卡片内 setMaximumHeight(160) 限制 + 自身滚动条)。
        # 用户反馈"展开 dialog 不方便",要求直接在卡片内看完整文本。
        # 之前 v0.7.8.36 用 QPlainTextEdit 一直 OK,没反馈卡 —— 卡是
        # v0.7.8.35 改 5 列大块卡片时 _build_segment_card 内的 QPlainTextEdit
        # + 4 QCheckBox + 4 QComboBox 等 widget 数量变多引起的,
        # 而 v0.7.8.36 之前的"单行横排"卡片根本没完整 prompt 显示。
        text_view = QPlainTextEdit(text or "（该段暂无 prompt 文本）")
        text_view.setReadOnly(True)
        text_view.setStyleSheet(
            "QPlainTextEdit { background: #1E1E1E; color: #c0c0c0;"
            " border: 1px solid #3F3F46; border-radius: 3px; padding: 4px;"
            " font-size: 11px; }"
        )
        # v0.7.8.79【删 maxHeight 160】:v0.7.8.37k 加 160 高度限制是想让
        # 23 段 tab 别太长(总高 23*160=3680),但导致卡片下方有 120px 空白
        # (卡片 280 - text 框 160 - margins)。user 反馈"框做大点,不要有
        # 那么多空位"。删 maxHeight,text_view stretch 1 自动占满 col2
        # (col2 高度 = 卡片 280 - outer margins 16 = 264),prompt 长出
        # scroll bar,短则 text 框 = 264 高但内部有空白(不可避免)。
        # 23 段 tab 总高 = 23*280 = 6440(跟 v0.7.8.37k 之前一样,user 能接受)。
        col2.addWidget(text_view, 1)
        col2_w = QWidget()
        col2_w.setLayout(col2)
        col2_w.setMinimumWidth(280)
        outer.addWidget(col2_w, 1)

        # 分隔线
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: #3F3F46;")
        outer.addWidget(sep2)

        # ========== [3] 资产列 160px ==========
        col3 = QVBoxLayout()
        col3.setSpacing(2)
        col3.setAlignment(Qt.AlignmentFlag.AlignTop)
        col3.addWidget(QLabel("<b>资产</b>"))
        assets = seg.get("assets", []) or []
        # v0.7.8.37g:如果 segment 没 assets 字段,从 seg["text"] 里的
        # [Asset Definitions] 段实时提取(老软件 server.py:402
        # extract_asset_sections 思路 + 新软件 prompt 格式 "资产名:@资产名")。
        # 避免 v0.7.8.35 之前 _auto_push_prompt_to_segments 分割 prompt 时
        # 没存 assets → 卡片显示"(无)"。不动 db,老 segments 立即生效。
        if not assets and seg.get("text"):
            assets = self._extract_assets_from_segment_text(seg.get("text", ""))
        if not assets:
            no_assets = QLabel("<i style='color:#888'>(无)</i>")
            col3.addWidget(no_assets)
        else:
            # 按 kind 分组显示,人物/场景/物品
            from collections import OrderedDict
            grouped: "OrderedDict[str, list]" = OrderedDict()
            for a in assets:
                a_name = a.get("name", "") if isinstance(a, dict) else str(a)
                a_kind = a.get("kind", "其他") if isinstance(a, dict) else "其他"
                grouped.setdefault(a_kind, []).append(a_name)
            kind_icons = {"人物": "👤", "场景": "🏞", "物品": "📦", "其他": "•"}
            for kind, names in grouped.items():
                icon = kind_icons.get(kind, "•")
                hdr = QLabel(f"{icon} <b>{kind}</b> ({len(names)})")
                hdr.setStyleSheet("color: #a0a0a0; font-size: 10px; padding-top: 2px;")
                col3.addWidget(hdr)
                for n in names:
                    cb_a = QCheckBox(f"@{n}")
                    # v0.7.8.37h:资产默认全选 —— 用户手动取消某个资产 = 该段视频
                    # 生成时不用该资产。复刻老软件"全选/部分选用"行为。
                    cb_a.setChecked(True)
                    cb_a.setStyleSheet("color: #c0c0c0; font-size: 11px;")
                    col3.addWidget(cb_a)
        col3.addStretch()
        col3_w = QWidget()
        col3_w.setLayout(col3)
        col3_w.setFixedWidth(160)
        outer.addWidget(col3_w)

        # 分隔线
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.VLine)
        sep3.setStyleSheet("color: #3F3F46;")
        outer.addWidget(sep3)

        # ========== [4] 参数列 140px ==========
        col4 = QVBoxLayout()
        col4.setSpacing(4)
        col4.setAlignment(Qt.AlignmentFlag.AlignTop)
        # v0.7.8.39【参数内容与链路的链接】：参数标题旁加 🔗 按钮，hover/click
        # 后弹小窗显示 model/ratio/duration/quality 各参数的具体来源链路。
        # 用户能一眼看出"参数 ↔ 链路"的对应关系。
        param_title_row = QHBoxLayout()
        param_title_row.setSpacing(2)
        param_title_row.addWidget(QLabel("<b>参数</b>"))
        param_title = QLabel("🔗")
        param_title.setToolTip(
            "参数内容与链路的链接：\n"
            "• model：API链路 → video_api_configs[active].saved_models；"
            "Web链路 → dreamina_models\n"
            "• ratio / duration / quality：始终在生视频界面设置，"
            "不走 settings dialog\n"
            "• 点击跳到【设置 → 🎬 视频 API】改 base_url / api_key / model"
        )
        param_title.setStyleSheet("color: #60a5fa; font-size: 12px;")
        param_title.setCursor(Qt.CursorShape.PointingHandCursor)
        param_title.mousePressEvent = (
            lambda _e, _id=seg_id: self._on_param_link_clicked(_id)
        )
        param_title_row.addWidget(param_title)
        param_title_row.addStretch()
        param_title_w = QWidget()
        param_title_w.setLayout(param_title_row)
        col4.addWidget(param_title_w)
        # v0.7.8.39【链路决定 model 列表来源】：
        # - web：dreamina_models（config 里）作为下拉项
        # - api：当前 video_api_configs[active].model（用户手动填的 1 个）
        # v0.7.8.42【不保存硬约束】：saved_models 不再使用，每次拉取的 fetched
        # 只在 settings dialog 期间显示，**不**留盘，所以视频卡片的 model_items
        # 不再读 saved_models。如果用户没在 settings 填 model，这里就是空。
        if self._video_link_mode == "api":
            api_cfg = None
            for c in self.config.video_api_configs:
                if c.get("id") == self.config.active_video_api_config_id:
                    api_cfg = c
                    break
            # v0.7.8.42：api_cfg.saved_models 已被 Config 清理（永远是 []）
            # model_items 只显示 api_cfg.model（用户在 settings 手动填的）
            model_items = []
            api_default = (api_cfg or {}).get("model", "") or ""
            cur_model = model or api_default
            if api_default:
                model_items = [api_default]
        else:
            model_items = list(self.config.dreamina_models or [])
            if not model_items:
                # 兜底：保留原 hard-coded 4 个（v0.7.8.38 之前）
                model_items = ["seedance2.0", "seedance2.0fast", "seedance2.0_vip", "seedance2.0fast_vip"]
            cur_model = model
        m_combo = QComboBox()
        for it in model_items:
            m_combo.addItem(it)
        # 当前 model 永远保留（v0.7.8.11 无兜底硬约束），setEditText 即可
        if cur_model:
            m_combo.setCurrentText(cur_model)
        m_combo.setStyleSheet(self._seg_combo_style())
        m_combo.currentTextChanged.connect(
            lambda v, _id=seg_id: self._on_update_seg_prop(_id, "model", v)
        )
        col4.addWidget(m_combo)
        # duration
        d_combo = QComboBox()
        d_combo.addItems(["4", "5", "6", "7", "8", "9", "10", "12", "15"])
        d_combo.setCurrentText(str(duration))
        d_combo.setStyleSheet(self._seg_combo_style())
        d_combo.currentTextChanged.connect(
            lambda v, _id=seg_id: self._on_update_seg_prop(_id, "duration", int(v))
        )
        col4.addWidget(d_combo)
        # ratio
        r_combo = QComboBox()
        r_combo.addItems(["16:9", "9:16", "1:1", "4:3", "3:4"])
        r_combo.setCurrentText(ratio)
        r_combo.setStyleSheet(self._seg_combo_style())
        r_combo.currentTextChanged.connect(
            lambda v, _id=seg_id: self._on_update_seg_prop(_id, "ratio", v)
        )
        col4.addWidget(r_combo)
        # quality
        q_combo = QComboBox()
        q_combo.addItems(["720p", "1080p", "480p"])
        q_combo.setCurrentText(quality)
        q_combo.setStyleSheet(self._seg_combo_style())
        q_combo.currentTextChanged.connect(
            lambda v, _id=seg_id: self._on_update_seg_prop(_id, "quality", v)
        )
        col4.addWidget(q_combo)
        col4_w = QWidget()
        col4_w.setLayout(col4)
        col4_w.setFixedWidth(140)
        outer.addWidget(col4_w)

        # 分隔线
        sep4 = QFrame()
        sep4.setFrameShape(QFrame.Shape.VLine)
        sep4.setStyleSheet("color: #3F3F46;")
        outer.addWidget(sep4)

        # ========== [5] 生成列 320px(v0.7.8.60:布局重排防遮挡) ==========
        # v0.7.8.60【布局重排】:v0.7.8.37e 把缩略图改成 280x160 + 按钮全垂直堆叠,
        # 总高 24+28+160+24+24+16=276 超过卡片 220,按钮压到缩略图上。
        # 改为:状态(顶) → 缩略图 220x124(中) → 3 按钮水平排列(底)。
        # 总高 24+124+28+24+16=216 < 280,不再遮挡。
        col5 = QVBoxLayout()
        col5.setSpacing(4)
        col5.setAlignment(Qt.AlignmentFlag.AlignTop)
        # 状态(顶部)
        s_lbl = QLabel(self._seg_status_text(status))
        s_lbl.setStyleSheet(self._seg_status_color(status) + " font-weight: 600;")
        s_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col5.addWidget(s_lbl)
        # 视频缩略图(中部,v0.7.8.60: 280x160 → 220x124 保持 16:9)
        if video_path and status == VIDEO_STATUS_READY:
            p = Path(video_path)
            thumb = self._get_video_thumbnail(p)
            if thumb and thumb.exists():
                thumb_lbl = QLabel()
                thumb_lbl.setFixedSize(220, 124)
                thumb_lbl.setStyleSheet(
                    "QLabel { background: #1E1E1E; border: 1px solid #3F3F46;"
                    " border-radius: 3px; }"
                )
                thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                thumb_lbl.setToolTip(f"{p.name}\n点击预览")
                thumb_lbl.setCursor(Qt.CursorShape.PointingHandCursor)
                from PySide6.QtGui import QPixmap
                pix = QPixmap(str(thumb))
                if not pix.isNull():
                    thumb_lbl.setPixmap(
                        pix.scaled(220, 124, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
                    )
                thumb_lbl.mousePressEvent = lambda _ev, _p=video_path: self._preview_video(_p)
                col5.addWidget(thumb_lbl, 0, Qt.AlignmentFlag.AlignHCenter)
        # 按钮行(v0.7.8.60:三个按钮水平排列,不再垂直堆叠遮挡缩略图)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        # ▶ 生成按钮
        btn_gen = QPushButton("▶ 生成")
        btn_gen.setFixedHeight(26)
        btn_gen.setStyleSheet(
            "QPushButton { background: #5B9BFF; color: #fff; font-weight: 600;"
            " font-size: 11px; padding: 0 6px; }"
            "QPushButton:hover { background: #4A8AEE; }"
            "QPushButton:disabled { background: #555; color: #999; }"
        )
        btn_gen.setEnabled(status not in ("generating",))
        # v0.7.8.69【按钮 click 指纹】:之前 _on_generate_single_video 的 log
        # 加在 line 1848,如果 click 后 1739-1748 QMessageBox.warning 早返回就
        # 看不到 → 没法区分"click 没到"vs"click 到了但函数早返回"。
        # 这条 log **在 lambda 内**,点击发生瞬间写一次,**无路可逃**。
        def _on_btn_gen_clicked(_checked: bool, _id: str = seg_id) -> None:
            log.info(
                "btn_gen.clicked: seg_id=%s, btn_enabled=%s, "
                "cur_ep=%s, cur_proj=%s",
                _id, btn_gen.isEnabled(),
                getattr(self._current_episode, "id", None),
                getattr(self._current_project, "id", None),
            )
            self._on_generate_single_video(_id)
        btn_gen.clicked.connect(_on_btn_gen_clicked)
        btn_row.addWidget(btn_gen, 1)
        # 📂 打开(仅 ready 时显示)
        if video_path and status == VIDEO_STATUS_READY:
            btn_open = QPushButton("📂 打开")
            btn_open.setFixedHeight(26)
            btn_open.setStyleSheet(
                "QPushButton { background: #3F3F46; color: #e0e0e0; font-size: 11px;"
                " padding: 0 6px; }"
                "QPushButton:hover { background: #52525B; }"
            )
            btn_open.setToolTip(str(p))
            btn_open.clicked.connect(lambda _checked=False, _p=p: self._open_in_explorer(_p))
            btn_row.addWidget(btn_open, 1)
        # v0.7.8.61:删除"🎵 音频"按钮 — 用户反馈段级音频无意义,
        # 资产级音频才是生视频参考。audio_path 字段保留 schema 兼容老 db,
        # 但 UI 不再展示、不再允许用户编辑。
        btn_row_w = QWidget()
        btn_row_w.setLayout(btn_row)
        col5.addWidget(btn_row_w)
        col5_w = QWidget()
        col5_w.setLayout(col5)
        col5_w.setFixedWidth(280)
        outer.addWidget(col5_w)

        return card

    @staticmethod
    def _seg_combo_style() -> str:
        return (
            "QComboBox { background: #1E1E1E; color: #c0c0c0;"
            " border: 1px solid #3F3F46; border-radius: 3px; padding: 3px 6px;"
            " font-size: 11px; min-height: 18px; }"
            "QComboBox:hover { border-color: #5B9BFF; }"
        )

    @staticmethod
    def _extract_assets_from_segment_text(text: str) -> list:
        """v0.7.8.37g:从 segment text 的 [Asset Definitions] 段提取资产列表。

        老软件 server.py:402 extract_asset_sections 的思路,适配新软件
        自己 prompt 格式。新软件 seedance agent 输出的资产段格式是:
            [Asset Definitions]
            资产名:@资产名
            ...
        返回 [{"name": "...", "kind": "人物/场景/物品/其他"}, ...]。

        kind 推断规则(简单规则,够用):
          - 包含 宗/府/山/洞/场景/地/境/殿 → 场景
          - 包含 炉/剑/丹/法器/物/器/宝/珠 → 物品
          - 其他 → 人物(角色名通常是2-4字人名,无明显物品/场景关键词)
        """
        if not text:
            return []
        # [Asset Definitions] 段,到下一个 [xxx] 或 段尾
        m = re.search(r'\[Asset Definitions\](.*?)(?=\n\[|\Z)', text, re.DOTALL)
        if not m:
            return []
        block = m.group(1)
        assets = []
        seen = set()  # 去重
        scene_kw = "宗府山洞场景地境殿观台塔林谷池湖海城池"
        item_kw = "炉剑丹法器物宝珠镜符卷轴旗令"
        for line in block.split('\n'):
            line = line.strip()
            if not line:
                continue
            # 格式: "资产名:@资产名" 或 "资产名：@资产名" (全/半角冒号都行)
            m2 = re.match(r'^(.+?)\s*[：:]\s*@(.+?)$', line)
            if not m2:
                continue
            name = m2.group(2).strip()
            if not name or name in seen:
                continue
            seen.add(name)
            # kind 推断
            kind = "人物"
            for c in name:
                if c in scene_kw:
                    kind = "场景"
                    break
            if kind == "人物":
                for c in name:
                    if c in item_kw:
                        kind = "物品"
                        break
            assets.append({"name": name, "kind": kind})
        return assets

    @staticmethod
    def _get_video_thumbnail(video_path: Path) -> Optional[Path]:
        """v0.7.8.36:抽视频第一帧作为缩略图,缓存到 <video>.thumb.png。

        ffmpeg 抽 1 帧约 100-200ms,缓存后秒返回。如果 ffmpeg 不可用返回 None。
        """
        if not video_path.exists():
            return None
        thumb = video_path.with_suffix(".thumb.png")
        if thumb.exists() and thumb.stat().st_mtime > video_path.stat().st_mtime:
            return thumb  # 缓存有效
        try:
            import subprocess
            r = subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error",
                    "-ss", "0", "-i", str(video_path),
                    "-vframes", "1", "-vf", "scale=160:-1",
                    str(thumb),
                ],
                capture_output=True, timeout=10,
            )
            if r.returncode == 0 and thumb.exists():
                return thumb
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass
        return None

    def _on_show_full_prompt(self, text: str, title: str) -> None:
        """v0.7.8.37j:展开完整 prompt —— 弹 QDialog(QPlainTextEdit)。

        段卡片里只显示前 200 字截断,完整 prompt 文本太大,QPlainTextEdit
        启动开销 ~50ms × 23 段 = 1+ 秒。改成点击"📖 展开"才创建 QPlainTextEdit。
        """
        from PySide6.QtWidgets import QDialog, QVBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle(f"完整 prompt - {title}")
        dlg.resize(900, 700)
        lay = QVBoxLayout(dlg)
        view = QPlainTextEdit(text)
        view.setReadOnly(True)
        view.setStyleSheet(
            "QPlainTextEdit { background: #1E1E1E; color: #d0d0d0;"
            " border: 1px solid #3F3F46; border-radius: 4px; padding: 8px;"
            " font-size: 12px; font-family: 'Consolas', 'Courier New', monospace; }"
        )
        lay.addWidget(view)
        dlg.exec()

    def _on_link_mode_changed(self) -> None:
        """v0.7.8.39：用户切换 API / Web 链路 RadioButton。
        v0.7.8.43：删状态标签更新代码（标签已删）。
        """
        if self._rb_link_api.isChecked():
            self._video_link_mode = "api"
        else:
            self._video_link_mode = "web"
        log.info("视频生成链路切换: %s", self._video_link_mode)

    def _on_param_link_clicked(self, seg_id: str) -> None:
        """v0.7.8.39【参数内容与链路的链接】：点参数 col4 旁的 🔗 → 弹小窗
        说明 4 个参数的具体来源（链路 + config 字段），并提供"跳到设置"按钮。
        v0.7.8.42：api 链路 model_src 文案更新——saved_models 不再使用。
        """
        if self._video_link_mode == "api":
            api_cfg = None
            for c in self.config.video_api_configs:
                if c.get("id") == self.config.active_video_api_config_id:
                    api_cfg = c
                    break
            api_name = (api_cfg or {}).get("name", "")
            api_url = (api_cfg or {}).get("base_url", "")
            api_model = (api_cfg or {}).get("model", "")
            # v0.7.8.42：saved_models 不再使用，model_src 只看 api_cfg.model
            model_src = f"video_api_configs[active={api_name!r}].model（{api_model!r}）"
            model_note = (
                "\n"
                f"  ⚠ 拉取列表**不**保存（v0.7.8.42 不保存硬约束）\n"
                f"  ⚠ 每次生视频前需要重新拉取（点设置里的 🔄 拉取）"
            )
        else:
            api_name = ""
            api_url = ""
            model_src = f"config/hermes_api.json · dreamina_models（{len(self.config.dreamina_models or [])} 个）"
            model_note = ""
        # 弹小窗
        dlg = QDialog(self)
        dlg.setWindowTitle("参数内容与链路的链接")
        dlg.resize(540, 360)
        dlg_v = QVBoxLayout(dlg)
        dlg_v.setContentsMargins(16, 16, 16, 16)
        dlg_v.setSpacing(10)

        # 顶部：当前链路
        if self._video_link_mode == "api":
            link_title = f"📡 当前链路：API 生成"
            link_sub = f"  · base_url = {api_url or '(未配)'}"
        else:
            link_title = "🖥 当前链路：浏览器生成"
            link_sub = f"  · dreamina.exe = {self.config.dreamina_exe or '(未配)'}"
        link_lbl = QLabel(f"<b>{link_title}</b><br><span style='color:#888;font-size:11px;'>{link_sub}</span>")
        link_lbl.setWordWrap(True)
        dlg_v.addWidget(link_lbl)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        dlg_v.addWidget(sep1)

        # 4 个参数来源
        rows = [
            ("model", model_src, "走链路 active 视频 API config / dreamina_models"),
            ("ratio", "始终在本卡片里设置", "16:9 / 9:16 / 1:1 / 4:3 / 3:4（v0.7.8.38.2 下放）"),
            ("duration", "始终在本卡片里设置", "4-15 秒（v0.7.8.38.2 下放）"),
            ("resolution / quality", "始终在本卡片里设置", "480p / 720p / 1080p（v0.7.8.38.2 下放）"),
        ]
        for name, src, detail in rows:
            row_w = QWidget()
            row_l = QVBoxLayout(row_w)
            row_l.setContentsMargins(0, 0, 0, 0)
            row_l.setSpacing(2)
            row_l.addWidget(QLabel(f"<b>{name}</b>"))
            row_l.addWidget(QLabel(f"  来源: {src}"))
            row_l.addWidget(QLabel(f"  <span style='color:#888;font-size:11px;'>{detail}</span>"))
            # v0.7.8.42：api 链路 model 加上"不保存"提示
            if name == "model" and model_note:
                row_l.addWidget(QLabel(
                    f"  <span style='color:#fbbf24;font-size:11px;'>{model_note}</span>"
                ))
            dlg_v.addWidget(row_w)

        dlg_v.addStretch()

        # v0.7.8.43：删"跳到设置"按钮（用户反馈"多余、点也没用、视频 API
        # 设置界面已经有相关功能"），只保留关闭按钮
        btn_close = QPushButton("关闭")
        btn_close.clicked.connect(dlg.accept)
        dlg_v.addWidget(btn_close)
        dlg.exec()

    def _on_update_seg_prop(self, seg_id: str, field: str, value) -> None:
        """v0.7.8.35:段属性被编辑(model / duration / ratio / quality / title),
        立即写回 db 并保存,无需"保存"按钮。
        """
        if not self._current_episode:
            return
        env = parse_video_segments(
            self._current_episode.video_segments or "",
            ep_num=self._current_episode.episode_num,
            ep_title=self._current_episode.title,
        )
        updated = False
        for s in env.get("segments", []):
            if s.get("id") == seg_id:
                s[field] = value
                updated = True
                break
        if not updated:
            log.warning("_on_update_seg_prop: seg_id=%s 未找到,跳过", seg_id)
            return
        raw = dump_video_segments(env)
        self.db.update_episode(self._current_episode.id, video_segments=raw)
        # 同步内存
        ep = self.db.get_episode(self._current_episode.id)
        if ep:
            self._current_episode = ep
        log.info("段属性更新: seg=%s %s=%r", seg_id, field, value)

    def _resolve_seg_reference_image(self, seg: Optional[dict]) -> Optional[Path]:
        """v0.7.8.64:从段的 assets 引用查 db.assets 拿真实参考图。

        seg.assets 里只存 {name, kind:"asset"} 名字引用(没有 image_path),
        必须用 name 去 db.assets 表查 (name, kind) → Asset.image_path。

        v0.7.8.63 fallback 规则(用户原话:没选过的默认就是最新生成的图):
        1. db.assets.image_path 有效 → 用它(用户⭐选定的,或生图自动写的)
        2. image_path 为空/文件不存在 → fallback 到该资产目录下 mtime 最新的图
           (list_asset_files 已经按 mtime 倒序排好)
        优先 character 类 → scene → prop → object。

        v0.7.8.64 强化诊断:每一步匹配结果都打 log,定位失效点。
        v0.7.8.66 修:状态栏 log 被刷新覆盖 → 改写文件
        `outputs/<项目>/logs/reference_image_<ts>.log` 持久化完整诊断。

        v0.7.8.71【bugfix】:_safe_filename 之前直接调用没 import,
        在 _flush_log (line 1593) / _fallback_latest (line 1678) 内抛
        NameError,导致 #2 段 click 后主线程 silent 死锁,user 看到
        "诊断一下就没事了"。这里显式 import 一次,两个 inner function 都能用。
        """
        from core.generators import _safe_filename  # v0.7.8.71 bugfix
        # v0.7.8.66:累积 log 行,最后一次性写文件(状态栏会被刷新覆盖)
        _log_lines: list = []

        def _emit(msg: str) -> None:
            """同时打状态栏 + 累积到 log 列表(末尾写文件)。"""
            _log_lines.append(msg)
            self.status_msg.setText(msg)

        def _flush_log() -> Path:
            """v0.7.8.66:把累积的 log 写文件,返回 log 文件路径。"""
            if not self._current_project:
                return Path()
            from datetime import datetime as _dt
            log_dir = (
                self.config.outputs_dir
                / _safe_filename(self._current_project.name)
                / "logs"
            )
            log_dir.mkdir(parents=True, exist_ok=True)
            ts = _dt.now().strftime("%Y%m%d_%H%M%S")
            log_file = log_dir / f"reference_image_{ts}.log"
            try:
                log_file.write_text(
                    "\n".join(_log_lines) + "\n", encoding="utf-8"
                )
            except OSError as e:
                self.status_msg.setText(f"⚠️ log 写盘失败: {e}")
            return log_file

        _emit(f"🔍 [诊断] helper 开始: 项目={self._current_project.name if self._current_project else 'None'}")
        if not seg or not self._current_project:
            _emit("🔍 [诊断] helper: seg 或 current_project 为空 → 直接 None")
            log_file = _flush_log_async() or Path()
            _emit(f"📄 完整 log: {log_file}")
            return None
        seg_assets = seg.get("assets") or []
        if not seg_assets:
            # v0.7.8.67【懒解析】:旧 envelope 段 assets 是空列表(早期 _auto_push_prompt_to_segments
            # 因"尊重用户手动编辑"跳过重写,或老数据生成时就没写),从 seg.text 的
            # [Asset Definitions] 块 @xxx 引用里提取资产名。复刻 _auto_push_prompt_to_segments:2604。
            text = seg.get("text", "") or ""
            extracted = self._extract_assets_from_segment_text(text)
            if extracted:
                # 映射 kind: 人物→character, 场景→scene, 物品→prop(对齐 db.assets.kind)
                _kind_map = {"人物": "character", "场景": "scene", "物品": "prop"}
                seg_assets = [
                    {
                        "name": a["name"],
                        "kind": _kind_map.get(a.get("kind", ""), "asset"),
                    }
                    for a in extracted
                ]
                _emit(
                    f"🔍 [诊断] helper: seg.assets 空,懒解析 text 得到 "
                    f"{len(seg_assets)} 条资产: {[a['name'] for a in seg_assets]}"
                )
            else:
                _emit("🔍 [诊断] helper: seg.assets 是空列表 → 直接 None")
                _emit(f"   seg keys: {list(seg.keys()) if seg else 'N/A'}")
                log_file = _flush_log()
                _emit(f"📄 完整 log: {log_file}")
                return None
        try:
            project_assets = self.db.list_assets(self._current_project.id)
        except Exception as e:
            _emit(f"🔍 [诊断] helper: list_assets 异常 {e} → None")
            log_file = _flush_log()
            _emit(f"📄 完整 log: {log_file}")
            return None
        # v0.7.8.64:打整个项目所有资产,看真实数据
        _emit(
            f"🔍 [诊断] 项目所有资产 {len(project_assets)} 条, "
            f"data=[{[(a.name, a.kind, '✓' + Path(a.image_path).name if a.image_path else '✗空') for a in project_assets]}]"
        )
        # 索引: (name, kind) → Asset,大小写不敏感
        idx_exact: Dict[tuple, object] = {
            (a.name, a.kind): a for a in project_assets
        }
        idx_lower: Dict[tuple, object] = {
            (a.name.lower(), a.kind.lower()): a for a in project_assets
        }
        name_to_assets: Dict[str, list] = {}
        for a in project_assets:
            name_to_assets.setdefault(a.name, []).append(a)
        name_to_assets_lower: Dict[str, list] = {
            k.lower(): v for k, v in name_to_assets.items()
        }

        def _fallback_latest(asset_name: str) -> Optional[Path]:
            """v0.7.8.63:db.image_path 失效时,扫资产目录拿 mtime 最新图。

            v0.7.8.65 强化:多层级 fallback
            1) 找安全目录名(safe_asset_dir_name)
            2) 模糊搜(原名 / 安全名 / 名字片段)
            3) 扫整个 outputs/<项目>/assets/ 下匹配名字的目录
            """
            try:
                from core.asset_browser import find_asset_dir, list_asset_files
                proj_assets_root = (
                    self.config.outputs_dir
                    / _safe_filename(self._current_project.name)
                    / "assets"
                )
                # 1) 标准目录
                asset_dir = find_asset_dir(
                    self.config.outputs_dir,
                    self._current_project.name,
                    asset_name,
                )
                _emit(
                    f"🔍 [诊断] helper: fallback 1) 找目录 {asset_dir} (exists={asset_dir.exists()})"
                )
                files = list_asset_files(asset_dir) if asset_dir.exists() else []
                for f in files:
                    if f.kind == "image" and Path(f.path).is_file():
                        _emit(
                            f"🔍 [诊断] helper: fallback 1) 找到 {f.name}"
                        )
                        return Path(f.path)
                # 2) v0.7.8.65:模糊搜项目下所有资产目录,匹配名字
                if proj_assets_root.exists():
                    matched_dirs = []
                    for child in proj_assets_root.iterdir():
                        if not child.is_dir():
                            continue
                        # 名字相似: 原名 / 安全名 / 包含关系
                        cn = child.name
                        if (cn == asset_name or
                            asset_name in cn or
                            cn.replace("_", "").replace("-", "") == asset_name.replace("_", "").replace("-", "")):
                            matched_dirs.append(child)
                    _emit(
                        f"🔍 [诊断] helper: fallback 2) 模糊搜 {proj_assets_root}, "
                        f"匹配 {len(matched_dirs)} 个目录: {[d.name for d in matched_dirs]}"
                    )
                    for d in matched_dirs:
                        files2 = list_asset_files(d)
                        for f in files2:
                            if f.kind == "image" and Path(f.path).is_file():
                                _emit(
                                    f"🔍 [诊断] helper: fallback 2) 找到 {d.name}/{f.name}"
                                )
                                return Path(f.path)
            except Exception as e:  # noqa: BLE001
                _emit(
                    f"🔍 [诊断] helper: fallback({asset_name}) 异常 {e}"
                )
            return None

        def _resolve(asset_name: str, kind_pref: str) -> Optional[Path]:
            """按 name + kind_pref 查 db,image_path 失效走 fallback_latest。"""
            if not asset_name:
                return None
            # 1. 精确匹配 (name, kind_pref)
            a = idx_exact.get((asset_name, kind_pref))
            if not a:
                a = idx_lower.get((asset_name.lower(), kind_pref.lower()))
            if a:
                if a.image_path and Path(a.image_path).is_file():
                    _emit(
                        f"🔍 [诊断] helper: [{asset_name}/{kind_pref}] 精确命中 → {Path(a.image_path).name}"
                    )
                    return Path(a.image_path)
                _emit(
                    f"🔍 [诊断] helper: [{asset_name}/{kind_pref}] 精确命中但 image_path "
                    f"={a.image_path!r} 失效(空或文件不存在)"
                )
            else:
                _emit(
                    f"🔍 [诊断] helper: [{asset_name}/{kind_pref}] db 查不到"
                )
            # 2. 兜底: 同名任意 kind
            cands = name_to_assets.get(asset_name) or name_to_assets_lower.get(asset_name.lower()) or []
            for c in cands:
                if c.image_path and Path(c.image_path).is_file():
                    _emit(
                        f"🔍 [诊断] helper: [{asset_name}] 同名兜底命中 "
                        f"(kind={c.kind}) → {Path(c.image_path).name}"
                    )
                    return Path(c.image_path)
            # 3. v0.7.8.63 fallback: db 路径失效 → 扫目录拿 mtime 最新图
            fb = _fallback_latest(asset_name)
            if fb:
                return fb
            return None

        # 优先 character → scene → prop → object
        for kind_pref in ("character", "scene", "prop", "object"):
            for a in seg_assets:
                p = _resolve(a.get("name", ""), kind_pref)
                if p:
                    _emit(f"🔍 [诊断] helper: ✅ 段参考图 = {p}")
                    log_file = _flush_log()
                    _emit(f"📄 完整 log: {log_file}")
                    return p
        # 兜底: 任意 kind_pref
        for a in seg_assets:
            for kp in ("character", "scene", "prop", "object", "asset", "other"):
                p = _resolve(a.get("name", ""), kp)
                if p:
                    _emit(f"🔍 [诊断] helper: ✅ 段参考图(兜底) = {p}")
                    log_file = _flush_log()
                    _emit(f"📄 完整 log: {log_file}")
                    return p
        _emit(
            f"🔍 [诊断] helper: ❌ 完全没找到参考图 "
            f"(seg_assets={len(seg_assets)} 条, project_assets={len(project_assets)} 条)"
        )
        log_file = _flush_log()
        _emit(f"📄 完整 log: {log_file}")
        return None

    def _on_generate_single_video(self, seg_id: str) -> None:
        """v0.7.8.35:单段视频生成(替代原来只能从第一个 pending 段开始的逻辑)。

        复刻老软件每段独立"▶ 生成"按钮的语义 — 哪段想生成就点哪段。
        v0.7.8.39：根据 self._video_link_mode 走 web/api 链路（VideoTask 内部路由）。
        """
        if not self._current_episode or not self._current_project:
            QMessageBox.warning(self, "提示", "请先选择一个剧集")
            return
        ep = self._current_episode
        if not ep.prompt or len(ep.prompt.strip()) < 10:
            QMessageBox.warning(
                self, "提示",
                "请先生成视频提示词(提示词为空或太短),然后再生成视频。",
            )
            return
        # v0.7.8.39【链路预检】：根据当前链路校验必要配置
        if self._video_link_mode == "web":
            if not self.config.dreamina_video_args:
                QMessageBox.warning(
                    self, "提示",
                    "当前是 🖥 浏览器生成 链路，但 config/hermes_api.json 未配置 "
                    "dreamina_video_args，无法生成视频。\n"
                    "请先在【设置】或直接编辑 config 补上模板。",
                )
                return
        else:  # api
            if not self.config.video_api_configs:
                QMessageBox.warning(
                    self, "提示",
                    "当前是 📡 API 生成 链路，但尚未配置任何 video_api_configs。\n\n"
                    "去【设置 → 🎬 视频 API】添加 API config。",
                )
                return
            if not self.config.video_api_base_url or not self.config.video_api_key:
                QMessageBox.warning(
                    self, "提示",
                    "当前活跃 video_api_config 缺 base_url 或 api_key。\n\n"
                    "去【设置 → 🎬 视频 API】补齐。",
                )
                return
        # v0.7.8.68【bugfix】:之前 `current_task is not None` 检查太宽 —
        # mark_success/mark_failed/mark_cancelled 都不清 _current_task,
        # 任务完成后 1.5s 内用户点 #2 段 → 早返回 + 弹"已有任务在跑",
        # 用户看到的是"我点了没反应"(弹窗关掉就以为没动)。
        # 修法:跟 _enqueue_task (main_window.py:2174-2179) 一致,用
        # state==RUNNING 作为权威。task 真在跑才挡,失败/取消/完成的不挡。
        from core.task_queue import TaskState
        cur = self.task_status_widget.current_task
        if cur is not None and getattr(cur, "state", None) == TaskState.RUNNING:
            QMessageBox.information(self, "提示", "已有任务在跑,请先等待或取消。")
            return
        env = parse_video_segments(ep.video_segments or "", ep_num=ep.episode_num, ep_title=ep.title)
        segs = env.get("segments", [])
        target_idx = None
        for i, s in enumerate(segs):
            if s.get("id") == seg_id:
                target_idx = i
                break
        if target_idx is None:
            QMessageBox.warning(self, "提示", f"未找到段 {seg_id}")
            return
        target_seg = segs[target_idx]
        # v0.7.8.61:段级音频已废弃,只取资产级音频 db.audio_selections
        audio_files: list = []
        for asset_name, audio_path in self.db.list_audio_selections(
            self._current_project.id
        ).items():
            if audio_path:
                audio_files.append(audio_path)
        # v0.7.8.62【bugfix】:seg.assets 只存 {name, kind:"asset"} 名字引用,
        # 没有 image_path。helper 用 name 查 db.assets 拿真实参考图。
        # 段结构（video_segments.py:64）：assets: [{name, kind, image_path?}, ...]
        reference_image: Optional[Path] = None
        seg_assets = target_seg.get("assets") or []
        # v0.7.8.57 诊断:显示 seg.assets 内容(name 是关键,kind 永远是 "asset" 占位)
        self.status_msg.setText(
            f"🔍 [诊断] seg_assets 长度={len(seg_assets)}, "
            f"names={[a.get('name','') for a in seg_assets]}"
        )
        reference_image = self._resolve_seg_reference_image(target_seg)
        # v0.7.8.57:最终 reference_image 状态打 log
        self.status_msg.setText(
            f"🔍 [诊断] reference_image 最终取值: {reference_image!r}"
        )
        # v0.7.8.39【链路参数打包】：API 链路要把 model / ratio / duration /
        # resolution 4 个卡片参数都塞进 link_params，传给 VideoTask
        link_params: Dict[str, Any] = {}
        if self._video_link_mode == "api":
            link_params = {
                "model": target_seg.get("model", "") or self.config.video_api_model,
                "ratio": target_seg.get("ratio", ""),
                "duration": int(target_seg.get("duration", 0) or 0),
                "resolution": target_seg.get("quality", ""),
            }
        request = VideoRequest(
            episode_id=ep.episode_num,
            episode_title=ep.title,
            prompt_text=target_seg.get("text") or ep.prompt,
            segment_index=target_idx,
            reference_image=reference_image,  # v0.7.8.46
            audio_files=audio_files,
            link_mode=self._video_link_mode,
            link_params=link_params,
        )
        # v0.7.8.58:视频落盘路径改造
        # 旧: outputs/<项目名>/video_<id>_segNN_<title>.mp4 (会覆盖)
        # 新: outputs/<项目名>-第N集-视频/🎞️ Segment X/video_<title>_<timestamp>.mp4
        # (按段建子目录 + 时间戳避免覆盖)
        proj_name = self._safe_dirname(self._current_project.name)
        ep_video_dir = (
            self.config.outputs_dir
            / f"{proj_name}-第{ep.episode_num}集-视频"
        )
        ep_video_dir.mkdir(parents=True, exist_ok=True)
        log.info(
            "_on_generate_single_video: 准备入队 seg_id=%s, target_idx=%d, "
            "output_dir=%s, link_mode=%s",
            seg_id, target_idx, ep_video_dir, self._video_link_mode,
        )
        try:
            task = VideoTask(ep, request, self.config, output_dir=ep_video_dir)
            self.task_queue.enqueue(task)
        except Exception as e:  # noqa: BLE001
            log.exception(
                "_on_generate_single_video: 入队失败 seg_id=%s (%s)", seg_id, e
            )
            self.status_msg.setText(f"❌ 入队失败: {e}")
            return
        audio_note = f"(含 {len(audio_files)} 个音频)" if audio_files else ""
        link_tag = "📡API" if self._video_link_mode == "api" else "🖥Web"
        log.info(
            "_on_generate_single_video: 入队成功 task=%s seg_id=%s",
            task.name, seg_id,
        )
        self.status_msg.setText(
            f"已入队[{link_tag}]: {task.name}(灌入第 {target_idx + 1} 段"
            f"「{target_seg.get('title','')}」){audio_note}"
        )

    @Slot()

    @staticmethod
    def _seg_status_text(status: str) -> str:
        return {
            "pending": "○ 待生成",
            "generating": "⏳ 生成中",
            "ready": "✓ 已生成",
            "failed": "✗ 失败",
        }.get(status, status)

    @staticmethod
    def _seg_status_color(status: str) -> str:
        return {
            "pending": "color: #888;",
            "generating": "color: #1976d2;",
            "ready": "color: #388e3c;",
            "failed": "color: #d32f2f;",
        }.get(status, "color: #666;")

    def _preview_video(self, path_str: str) -> None:
        """v0.6.19：预览视频（用系统默认播放器）。"""
        p = Path(path_str)
        if not p.exists():
            QMessageBox.information(self, "提示", f"文件丢失: {p}")
            return
        try:
            if os.name == "nt":
                os.startfile(str(p))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["open", str(p)])
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "提示", f"打开失败: {e}")

    # ---------- v0.6.19 段操作 ----------
    def _current_video_envelope(self) -> Optional[dict]:
        if not self._current_episode:
            return None
        return parse_video_segments(
            self._current_episode.video_segments or "",
            ep_num=self._current_episode.episode_num,
            ep_title=self._current_episode.title,
        )

    def _save_video_envelope(self, envelope: dict) -> None:
        """把 envelope 写回 db + 刷新视频 Tab。"""
        if not self._current_episode:
            return
        raw = dump_video_segments(envelope)
        self.db.update_episode(self._current_episode.id, video_segments=raw)
        ep_fresh = self.db.get_episode(self._current_episode.id)
        if ep_fresh and self._current_project:
            self._current_episode = ep_fresh
            self._show_video_tab(ep_fresh, self._current_project)

    def _on_remove_segment(self, seg_id: str) -> None:
        env = self._current_video_envelope()
        if env is None:
            return
        seg = next((s for s in env.get("segments", []) if s.get("id") == seg_id), None)
        if not seg:
            return
        ret = QMessageBox.question(
            self, "确认删除",
            f"确定删除段「{seg.get('title') or seg.get('id')}」？\n"
            f"（只删 db 记录，不删磁盘视频文件）",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        new_env = remove_segment(env, seg_id)
        self._save_video_envelope(new_env)
        self.status_msg.setText("✓ 段已删除")

    def _show_segment_text(self, text: str, title: str) -> None:
        """v0.7.8.30：弹窗显示该段的 prompt 全文（剧集关键词）。

        用 QDialog + QPlainTextEdit 复刻老软件把 text 作为视频 prompt 的行为,
        弹窗让用户能直接看每段的关键词内容(老软件是直接传给视频 API)。
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(f"📋 关键词 - {title}")
        dlg.resize(720, 520)
        v = QVBoxLayout(dlg)
        info = QLabel(
            f"<i>以下是该段的 prompt 文本(剧集关键词),生成视频时作为 prompt "
            f"传给视频 API。{len(text)} 字。</i>"
        )
        info.setStyleSheet("color: #888;")
        v.addWidget(info)
        edit = QPlainTextEdit(text)
        edit.setReadOnly(True)
        edit.setStyleSheet("background: #1E1E1E; color: #e0e0e0;")
        v.addWidget(edit, 1)
        btn_row = QHBoxLayout()
        btn_close = QPushButton("关闭")
        btn_close.setFixedHeight(32)
        btn_close.clicked.connect(dlg.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        v.addLayout(btn_row)
        dlg.exec()

    def _on_split_first_segment(self) -> None:
        env = self._current_video_envelope()
        if env is None or not env.get("segments"):
            QMessageBox.information(self, "提示", "没有可切的段。")
            return
        first = env["segments"][0]
        if not first.get("text"):
            QMessageBox.information(self, "提示", "第 1 段没有 prompt 文本，无法切分。")
            return
        new_env = split_segment_by_marker(env, first["id"])
        n_before = len(env.get("segments", []))
        n_after = len(new_env.get("segments", []))
        if n_after == n_before:
            QMessageBox.information(self, "提示", "没找到「## 分镜N」标记，未切分。")
            return
        self._save_video_envelope(new_env)
        self.status_msg.setText(f"✓ 第 1 段已切分为 {n_after} 段")

    def _on_add_empty_segment(self) -> None:
        env = self._current_video_envelope() or {"ep_num": 0, "ep_title": "", "segments": []}
        new_env = add_segment(env)
        self._save_video_envelope(new_env)
        self.status_msg.setText("✓ 已加空段")

    # v0.7.8.61:_on_segment_audio 已删除 — 用户反馈段级音频无意义,
    # 资产级音频才是生视频参考。audio_path 字段保留在 seg schema 里
    # 兼容老 db(避免破坏 parse_video_segments),但 UI 不再让用户编辑。

    # ---------- v0.6.22 web 视频生成 ----------
    @Slot()
    def _on_generate_web_video(self) -> None:
        """v0.6.22：用配置的 cmd_template 调外部命令生成视频（不走 dreamina.exe）。

        复刻原软件 D:\\剧本分镜助手\\server.py:1956-2001 `/api/video/generate/web`，
        改成更通用的"用户配命令模板"方案。
        """
        if not self._current_episode or not self._current_project:
            QMessageBox.warning(self, "提示", "请先选择一个剧集")
            return
        cmd_tpl = self.config.web_video_cmd_template
        err = validate_cmd_template(cmd_tpl)
        if err:
            ret = QMessageBox.question(
                self, "未配置 web 视频",
                f"web 视频命令未配置或无效：\n{err}\n\n"
                f"现在去设置吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if ret == QMessageBox.StandardButton.Yes:
                self._on_configure_web_video()
            return
        ep = self._current_episode
        # 找第 1 个 pending 段
        env = parse_video_segments(ep.video_segments or "", ep_num=ep.episode_num, ep_title=ep.title)
        segs = env.get("segments", [])
        target_idx = 0
        for i, s in enumerate(segs):
            if s.get("video_status") in ("pending", "failed"):
                target_idx = i
                break
        # 造输出路径
        from core.generators import _safe_filename
        proj_dir = self.config.outputs_dir / _safe_filename(ep.title or f"ep_{ep.episode_num}")
        proj_dir.mkdir(parents=True, exist_ok=True)
        output_path = proj_dir / safe_web_video_filename(ep.title or "ep", target_idx)
        # 启动后台线程
        # v0.7.8.40：_btn_web_video 已删，去掉按钮状态切换
        self.status_msg.setText(f"v0.6.22 web video: 启动 ({output_path.name})…")
        req = WebVideoRequest(
            episode_id=ep.episode_num,
            episode_title=ep.title,
            prompt_text=ep.prompt or "",
            segment_index=target_idx,
            output_path=output_path,
            cmd_template=cmd_tpl,
        )
        self._web_video_thread = _WebVideoWorker(req, self.config.web_video_timeout, parent=self)
        self._web_video_thread.finished_ok.connect(self._on_web_video_done)
        self._web_video_thread.failed.connect(self._on_web_video_failed)
        self._web_video_thread.start()

    def _on_configure_web_video(self) -> None:
        """v0.6.22：弹输入框让用户填命令模板。"""
        from PySide6.QtWidgets import QInputDialog
        cur = self.config.web_video_cmd_template
        text, ok = QInputDialog.getMultiLineText(
            self, "配置 web 视频命令模板",
            "命令模板（必须含 {prompt_file} / {output_file} 占位符）：\n"
            "示例：\n"
            "  python D:/scripts/my_video.py {prompt_file} {output_file}\n"
            "  agent-browser open https://dreamina.jianying.com/ai-tool/video\n"
            "（脚本自己负责调 videoApiUrl + 写 mp4 到 {output_file}）",
            cur,
        )
        if not ok:
            return
        # 校验
        err = validate_cmd_template(text.strip())
        if err:
            QMessageBox.warning(self, "校验失败", err)
            return
        # 写盘
        cfg_path = self.config.path
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            QMessageBox.critical(self, "错误", f"读配置失败: {e}")
            return
        raw.setdefault("web_video", {})["cmd_template"] = text.strip()
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(raw, f, ensure_ascii=False, indent=2)
        except OSError as e:
            QMessageBox.critical(self, "错误", f"写配置失败: {e}")
            return
        # reload Config
        from core.config import Config
        Config.reload(cfg_path)
        QMessageBox.information(
            self, "✓ 已保存",
            f"web 视频命令模板已保存。\n"
            f"下次点【🌐 浏览器生成】即生效。\n\n"
            f"模板：\n{text.strip()}",
        )
        self.status_msg.setText("✓ web 视频命令模板已保存")

    @Slot(str)
    def _on_web_video_done(self, video_path: str) -> None:
        """v0.6.22：web 视频生成完成回调。"""
        ep_id = self._current_episode.id if self._current_episode else None
        if not ep_id:
            return
        # 找段号（web video 总是写到第 1 个 pending 段）
        env = self._current_video_envelope()
        if env is None:
            return
        segs = env.get("segments", [])
        target_idx = 0
        for i, s in enumerate(segs):
            if s.get("video_status") in ("pending", "failed"):
                target_idx = i
                break
        if segs:
            target_seg = segs[target_idx]
            env = update_segment_video(env, target_seg["id"], video_path, VIDEO_STATUS_READY)
            raw = dump_video_segments(env)
            self.db.update_episode(ep_id, video_segments=raw)
            if self._current_episode and self._current_project:
                ep_updated = self.db.get_episode(ep_id)
                if ep_updated:
                    self._current_episode = ep_updated
                    self._show_video_tab(ep_updated, self._current_project)
        # v0.7.8.40：_btn_web_video 已删，去掉这俩 setEnabled/setText（避免 AttributeError）
        self.status_msg.setText(f"✓ web 视频已生成: {Path(video_path).name}")

    @Slot(str)
    def _on_web_video_failed(self, error: str) -> None:
        # v0.7.8.40：_btn_web_video 已删，去掉这俩 setEnabled/setText
        QMessageBox.critical(self, "web 视频失败", error)
        self.status_msg.setText(f"✗ web 视频失败: {error[:60]}")

    def _replace_tab(self, index: int, widget: QWidget, label: str, *, switch: bool = True) -> None:
        """v0.7.8.36:回退到 removeTab + insertTab 模式(放弃 v0.7.8.37 holder)。

        原因:v0.7.8.37 holder 模式让 QScrollArea 默认 Preferred size 缩成
        角落 + inner layout stretch 没设,导致 tab 内容看不到,UI 全坏。
        先恢复 v0.7.8.36 能用的状态,UI 变形问题以后再优化。
        v0.7.8.49:同 index 上已经是这个 widget → 只切 tab,不重建(避免
        removeTab/insertTab 强 QStackedWidget 整体 layout)。
        """
        if 0 <= index < self.tabs.count() and self.tabs.widget(index) is widget:
            # 已经在那个位置,只是切过去就行
            if switch:
                self.tabs.setCurrentIndex(index)
            return
        if 0 <= index < self.tabs.count():
            self.tabs.removeTab(index)
        self.tabs.insertTab(index, widget, label)
        if switch:
            self.tabs.setCurrentIndex(index)

    def _show_asset_tab(self, project: Project, *, switch: bool = True) -> None:
        """资产 Tab（第 5 个）。项目级：所有剧集共用一份资产清单。

        v0.7.8.20:switch=False 时只刷新内容不切 tab,供选项目/剧集时调用。
        v0.7.8.49:cache 命中(同 project_id)→ 复用旧 AssetListWidget,只 refresh 数据,
        不重建 widget 树(N 个资产 × 6 widget 重建很卡)。
        """
        # v0.7.8.49:同项目 → 复用 widget,只 refresh
        if self._asset_tab_cache and self._asset_tab_cache[0] == project.id:
            cached_panel = self._asset_tab_cache[1]
            cached_panel.refresh()  # 重新从 db 拉一次,可能有新资产
            if 0 <= 4 < self.tabs.count():
                self.tabs.removeTab(4)
            self.tabs.insertTab(4, cached_panel, "🎨 资产")
            if switch:
                self.tabs.setCurrentIndex(4)
            return
        # 切到新项目 / 首次进入 → 重建 widget
        panel = AssetListWidget(
            project=project,
            db=self.db,
            on_enqueue=self._enqueue_task,
            on_open_outputs=self._open_in_explorer,
        )
        self._asset_tab_cache = (project.id, panel)
        self._replace_tab(4, panel, "🎨 资产", switch=switch)

    def _current_asset_panel(self) -> Optional[AssetListWidget]:
        w = self.tabs.widget(4)
        return w if isinstance(w, AssetListWidget) else None

    def _enqueue_task(self, task: Task) -> None:
        """统一入队入口（被 asset panel 调用）。"""
        log.info(
            "_enqueue_task 收到 task=%s (%s)",
            task.name, type(task).__name__,
        )
        # guard: 当前任务还在 RUNNING 才算"在跑" — 失败/取消/完成的不算
        cur = self.task_status_widget.current_task
        from core.task_queue import TaskState
        if cur is not None and getattr(cur, "state", None) == TaskState.RUNNING:
            log.warning("_enqueue_task: 已有任务在跑 (%s)，拒绝 %s", cur.name, task.name)
            QMessageBox.information(self, "提示", "已有任务在跑，请先等待或取消。")
            return
        try:
            self.task_queue.enqueue(task)
            self.status_msg.setText(f"已入队: {task.name}")
            self.task_status_widget.clear()
            log.info("_enqueue_task: 入队成功 %s", task.name)
        except Exception as e:  # noqa: BLE001
            log.exception("_enqueue_task: enqueue 抛了")
            QMessageBox.critical(self, "错误", f"任务入队失败: {e}\n\n看 logs/manju.log。")

    @staticmethod
    def _tabs_remove_widget(w: Optional[QWidget]) -> None:
        """移除 Tab 中的 widget 引用，避免内存泄漏。"""
        if w is None:
            return
        w.setParent(None)
        w.deleteLater()

    # ---------- CRUD 处理器 ----------
    @Slot()
    def _on_new_project(self) -> None:
        # v0.6.18：传空默认值，dialog 出来后用户选 style/render
        dlg = NewProjectDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        name, desc, style_id, render_type = dlg.data()
        if not name:
            QMessageBox.warning(self, "提示", "项目名不能为空")
            return
        try:
            p = self.db.create_project(name, desc, style_id, render_type)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建失败: {e}")
            return
        # v1.1.5【B1 修复】:add_project 返回 item,用 setCurrentItem 触发
        # itemSelectionChanged → _on_project_selected,自动设 _current_project
        # + 启用 toolbar "新建剧集" 按钮(之前 addTopLevelItem 不触发 selection,
        # user 新建项目后 toolbar 按钮还是灰的,user 不知道为啥按不动)。
        item = self.tree.add_project(p)
        if item is not None:
            self.tree.setCurrentItem(item)
        self.status_msg.setText(f"已创建项目: {name}")

    @Slot(str)
    def _on_new_episode(self, project_id: str) -> None:
        eps = self.db.list_episodes(project_id)
        default_num = max((e.episode_num for e in eps), default=0) + 1
        # v0.6.28：渲染类型走项目级，dialog 不再让用户选
        dlg = NewEpisodeDialog(self, default_num=default_num)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        num, title, script = dlg.data()
        if not title:
            QMessageBox.warning(self, "提示", "剧集标题不能为空")
            return
        try:
            ep = self.db.create_episode(
                project_id, title, script, episode_num=num
            )
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建失败: {e}")
            return
        project = self.db.get_project(project_id)
        proj_name = project.name if project else ""
        # v1.1.5【B2 修复】:add_episode 返回 child item,用 setCurrentItem 触发
        # itemSelectionChanged → _on_episode_selected,自动设 _current_episode
        # + 切到分镜 tab(之前 addChild 不触发 selection,user 新建剧集后还停在
        # 旧剧集/项目概览,看不到新剧集内容)。
        # 同时建完即让用户能看到剧本,先 invalidate cache。
        self._invalidate_all_ui_caches()
        item = self.tree.add_episode(ep, project_name=proj_name)
        if item is not None and not item.treeWidget() is None:
            self.tree.setCurrentItem(item)
        self.status_msg.setText(f"已创建剧集: 第{ep.episode_num}集 - {title}")

    @Slot()
    def _on_new_episode_toolbar(self) -> None:
        """v0.6.27：toolbar 的 ➕ 新建剧集 按钮 handler。

        必须先选中项目（按钮在没选项目时是灰的）。"""
        if not self._current_project:
            QMessageBox.information(self, "提示", "请先在左侧选中一个项目，再点 ➕ 新建剧集。")
            return
        self._on_new_episode(self._current_project.id)

    @Slot(str)
    def _on_rename_project(self, project_id: str) -> None:
        p = self.db.get_project(project_id)
        if not p:
            return
        # v0.6.18：把已有 style/render 作为 dialog 默认值，用户可继续改
        dlg = NewProjectDialog(
            self,
            default_name=p.name,
            default_desc=p.description,
            default_style_id=p.style_id,
            default_render_type=p.render_type,
        )
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        name, desc, style_id, render_type = dlg.data()
        if not name:
            QMessageBox.warning(self, "提示", "项目名不能为空")
            return
        self.db.update_project(
            project_id,
            name=name,
            description=desc,
            style_id=style_id,
            render_type=render_type,
        )
        p = self.db.get_project(project_id)
        self.tree.update_project(p)
        # v1.1.5【C1 修复】:重命名后 _project_overview_cache 命中
        # (cache_key = (project.id, len(eps))),右侧"📋 概览" tab 仍显示
        # 旧项目名(title_box 的 <h2>{project.name}</h2> 在构造时就写死)。
        # 修法:清 project_overview_cache,若当前正在看这个项目,主动刷一次。
        self._project_overview_cache = None
        if (
            self._current_project is not None
            and self._current_project.id == project_id
        ):
            # 重新拉一次,刷新内存里的 _current_project
            self._current_project = p
            eps = self.db.list_episodes(project_id)
            self._show_project_overview(p, eps)
        self.status_msg.setText(f"已更新项目: {name}")

    @Slot(str)
    def _on_delete_project(self, project_id: str) -> None:
        p = self.db.get_project(project_id)
        if not p:
            return
        ret = QMessageBox.question(
            self, "确认删除",
            f"确定要删除项目「{p.name}」吗？\n该项目下的所有剧集也会被删除，无法恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        # v1.1.5【B3 修复】:删除前先记下,看是不是当前正在看的。
        # 之前删完直接 return → _current_project / _current_episode 还指向
        # 已删 id 的 stale 对象 → 后续任何 _current_project.id 比较、
        # db.get_project(...) 都会出错或右侧 tab 显示已删剧集的旧内容。
        was_current = (
            self._current_project is not None
            and self._current_project.id == project_id
        )
        self.db.delete_project(project_id)
        self.tree.remove_project(project_id)
        if was_current:
            self._current_project = None
            self._current_episode = None
            # 切回初始空态,清所有 cache 防 stale widget
            self._invalidate_all_ui_caches()
            # 清空右侧所有 tab,用占位 tab 替
            self.tabs.setCurrentIndex(0)
            self._replace_tab(0, self._placeholder_tab("（项目已删除）"), "📋 概览")
            # 同步 toolbar 状态
            if hasattr(self, "_act_new_episode"):
                self._act_new_episode.setEnabled(False)
            self.btn_open_project_dir.setEnabled(False)
        self.status_msg.setText(f"已删除项目: {p.name}")

    @Slot(str)
    def _on_edit_episode(self, episode_id: str) -> None:
        ep = self.db.get_episode(episode_id)
        if not ep:
            return
        # v0.6.28：渲染类型走项目级，编辑剧集时不让用户改
        dlg = NewEpisodeDialog(
            self,
            default_num=ep.episode_num,
            default_title=ep.title,
        )
        dlg.script_edit.setPlainText(ep.script)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        num, title, script = dlg.data()
        if not title:
            QMessageBox.warning(self, "提示", "剧集标题不能为空")
            return
        self.db.update_episode(
            episode_id, title=title, script=script
        )
        # v1.1.5【C2 修复】:之前只 _reload_projects()(只刷 tree),没 invalidate
        # episode_detail_cache / prompt_tab_cache / video_tab_cache,导致:
        # - _episode_detail_cache id-only 命中 → tab 还显示旧 title/script
        # - _prompt_tab_cache key 含 hash(ep.prompt),prompt 没变就 OK
        # - _video_tab_cache key 含 hash(video_segments)/hash(prompt),都没变 OK
        # 修法:invalidate 所有 cache(只多花 200-800ms 重建一次,user 刚点"保存"了)
        # + 如果当前正在看这个剧集,主动刷详情页让用户立刻看到改动。
        self._invalidate_all_ui_caches()
        self._reload_projects()
        if (
            self._current_episode is not None
            and self._current_episode.id == episode_id
        ):
            ep_fresh = self.db.get_episode(episode_id)
            if ep_fresh is not None and self._current_project is not None:
                self._current_episode = ep_fresh
                self._show_episode_detail(ep_fresh, self._current_project)
                self._show_prompt_tab(ep_fresh, self._current_project)
                self._show_video_tab(ep_fresh, self._current_project)
        self.status_msg.setText(f"已更新剧集: 第{num}集 - {title}")

    @Slot(str)
    def _on_delete_episode(self, episode_id: str) -> None:
        ep = self.db.get_episode(episode_id)
        if not ep:
            return
        ret = QMessageBox.question(
            self, "确认删除",
            f"确定要删除「第{ep.episode_num}集：{ep.title}」吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        # v1.1.5【B4 修复】:删除前记下,看是不是当前正在看的剧集。
        # 之前删完只调 self.tree.remove_episode → _current_episode 还指向
        # 已删 id 的 stale 对象;另外 remove_episode 不会更新项目行的"(N)" 计数。
        was_current = (
            self._current_episode is not None
            and self._current_episode.id == episode_id
        )
        project_id = ep.project_id
        self.db.delete_episode(episode_id)
        # 重新拉剩余剧集并刷 tree 括号数字(N)
        try:
            eps_after = self.db.list_episodes(project_id)
            self.tree.set_episodes(project_id, eps_after)
        except Exception as e:
            log.exception("delete_episode: 刷剧集列表失败: %s", e)
        if was_current:
            self._current_episode = None
            self._invalidate_all_ui_caches()
            # 切回项目概览
            proj = self.db.get_project(project_id)
            if proj is not None:
                self._current_project = proj
                self._on_project_selected(project_id)
        self.status_msg.setText(f"已删除剧集: 第{ep.episode_num}集")

    # ---------- 生成操作 ----------
    @Slot()
    def _on_generate_storyboard(self) -> None:
        if not self._current_episode or not self._current_project:
            QMessageBox.warning(self, "提示", "请先选择一个剧集")
            return
        ep = self._current_episode
        if not ep.script or len(ep.script.strip()) < 20:
            QMessageBox.warning(
                self, "提示",
                "剧集剧本为空或太短（< 20 字），无法生成分镜。\n请先在右键菜单里编辑剧集、填写剧本。"
            )
            return
        # v0.7.8.68:跟 _on_generate_single_video 一致,用 state==RUNNING 判断
        from core.task_queue import TaskState
        cur = self.task_status_widget.current_task
        if cur is not None and getattr(cur, "state", None) == TaskState.RUNNING:
            QMessageBox.information(self, "提示", "已有任务在跑，请先等待或取消。")
            return
        # v0.6.17：注入前序剧集摘要。v0.6.28：style_id / render_type 由 Task 内部从 project 读
        previous_summaries = self._get_previous_summaries(ep)
        task = StoryboardTask(
            ep,
            self._current_project,
            self.config,
            parent=self,
            previous_summaries=previous_summaries,
        )
        self.task_queue.enqueue(task)
        self.status_msg.setText(f"已入队: {task.name}")

    @Slot()
    def _on_generate_prompt(self) -> None:
        if not self._current_episode or not self._current_project:
            QMessageBox.warning(self, "提示", "请先选择一个剧集")
            return
        ep = self._current_episode
        if not ep.storyboard or len(ep.storyboard.strip()) < 20:
            QMessageBox.warning(
                self, "提示",
                "请先生成分镜（分镜内容为空或太短），然后再生成视频提示词。"
            )
            return
        # v0.7.8.68:跟 _on_generate_single_video 一致,用 state==RUNNING 判断
        from core.task_queue import TaskState
        cur = self.task_status_widget.current_task
        if cur is not None and getattr(cur, "state", None) == TaskState.RUNNING:
            QMessageBox.information(self, "提示", "已有任务在跑，请先等待或取消。")
            return
        # v0.6.17：注入资产列表。v0.6.28：style_id / render_type 由 Task 内部从 project 读
        asset_names = self._get_asset_list_for_current_project()
        task = VideoPromptTask(
            ep,
            self._current_project,
            self.config,
            parent=self,
            asset_names=asset_names,
        )
        self.task_queue.enqueue(task)
        self.status_msg.setText(f"已入队: {task.name}")

    @Slot()
    def _on_generate_video(self) -> None:
        if not self._current_episode or not self._current_project:
            QMessageBox.warning(self, "提示", "请先选择一个剧集")
            return
        ep = self._current_episode
        if not ep.prompt or len(ep.prompt.strip()) < 10:
            QMessageBox.warning(
                self, "提示",
                "请先生成视频提示词（提示词为空或太短），然后再生成视频。"
            )
            return
        if not self.config.dreamina_video_args:
            QMessageBox.warning(
                self, "提示",
                "config/hermes_api.json 未配置 dreamina_video_args，"
                "无法生成视频。请先在【设置】或直接编辑 config 补上模板。"
            )
            return
        # v0.7.8.68:跟 _on_generate_single_video 一致,用 state==RUNNING 判断
        from core.task_queue import TaskState
        cur = self.task_status_widget.current_task
        if cur is not None and getattr(cur, "state", None) == TaskState.RUNNING:
            QMessageBox.information(self, "提示", "已有任务在跑，请先等待或取消。")
            return
        # v0.6.19：找第 1 个 pending 段（默认灌入位置）
        env = parse_video_segments(ep.video_segments or "", ep_num=ep.episode_num, ep_title=ep.title)
        segs = env.get("segments", [])
        target_idx = 0
        for i, s in enumerate(segs):
            if s.get("video_status") in ("pending", "failed"):
                target_idx = i
                break
        # v0.7.8.61:段级音频已废弃,只取资产级音频 db.audio_selections
        audio_files: list = []
        for asset_name, audio_path in self.db.list_audio_selections(
            self._current_project.id
        ).items():
            if audio_path:
                audio_files.append(audio_path)
        # v0.7.8.62:批量第一段也要取 reference_image
        reference_image = self._resolve_seg_reference_image(
            segs[target_idx] if target_idx < len(segs) else None
        )
        request = VideoRequest(
            episode_id=ep.episode_num,
            episode_title=ep.title,
            prompt_text=ep.prompt,
            segment_index=target_idx,
            reference_image=reference_image,
            audio_files=audio_files,
        )
        # v0.7.8.58:视频落盘路径改造(同 _on_generate_single_video 一样的目录结构)
        proj_name = self._safe_dirname(self._current_project.name)
        ep_video_dir = (
            self.config.outputs_dir
            / f"{proj_name}-第{ep.episode_num}集-视频"
        )
        ep_video_dir.mkdir(parents=True, exist_ok=True)
        task = VideoTask(ep, request, self.config, output_dir=ep_video_dir)
        self.task_queue.enqueue(task)
        audio_note = f"（含 {len(audio_files)} 个音频）" if audio_files else ""
        self.status_msg.setText(f"已入队: {task.name}（灌入第 {target_idx + 1} 段）{audio_note}")

    def _get_previous_summaries(self, current_episode) -> list:
        """v0.6.17：返回当前剧集**之前**所有剧集的剧情概要 list。

        复刻自原软件 D:\\剧本分镜助手\\server.py:267-274 `build_storyboard_prompt`
        的 previous_summaries 参数。原软件用这个列表注入续集 prompt 让 LLM 保持
        人物/世界观/剧情伏笔连贯。

        Returns:
            list of dict: [{'episode_num': int, 'title': str, 'summary': str}, ...]
            按 episode_num 升序，**不含** current_episode 本身。
        """
        if not self._current_project:
            return []
        eps = self.db.list_episodes(self._current_project.id)
        summaries = []
        for ep in eps:
            if ep.episode_num >= current_episode.episode_num:
                continue
            if not ep.storyboard or len(ep.storyboard.strip()) < 20:
                continue  # 没分镜的不算
            # 摘剧情概要：取分镜前 600 字符（复刻 server.py:315 summarize_storyboard）
            sb = ep.storyboard.strip()
            # 找 ## 分镜脚本 之类标记（复刻 server.py:315 markers）
            for marker in ("\n## 分镜脚本", "\n## 完整分镜表", "\n════════════"):
                idx = sb.find(marker)
                if idx > 0:
                    sb = sb[idx + len(marker):].strip()
                    break
            summary = sb[:600].strip()
            if summary:
                summaries.append({
                    "episode_num": ep.episode_num,
                    "title": ep.title or f"第{ep.episode_num}集",
                    "summary": summary,
                })
        return summaries

    def _get_asset_list_for_current_project(self) -> str:
        """v0.6.17：返回当前项目的资产名列表（人/场/物三段纯文本）。

        优先从 `outputs/<project_id>_asset_list.txt` 读（v0.6.16 AssetExtractTask 写盘的），
        否则从 db 凑一份（不完美但能用）。

        复刻自原软件 D:\\剧本分镜助手\\server.py:1307-1310 注入下游
        seedance prompt 的 asset_block。
        """
        if not self._current_project:
            return ""
        from core.asset_parser import list_file_path
        # 1. 从写盘文件读
        try:
            lf = list_file_path(self.config.outputs_dir, self._current_project.id)
            if lf.exists():
                return lf.read_text(encoding="utf-8")
        except OSError:
            pass
        # 2. 从 db 凑
        from core.asset_parser import _SECTION_KIND
        d = {title: [] for title in _SECTION_KIND}
        section_map = {kind: title for title, kind in _SECTION_KIND.items()}
        for a in self.db.list_assets(self._current_project.id):
            k = section_map.get(a.kind)
            if k:
                d[k].append(a.name)
        lines = []
        for section_key, _kind in _SECTION_KIND.items():
            items = d.get(section_key) or []
            if items:
                lines.append(f"{section_key}：{'、'.join(items)}")
        return "\n".join(lines)

    def _on_open_video_dir(self) -> None:
        if not self._current_project:
            return
        # 视频输出在 outputs/<项目名>/
        from core.generators import _safe_filename
        proj_dir = self.config.outputs_dir / _safe_filename(self._current_project.name)
        proj_dir.mkdir(parents=True, exist_ok=True)
        self._open_in_explorer(proj_dir)

    @Slot()
    def _on_clear_prompt(self) -> None:
        """v0.6.18 #6：清空当前剧集的 prompt（连同 db + 文件）。"""
        if not self._current_episode:
            QMessageBox.warning(self, "提示", "请先选择一个剧集")
            return
        ep = self._current_episode
        if not ep.prompt:
            QMessageBox.information(self, "提示", "当前剧集没有 prompt，无需清空。")
            return
        ret = QMessageBox.question(
            self, "确认清空",
            f"确定要清空「第{ep.episode_num}集：{ep.title}」的 prompt 吗？\n"
            f"会同时清空 db 字段和 outputs 目录下的 prompt 文件。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        # 清 db
        self.db.update_episode(ep.id, prompt="", prompt_status="")
        # 清文件
        p = self._prompt_file_path()
        if p and p.exists():
            try:
                p.unlink()
                log.info("已删除 prompt 文件: %s", p)
            except OSError as e:
                log.warning("删除 prompt 文件失败: %s", e)
        # 刷新 UI
        ep_fresh = self.db.get_episode(ep.id)
        if ep_fresh and self._current_project:
            self._current_episode = ep_fresh
            self._show_prompt_tab(ep_fresh, self._current_project)
        self.status_msg.setText("✓ prompt 已清空")

    def _auto_push_prompt_to_segments(self, ep: Episode, prompt_text: str, force: bool = False) -> int:
        """v0.7.8.32:把 prompt_text 按 🎞️ Segment 切分,直接 overwrite 写入
        ep.video_segments(不弹窗),返回段数。

        复刻老软件 index.html:2137 pushPromptsToVideo() 的核心逻辑,但
        移除了"覆盖/追加"对话框 —— v0.7.8.32 用户要求新生成 prompt 时
        自动推送,直接覆盖,不需要交互。

        v0.7.8.34:不再无脑覆盖。video_segments 非空说明用户在视频 tab
        里手动编辑过段(text / 标题 / 合并 / 删除等),尊重他的编辑,不
        覆盖。返回 0 + 日志记录。

        v0.7.8.77【加 force 参数】:用户主动点"📥 提取提示词到视频"按钮时
        传 force=True,跳过 v0.7.8.34 保护,直接覆盖。供"我想用新 prompt
        替换当前 video_segments"场景用 —— 这是 user 主动行为,不算误覆盖。
        """
        import re as _re

        if not prompt_text:
            return 0

        # v0.7.8.34:非空 = 用户在视频 tab 手动编辑过,尊重不覆盖。
        # v0.7.8.77:force=True 时跳过保护(用户主动按按钮,显式同意覆盖)
        if (not force) and ep.video_segments and ep.video_segments.strip():
            env_existing = parse_video_segments(
                ep.video_segments, ep_num=ep.episode_num, ep_title=ep.title,
            )
            n_existing = len(env_existing.get("segments", []))
            if n_existing > 0:
                log.info(
                    "_auto_push_prompt_to_segments: ep=%s 视频段已有 %d 段(用户手动编辑),"
                    "不覆盖,跳过自动推送",
                    ep.id, n_existing,
                )
                return 0

        # 按 🎞️ Segment N 分割（复刻 index.html:2143）
        parts = _re.split(r"🎞️\s*Segment\s*\d+", prompt_text, flags=_re.IGNORECASE)
        if len(parts) < 2:
            log.warning("_auto_push_prompt_to_segments: ep=%s prompt 没有 🎞️ Segment 标记,跳过", ep.id)
            return 0

        # 解析每段
        segs_new: list = []
        for i in range(1, len(parts)):
            text = parts[i].strip()
            if not text:
                continue
            # 标题:首行
            first_line = text.split("\n", 1)[0]
            m = _re.match(r"^[:\s]*(.+)", first_line)
            title = m.group(1).strip() if m else f"Segment {i}"
            # 时长: (0-6s) → 6
            duration = 8
            dm = _re.search(r"\((\d+)\s*-\s*(\d+)\s*s\)", title)
            if dm:
                duration = int(dm.group(2))
                title = _re.sub(r"\s*\(\d+\s*-\s*\d+\s*s\)", "", title).strip()
            # 资产:[Asset Definitions] 块里的 @xxx 引用
            assets: list = []
            ad = _re.search(
                r"\[Asset\s*Definitions?\]([\s\S]*?)(?=\n\n[🎞️\[]|\n##|\n───|\n\*\*[A-Z]|$)",
                text, flags=_re.IGNORECASE,
            )
            if ad:
                at_refs = _re.findall(r"@([^\s\n,，@]+)", ad.group(1))
                for ref in at_refs:
                    name = ref.strip()
                    if name and len(name) > 1 and not name.isdigit():
                        if not any(a["name"] == name for a in assets):
                            assets.append({"name": name, "kind": "asset"})
            segs_new.append({
                # v0.7.8.60:title 也带 🎞️ Segment N 前缀(老软件 hermes 输出
                # 原文本里 _re.split 把 🎞️ Segment N 当分隔符丢了,这里
                # 同时补回 title 和 text,用户 UI 上能看到段序号;后续
                # _on_update_seg_prop 保存时自动持久化)
                "title": f"🎞️ Segment {i} - " + (title or f"Segment {i}"),
                "text": f"🎞️ Segment {i}\n\n{text}",
                "assets": assets,
                "duration": duration,
                "model": "seedance2.0fast",
                "ratio": "16:9",
                "quality": "720p",
            })

        if not segs_new:
            log.warning("_auto_push_prompt_to_segments: ep=%s 解析出 0 段,跳过", ep.id)
            return 0

        # 直接 overwrite,写 envelope
        env = empty_envelope(ep_num=ep.episode_num, ep_title=ep.title)
        for s in segs_new:
            env = add_segment(
                env, title=s["title"], text=s["text"], duration=s["duration"],
                model=s["model"], ratio=s["ratio"], quality=s["quality"],
            )
        raw_new = dump_video_segments(env)
        self.db.update_episode(ep.id, video_segments=raw_new)
        log.info("_auto_push_prompt_to_segments: ep=%s, segs=%d (overwrite)", ep.id, len(segs_new))
        return len(segs_new)

    @Slot()
    def _on_extract_prompt_to_video(self) -> None:
        """v0.7.8.77【📥 提取提示词到视频按钮】点击事件。

        把当前剧集的 ep.prompt 按 🎞️ Segment 切分,强制覆盖到 video_segments
        (跳过 v0.7.8.34 保护)。user 主动行为 = 显式同意覆盖,不算误冲手动
        编辑。

        适用场景:
        - 重新生成提示词后,新 prompt 因 v0.7.8.34 保护没自动 push 到 UI
        - 想用新 prompt 替换当前 video_segments(7/3 那种 23 段老结果)

        不做的事:
        - 不删磁盘 video 文件(video_path / video_status 字段保留)
        - 不调 LLM,不动 storyboard
        - 不动 db 任何其他字段
        """
        if not self._current_episode:
            QMessageBox.warning(self, "提示", "请先选择一个剧集")
            return
        ep = self._current_episode
        if not ep.prompt or not ep.prompt.strip():
            QMessageBox.warning(
                self, "提示词为空",
                "当前剧集还没有生成提示词。\n\n"
                "请先到【提示词】tab 点【📝 生成视频提示词】生成,然后再点此按钮。",
            )
            return
        # user 主动行为,直接覆盖(按钮 tooltip 已写清风险)
        n = self._auto_push_prompt_to_segments(ep, ep.prompt, force=True)
        if n <= 0:
            self.status_msg.setText("⚠ 提取失败:prompt 里没有 🎞️ Segment 标记")
            return
        # 刷新视频 tab(用最新 ep)
        ep_fresh = self.db.get_episode(ep.id)
        if ep_fresh and self._current_project:
            self._current_episode = ep_fresh
            self._show_video_tab(ep_fresh, self._current_project)
        self.status_msg.setText(f"✓ 已提取 {n} 段到视频界面(覆盖式)")

    @Slot()
    def _on_clear_storyboard(self) -> None:
        """v0.6.26：只清空当前剧集的分镜（不动剧集本身，不重跑 LLM）。

        复刻自原软件 D:\\剧本分镜助手\\server.py:1153-1171
        `POST /api/projects/<id>/episodes/<eid>/clear-storyboard`：
        - 旧路由只把 storyboard 字段清空（保留 script / 其他）
        - 不调 LLM，不删剧集
        """
        if not self._current_episode:
            QMessageBox.warning(self, "提示", "请先选择一个剧集")
            return
        ep = self._current_episode
        if not ep.storyboard:
            QMessageBox.information(self, "提示", "当前剧集没有分镜，无需清空。")
            return
        ret = QMessageBox.question(
            self, "确认清空分镜",
            f"确定要清空「第{ep.episode_num}集：{ep.title}」的分镜吗？\n\n"
            f"• 剧集本身（标题 / 剧本 / 渲染类型）保留\n"
            f"• prompt 不会被清空（可独立处理）\n"
            f"• 分镜文件 (outputs/.../ep*_storyboard.md) 也会被删除",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        # 清 db（只清 storyboard 字段，保留其他）
        self.db.update_episode(ep.id, storyboard="")
        # 清文件
        p = self._storyboard_file_path()
        if p and p.exists():
            try:
                p.unlink()
                log.info("已删除分镜文件: %s", p)
            except OSError as e:
                log.warning("删除分镜文件失败: %s", e)
        # 刷新 UI
        ep_fresh = self.db.get_episode(ep.id)
        if ep_fresh and self._current_project:
            self._current_episode = ep_fresh
            self._show_episode_detail(ep_fresh, self._current_project)
        self.status_msg.setText("✓ 分镜已清空（剧集保留）")

    @Slot()
    def _on_open_project_dir(self) -> None:
        """v0.6.18 #9：打开项目目录（outputs/<项目名>/）。"""
        if not self._current_project:
            QMessageBox.information(self, "提示", "请先选择一个项目")
            return
        from core.generators import _safe_filename
        proj_dir = self.config.outputs_dir / _safe_filename(self._current_project.name)
        proj_dir.mkdir(parents=True, exist_ok=True)
        self._open_in_explorer(proj_dir)

    @Slot(str)
    def _on_export_all_prompts(self, project_id: str) -> None:
        """v0.6.18 #8：导出整剧集 prompts。

        复刻自原软件 D:\\剧本分镜助手\\server.py 的
        /api/projects/<id>/export-prompts — 合并所有剧集的 prompt 到一个 md。
        """
        project = self.db.get_project(project_id)
        if not project:
            return
        eps = self.db.list_episodes(project_id)
        if not eps:
            QMessageBox.information(self, "提示", "项目下没有剧集")
            return
        # 只导有 prompt 的
        with_prompt = [ep for ep in eps if ep.prompt and ep.prompt.strip()]
        if not with_prompt:
            QMessageBox.warning(self, "提示", "项目下没有已生成的 prompt。\n请先在剧集里点【生成视频提示词】。")
            return
        # 拼成一个大 md
        parts: list = [f"# {project.name} — 整剧集视频提示词", ""]
        parts.append(f"> 共 {len(with_prompt)} 集有 prompt（共 {len(eps)} 集）")
        parts.append(f"> 导出时间: {__import__('datetime').datetime.now().isoformat(timespec='seconds')}")
        parts.append("")
        for ep in with_prompt:
            parts.append(f"## 第{ep.episode_num}集：{ep.title or '（无标题）'}")
            parts.append("")
            parts.append(ep.prompt)
            parts.append("")
            parts.append("---")
            parts.append("")
        content = "\n".join(parts)
        # 写盘到 outputs/<项目名>/all_prompts_<时间戳>.md
        from core.generators import _safe_filename
        ts = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_dir = self.config.outputs_dir / _safe_filename(project.name)
        proj_dir.mkdir(parents=True, exist_ok=True)
        out_path = proj_dir / f"all_prompts_{ts}.md"
        try:
            out_path.write_text(content, encoding="utf-8")
        except OSError as e:
            QMessageBox.critical(self, "错误", f"导出失败: {e}")
            return
        # 弹窗确认 + 打开文件
        ret = QMessageBox.question(
            self, "导出完成",
            f"已导出 {len(with_prompt)} 集 prompt 到：\n{out_path}\n\n"
            f"总字符: {len(content)}\n\n是否打开文件？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ret == QMessageBox.StandardButton.Yes:
            self._open_in_explorer(out_path)
        self.status_msg.setText(f"✓ 已导出 {len(with_prompt)} 集 prompts → {out_path.name}")

    @Slot()
    def _on_open_storyboard_file(self) -> None:
        if not self._current_project:
            return
        path = self._storyboard_file_path()
        if not path or not path.exists():
            QMessageBox.information(self, "提示", "分镜文件尚未生成")
            return
        self._open_in_explorer(path)

    @Slot()
    def _on_open_prompt_file(self) -> None:
        if not self._current_project:
            return
        path = self._prompt_file_path()
        if not path or not path.exists():
            QMessageBox.information(self, "提示", "提示词文件尚未生成")
            return
        self._open_in_explorer(path)

    # ============ v0.7.8.14：分镜界面"📥 导入剧本"按钮 handler ============
    @Slot()
    def _on_import_script_file(self) -> None:
        """v0.7.8.14：从本地 .txt/.md/.docx 加载剧本到当前剧集。

        用 Win32 原生多选 dialog（asset_panel._win32_open_files_dialog），
        绕开 QFileDialog / tkinter 在 PyInstaller EXE 里卡死的问题。
        多文件内容会依次追加到当前剧本（保留已有内容）。
        """
        if not self._current_episode or not self._current_project:
            QMessageBox.information(self, "提示", "请先在左侧选中一个剧集。")
            return
        from ui.asset_panel import _win32_open_files_dialog
        from ui.dialogs import _read_script_file
        # 优先定位到 outputs/<项目>/ 目录（用户的剧本常放在这里）
        proj_dir = self.config.outputs_dir / self._safe_dirname(self._current_project.name)
        initial = str(proj_dir) if proj_dir.exists() else ""
        files = _win32_open_files_dialog(
            title="选择剧本文件（可多选 .txt / .md / .docx）",
            file_filter=(
                "剧本文件 (*.txt;*.md;*.docx)\0*.txt;*.md;*.docx\0"
                "文本文件 (*.txt)\0*.txt\0"
                "Markdown (*.md)\0*.md\0"
                "Word 文档 (*.docx)\0*.docx\0"
                "所有文件 (*.*)\0*.*\0\0"
            ),
            initial_dir=initial,
        )
        if not files:
            return  # 用户取消
        success_parts: list[str] = []
        failed: list[tuple[str, str]] = []
        for fp in files:
            try:
                content = _read_script_file(fp)
                if content:
                    success_parts.append(f"=== {os.path.basename(fp)} ===\n{content}")
                else:
                    success_parts.append(f"=== {os.path.basename(fp)} ===\n（文件为空）")
            except Exception as e:  # noqa: BLE001
                failed.append((os.path.basename(fp), f"{type(e).__name__}: {e}"))
        if not success_parts:
            QMessageBox.warning(
                self, "导入失败",
                "所有文件都读取失败：\n" + "\n".join(f"  - {n}: {r}" for n, r in failed),
            )
            return
        # 追加到当前剧本（保留已有内容）
        ep = self._current_episode
        new_block = "\n\n".join(success_parts)
        if ep.script and ep.script.strip():
            merged = ep.script.rstrip() + "\n\n" + new_block
        else:
            merged = new_block
        # 写回 db
        try:
            self.db.update_episode(ep.id, script=merged)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"更新剧集失败：\n{e}")
            return
        # 同步落盘成 `<项目名>--第N集--剧本.txt`（v0.7.8.14 新增，便于"打开剧本"按钮）
        proj = self.db.get_project(ep.project_id)
        if proj:
            try:
                from core.generators import _safe_filename  # 复用
                # 剧本文件名跟分镜/提示词区分：用 `--剧本.txt`
                pdir = self.config.outputs_dir / self._safe_dirname(proj.name)
                pdir.mkdir(parents=True, exist_ok=True)
                sb_path = pdir / f"{self._safe_dirname(proj.name)}--第{ep.episode_num}集--剧本.txt"
                sb_path.write_text(merged, encoding="utf-8")
                log.info("dump script: %s (%d chars)", sb_path, len(merged))
            except Exception as e:
                log.warning("dump script to disk failed: %s", e)
        # 提示
        if failed:
            msg = (
                f"已成功导入 {len(success_parts)} 个文件到第{ep.episode_num}集剧本。\n"
                f"以下文件失败（已跳过）：\n"
                + "\n".join(f"  - {n}: {r}" for n, r in failed)
            )
            QMessageBox.information(self, "部分导入成功", msg)
        else:
            QMessageBox.information(
                self, "导入成功",
                f"已成功导入 {len(success_parts)} 个文件到第{ep.episode_num}集剧本。\n"
                f"（{len(merged)} 字,已保存到 db + 磁盘）",
            )
        # 刷新当前详情页
        # v1.1.5【致命 BUG 修复】:之前这里调 self._show_storyboard_tab(...)
        # 但这个方法不存在!整个文件 grep 0 处定义,只有这里 1 次引用。
        # 实际分镜 tab 的方法是 _show_episode_detail(line 789)。
        # 后果:用户点"📥 导入剧本"按钮 → AttributeError → Qt 弹"内部错误"
        # → 整个导入剧本功能是坏的,user 报告"按钮没反应"。
        # 修法:改名 + 前面加 _invalidate_all_ui_caches() 防 _episode_detail_cache
        # 命中旧 widget(id-only cache)。
        self._invalidate_all_ui_caches()
        ep_updated = self.db.get_episode(ep.id)
        if ep_updated:
            self._current_episode = ep_updated
            self._show_episode_detail(ep_updated, self._current_project)

    def _storyboard_file_path(self) -> Optional[Path]:
        if not self._current_episode or not self._current_project:
            return None
        return self._ep_txt_path(self._current_episode, self._current_project, "分镜词")

    def _prompt_file_path(self) -> Optional[Path]:
        if not self._current_episode or not self._current_project:
            return None
        return self._ep_txt_path(self._current_episode, self._current_project, "提示词")

    @staticmethod
    def _safe_dirname(name: str) -> str:
        """v0.7.8.13：清理项目名/剧集名里的 Windows 非法字符 (/\\:*?"<>|) 为 _。"""
        if not name:
            return "未命名"
        bad = '<>:"/\\|?*'
        out = "".join("_" if c in bad else c for c in str(name)).strip().rstrip(".")
        return out or "未命名"

    def _ep_txt_path(
        self,
        ep,
        proj=None,
        kind: str = "分镜词",
    ) -> Optional[Path]:
        """v0.7.8.13：剧集产物文件路径 = `<项目名>--第N集--<分镜词|提示词>.txt`。

        N 用阿拉伯数字（1, 2, 3...），跟 ep.episode_num 一致。双横线 `--` 分隔。
        不依赖 self._current_*，落盘时直接传 ep / proj 对象更稳健。
        """
        if not ep or not getattr(ep, "id", None):
            return None
        if proj is None:
            proj = self.db.get_project(ep.project_id) if self.db else None
        if not proj:
            proj = self._current_project if (
                self._current_project and self._current_project.id == ep.project_id
            ) else None
        if not proj:
            return None
        proj_dir = self.config.outputs_dir / self._safe_dirname(proj.name)
        proj_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{self._safe_dirname(proj.name)}--第{ep.episode_num}集--{kind}.txt"
        return proj_dir / filename

    def _dump_storyboard_to_disk(self, ep, content: str) -> None:
        """v0.7.8.13：把分镜文本同步落盘到 `<项目名>--第N集--分镜词.txt`。

        失败时仅 log，不抛（db 才是主存；磁盘文件是 _on_open_storyboard_file
        的"打开文件"按钮依赖的展示用，不影响任务结果）。
        """
        if not content:
            return
        path = self._ep_txt_path(ep, kind="分镜词")
        if not path:
            log.warning("dump_storyboard_to_disk: 路径计算失败 ep=%s", getattr(ep, "id", "?"))
            return
        try:
            path.write_text(content, encoding="utf-8")
            log.info("dump_storyboard_to_disk: %s (%d chars)", path, len(content))
        except Exception as e:
            log.warning("dump_storyboard_to_disk failed %s: %s", path, e)

    def _dump_prompt_to_disk(self, ep, content: str) -> None:
        """v0.7.8.13：把 video_prompt 文本同步落盘为 `<项目名>--第N集--提示词.txt`。"""
        if not content:
            return
        path = self._ep_txt_path(ep, kind="提示词")
        if not path:
            log.warning("dump_prompt_to_disk: 路径计算失败 ep=%s", getattr(ep, "id", "?"))
            return
        try:
            path.write_text(content, encoding="utf-8")
            log.info("dump_prompt_to_disk: %s (%d chars)", path, len(content))
        except Exception as e:
            log.warning("dump_prompt_to_disk failed %s: %s", path, e)

    def dump_all_episodes_to_disk(self) -> int:
        """v0.7.8.12：把 db 里所有有 storyboard / prompt 内容的剧集补写磁盘。

        用于 v0.7.8.12 之前已生成但没落盘的历史数据；返回补写文件数。
        启动时自动跑一次（_connect_db 后），保证"打开文件"按钮可用。
        """
        count = 0
        try:
            projs = self.db.list_projects() if hasattr(self.db, "list_projects") else []
        except Exception:
            projs = []
        for proj in projs:
            try:
                eps = self.db.list_episodes(proj.id)
            except Exception:
                continue
            for ep in eps:
                if ep.storyboard and ep.storyboard.strip():
                    self._dump_storyboard_to_disk(ep, ep.storyboard)
                    count += 1
                if ep.prompt and ep.prompt.strip():
                    self._dump_prompt_to_disk(ep, ep.prompt)
                    count += 1
        if count:
            log.info("dump_all_episodes_to_disk: 补写 %d 个文件", count)
        return count

    def _open_in_explorer(self, path: Path) -> None:
        try:
            if os.name == "nt":
                # Windows: explorer /select,<path>
                subprocess.Popen(["explorer", "/select,", str(path)])
            else:
                subprocess.Popen(["open", str(path.parent)])
        except Exception as e:
            QMessageBox.warning(self, "提示", f"打开失败: {e}")

    # ---------- 任务队列信号 ----------
    def _connect_task_queue(self) -> None:
        self.task_queue.task_started.connect(self._on_task_started)
        self.task_queue.task_phase_changed.connect(self._on_task_phase)
        self.task_queue.task_output.connect(self._on_task_output)  # 新增：实时输出
        self.task_queue.task_finished.connect(self._on_task_finished)
        self.task_queue.task_failed.connect(self._on_task_failed)
        self.task_queue.task_cancelled.connect(self._on_task_cancelled)

    @Slot(object)
    def _on_task_started(self, task: Task) -> None:
        self.task_status_widget.show_task(task)
        self.status_msg.setText(f"开始: {task.name}")
        self.log_buffer.append(f"开始: {task.name}")

    @Slot(object, str)
    def _on_task_phase(self, task: Task, phase: str) -> None:
        if self.task_status_widget.current_task is task:
            self.task_status_widget.update_phase(phase)

    @Slot(object, str)
    def _on_task_output(self, task: Task, line: str) -> None:
        """实时显示 hermes 的 stdout 输出到状态栏 + log buffer。

        之前没接这个信号，hermes 跑 20+ 分钟用户看不到任何东西以为卡死。
        现在状态栏会显示最后一行输出（截断），LogDialog 也有完整记录。
        """
        if self.task_status_widget.current_task is task:
            # 截断到 60 字符，避免状态栏变形
            short = line.strip()
            if len(short) > 60:
                short = short[:57] + "..."
            self.task_status_widget.update_phase(short)
        # 完整行进 log buffer（LogDialog 看）
        if line.strip():
            self.log_buffer.append(f"  {line.rstrip()}")

    @Slot(object)
    def _on_task_finished(self, task: Task) -> None:
        if self.task_status_widget.current_task is task:
            self.task_status_widget.mark_success()
        # 把结果回写 db（主线程里做）
        try:
            self._persist_task_result(task)
        except Exception as e:
            log.exception("persist task result failed")
            QMessageBox.warning(self, "提示", f"任务完成，但保存到 db 失败: {e}")
        # 1.5 秒后清空状态栏
        QTimer.singleShot(1500, self.task_status_widget.clear)
        self.status_msg.setText(f"✓ {task.name}")
        self.log_buffer.append(f"✓ 完成: {task.name}")

    @Slot(object, str)
    def _on_task_failed(self, task: Task, reason: str) -> None:
        if self.task_status_widget.current_task is task:
            self.task_status_widget.mark_failed(reason)
        # AssetImageTask 失败时把 image_status 标记为 failed
        if isinstance(task, AssetImageTask):
            try:
                # v0.7.7 重打 19 (user 反馈 root cause)：
                # 之前这里传了 image_prompt=getattr(task, "result_prompt", "")，
                # 任务失败时 result_prompt 没值（默认空），会把 db 里 user 精心编辑的
                # 1294 字 image_prompt 覆盖成空字符串！
                # project memory 明确："生图后写回 db 的字段必须是 image_path/image_status，
                # 绝不能包含 image_prompt"——失败路径漏修了。
                # 修法：跟 generators.py:975 成功路径一致，**不传 image_prompt**，
                # database.update_asset_image 默认 "" 也不传 → SQL 不会动 image_prompt 列。
                # （也可以在 database 里把 image_prompt 参数移除，更稳，但最小改动先这样）
                self.db.update_asset_image(
                    task._asset.id,
                    image_path="",
                    image_status="failed",
                )
                panel = self._current_asset_panel()
                if panel is not None:
                    fresh = self.db.get_asset(task._asset.id)
                    if fresh:
                        panel.update_asset(fresh)
            except Exception:
                log.exception("mark asset failed")
        QTimer.singleShot(3000, self.task_status_widget.clear)
        # 状态栏显示短摘要，完整 reason 进 LogBuffer（LogDialog 可看）
        self.status_msg.setText(f"✗ {task.name}: {reason[:80]}")
        self.log_buffer.append(f"✗ 失败: {task.name} — {reason}")
        # 状态栏点击可复制完整 reason
        self.status_msg.setToolTip(reason)

        # v0.7.8.5: 检测 401/403/404/500/502/503 等 HTTP 错误 → 弹一个**带
        # "换模型"按钮**的提示框,让用户能一键切到其他 active 配置重试。
        # **不**评论 key 真假,只展示 hermes 的 stderr 关键行,把决定权给用户。
        # (复刻 D:\剧本分镜助手\ 老的 server.py:任务失败时返回 stderr 给前端
        # 让前端用 toast 提示 "模型配置可能有问题"的友好 UX,manju 之前只把
        # stderr 塞 log_buffer,用户在主窗口看不到关键错误。)
        # v1.1.5【C3 修复】:之前只对 StoryboardTask / VideoPromptTask /
        # AssetExtractTask 三类 LLM task 弹"换模型"对话框,资产生图 / 批量
        # 生图 / 生视频失败时**不弹** → 换完 model 后没生效(401/403),用户
        # 看不到"换模型"提示,只能去 log_buffer 翻 stderr。
        # 修法:扩到所有 6 类 task。
        if task.__class__.__name__ in (
            "StoryboardTask",
            "VideoPromptTask",
            "AssetExtractTask",
            "AssetImageTask",
            "BatchAssetImageTask",
            "VideoTask",
        ):
            self._maybe_prompt_model_switch(task, reason)

    def _maybe_prompt_model_switch(self, task: Task, reason: str) -> None:
        """v0.7.8.5: hermes 失败时从 reason 提 HTTP 错误码,弹个"换模型"对话框。

        行为:
        - reason 含 "401" / "403" / "404" / "500" / "502" / "503" 之一 → 弹 QMessageBox
        - 弹窗里只显示 hermes stderr 关键行(后 500 字符),让用户自己判断
        - 提供"打开设置"按钮 → 一键打开 SettingsDialog 切 active 配置
        - 提供"关闭"按钮 → 取消,任务仍是 failed 状态

        不评论"key 是不是真失效",只把 hermes 给的事实展示给用户。
        """
        import re
        # 提 HTTP 错误码
        m = re.search(r"\b(401|403|404|500|502|503|timeout|Timeout|ConnectionError)\b", reason, re.IGNORECASE)
        if not m:
            return
        # 提关键 stderr 行(去掉 cmdline 那段无意义信息)
        tail = reason.split("--- output (tail) ---")[-1] if "--- output (tail) ---" in reason else reason
        tail = tail.strip()
        if len(tail) > 800:
            tail = "..." + tail[-800:]

        try:
            active = self.config.active_config
            active_name = active.get("name") or active.get("id") or "当前"
            all_cfgs = self.config.all_configs
            other_cfgs = [c for c in all_cfgs if c.get("id") != active.get("id")]
        except Exception:
            active_name = "当前"
            other_cfgs = []

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(f"hermes 失败: {task.name}")
        box.setText(
            f"任务 {task.name} 失败,hermes 返回了 `{m.group(0)}` 类错误。\n\n"
            f"当前 active 模型: **{active_name}**\n\n"
            f"软件已经把完整 stderr 写到 Log 标签页(底部「Log」按钮可看),"
            f"建议你先在浏览器登录对应平台确认 key 状态,\n"
            f"或直接切到其他 active 模型重试。"
        )
        box.setDetailedText(tail)
        if other_cfgs:
            box.setInformativeText(
                f"可用的其他 active 配置: " + " / ".join(
                    c.get("name") or c.get("id") for c in other_cfgs[:5]
                )
            )
        # "打开设置"按钮: 用户点这个就打开 SettingsDialog 切 active
        btn_settings = box.addButton("打开设置切换模型", QMessageBox.AcceptRole)
        btn_close = box.addButton("关闭", QMessageBox.RejectRole)
        box.setDefaultButton(btn_settings)
        box.exec()
        if box.clickedButton() is btn_settings:
            try:
                self._on_settings()
            except Exception as e:
                log.exception("打开设置失败: %s", e)

    @Slot(object)
    def _on_task_cancelled(self, task: Task) -> None:
        if self.task_status_widget.current_task is task:
            self.task_status_widget.mark_cancelled()
        QTimer.singleShot(1500, self.task_status_widget.clear)
        self.status_msg.setText(f"⏹ {task.name}: 已取消")
        self.log_buffer.append(f"⏹ 取消: {task.name}")

    @Slot()
    def _on_cancel_current_task(self) -> None:
        cur = self.task_status_widget.current_task
        if cur is None:
            return
        self.task_queue.cancel(cur.task_id)
        self.status_msg.setText(f"已请求取消: {cur.name}")

    def _persist_task_result(self, task: Task) -> None:
        """把任务结果回写到 db + 同步落盘 .md + 刷新当前详情。

        v0.7.8.12【同步落盘】_storyboard_file_path/_prompt_file_path
        依赖磁盘上的 .md 文件存在（"打开文件"按钮），但历史上只写 db 没
        落盘 → 报"分镜文件尚未生成"。现在 update_episode 后立即落盘。

        v1.1.4【统一 UI 缓存失效】任何 task 完成都可能改 ep / project / asset 字段。
        之前 v1.1.2 只对 StoryboardTask / VideoPromptTask 单独 invalidate
        _episode_detail_cache,资产提取 / 资产生图 / 批量生图完成后 UI
        仍不刷(因为 _asset_tab_cache 也是 id-only 命中走 early return,
        即使 db 写好 panel 也不显示新内容)。统一在入口处 invalidate 所有
        UI cache,下面各 task 分支再单独按需刷当前 tab 即可。
        """
        self._invalidate_all_ui_caches()
        if isinstance(task, StoryboardTask):
            ep_id = task._episode.id
            ep_fresh = self.db.get_episode(ep_id)
            if not ep_fresh:
                return
            self.db.update_episode(
                ep_id,
                storyboard=task.result_content,
                status="storyboard_done",
            )
            # v0.7.8.12：分镜完成后立即同步落盘到 outputs/<项目>/epNN_xxx_storyboard.md
            self._dump_storyboard_to_disk(ep_fresh, task.result_content)
            if self._current_episode and self._current_episode.id == ep_id:
                # v1.1.2【UI 刷新 bug 修复】:分镜刚生成完,ep 里的 storyboard /
                # status 字段都变了,必须 invalidate 缓存(否则 _show_episode_detail
                # 会因 v0.7.8.49 缓存命中走 early return,UI 永远显示旧的
                # "(暂无分镜)"和"状态: pending",即使 db 已经写好)。
                if (self._episode_detail_cache
                        and self._episode_detail_cache[0] == ep_id):
                    self._episode_detail_cache = None
                ep_updated = self.db.get_episode(ep_id)
                if ep_updated and self._current_project:
                    self._current_episode = ep_updated
                    self._show_episode_detail(ep_updated, self._current_project)
                    self._show_prompt_tab(ep_updated, self._current_project)
        elif isinstance(task, VideoPromptTask):
            ep_id = task._episode.id
            ep_fresh = self.db.get_episode(ep_id)
            if not ep_fresh:
                return
            self.db.update_episode(
                ep_id,
                prompt=task.result_content,
                prompt_status="done",
            )
            # v0.7.8.12：prompt 完成后立即同步落盘到 outputs/<项目>/epNN_xxx_video_prompt.md
            self._dump_prompt_to_disk(ep_fresh, task.result_content)
            # v0.7.8.32：新生成 prompt 后自动按 🎞️ Segment 切分灌入
            # ep.video_segments。v0.7.8.34：尊重用户在视频 tab 的手动编辑
            # (video_segments 已非空时返回 0,不覆盖)
            n_segs = self._auto_push_prompt_to_segments(ep_fresh, task.result_content)
            if self._current_episode and self._current_episode.id == ep_id:
                # v1.1.2【UI 刷新 bug 修复】:同 StoryboardTask,prompt/video
                # 字段变了也要 invalidate 缓存
                if (self._episode_detail_cache
                        and self._episode_detail_cache[0] == ep_id):
                    self._episode_detail_cache = None
                ep_updated = self.db.get_episode(ep_id)
                if ep_updated and self._current_project:
                    self._current_episode = ep_updated
                    self._show_episode_detail(ep_updated, self._current_project)
                    self._show_prompt_tab(ep_updated, self._current_project)
                    self._show_video_tab(ep_updated, self._current_project)
                    if n_segs > 0:
                        # 新推送,自动跳视频 tab
                        self.tabs.setCurrentIndex(3)
                        self.status_msg.setText(
                            f"✓ 已自动推送 {n_segs} 个 Segment 到视频页"
                        )
                    else:
                        # v0.7.8.34：用户已手动编辑过视频段(或有其他原因跳过)
                        # 不切 tab,在状态栏轻提示
                        if ep_fresh.video_segments and ep_fresh.video_segments.strip():
                            self.status_msg.setText(
                                "✓ prompt 已更新,视频段有手动编辑,未覆盖"
                            )
        elif isinstance(task, VideoTask):
            ep_id = task._episode.id
            ep_fresh = self.db.get_episode(ep_id)
            if not ep_fresh:
                return
            new_path = str(task.result_output_file) if task.result_output_file else ""
            # v0.6.19：把视频路径灌入 envelope 的对应段（按 segment_index）
            env = parse_video_segments(
                ep_fresh.video_segments or "",
                ep_num=ep_fresh.episode_num,
                ep_title=ep_fresh.title,
            )
            segs = env.get("segments", [])
            target_idx = task._request.segment_index if task._request else None
            if not segs:
                # envelope 是空（旧版纯文本被洗）→ 造 1 个段
                env = add_segment(env, title=f"第{ep_fresh.episode_num}集视频", text=ep_fresh.prompt or "")
                segs = env["segments"]
                target_idx = 0
            if target_idx is None or target_idx < 0 or target_idx >= len(segs):
                target_idx = 0
            target_seg = segs[target_idx]
            if new_path:
                env = update_segment_video(env, target_seg["id"], new_path, VIDEO_STATUS_READY)
            else:
                env = update_segment_video(env, target_seg["id"], "", "failed")
            raw = dump_video_segments(env)
            self.db.update_episode(ep_id, video_segments=raw)
            if self._current_episode and self._current_episode.id == ep_id:
                ep_updated = self.db.get_episode(ep_id)
                if ep_updated and self._current_project:
                    self._current_episode = ep_updated
                    self._show_video_tab(ep_updated, self._current_project)
        elif isinstance(task, AssetExtractTask):
            # 把解析出的资产条目 upsert 到 assets 表
            # v0.7.0：parse_asset_markdown 返回 4-tuple
            #   (kind, name, description, image_prompt)
            # image_prompt 来自 hermes 输出"中文指令词"段，作为生图 prompt
            project_id = task._project.id
            inserted = 0
            for kind, name, desc, image_prompt in task.result_assets:
                self.db.upsert_asset(
                    project_id, name, kind, desc, image_prompt=image_prompt
                )
                inserted += 1
            log.info(
                "AssetExtractTask persisted %d assets (含 image_prompt)",
                inserted,
            )
            # 刷新资产 tab
            panel = self._current_asset_panel()
            if panel is not None:
                # v0.6.16：把 result_asset_list 灌给 panel（启用"复制资产列表"按钮）
                result = task.result  # AssetExtractResult
                list_text = getattr(task, "result_asset_list", "")
                list_file = getattr(result, "asset_list_file", None) if result else None
                panel.set_asset_list(list_text, list_file)
                panel.refresh()
        elif isinstance(task, AssetImageTask):
            # 把图片路径写回 assets 行
            # v0.7.7 重打 20：update_asset_image 移除了 image_prompt 参数。
            # 成功路径这里之前把 result_prompt（实际上等于 _run_one_asset_image 里的 prompt 变量）
            # 当 image_prompt 写回 → 没问题但违反 project memory 规则（生图是只读消费）。
            # 删了就是，prompt 已经在 db 里不动。
            self.db.update_asset_image(
                task._asset.id,
                image_path=task.result_image_path,
                image_status="ready",
            )
            # 刷新资产 tab
            panel = self._current_asset_panel()
            if panel is not None:
                fresh = self.db.get_asset(task._asset.id)
                if fresh:
                    panel.update_asset(fresh)
        elif isinstance(task, BatchAssetImageTask):
            # v0.6.26：批量生图结束 → 刷新整个资产 tab
            panel = self._current_asset_panel()
            if panel is not None:
                panel.refresh()
            # 弹总结框
            r = task.result  # BatchAssetImageResult
            if r is not None:
                fail_text = ""
                if r.failures:
                    fail_lines = [f"  • {n}: {e[:80]}" for n, e in r.failures[:10]]
                    extra = "" if len(r.failures) <= 10 else f"\n  ... 共 {len(r.failures)} 个失败"
                    fail_text = "\n失败明细：\n" + "\n".join(fail_lines) + extra
                QMessageBox.information(
                    self, "批量生图完成",
                    f"共 {r.total} 个资产：\n"
                    f"  ✓ 成功 {r.success}\n"
                    f"  ✗ 失败 {r.failed}\n"
                    f"  ⏭ 跳过 {r.skipped}（已有图）"
                    + fail_text,
                )

    def _invalidate_all_ui_caches(self) -> None:
        """v1.1.4【统一 UI 缓存失效】清空所有 tab widget 缓存,下次切 tab
        触发 _show_*_tab 重建 / refresh。

        之前 v1.1.2 只在 StoryboardTask / VideoPromptTask 分支手工
        invalidate _episode_detail_cache,其他 task(AssetExtract /
        AssetImage / BatchAssetImage / 未来新增 task)完成后
        _asset_tab_cache 等 id-only cache 仍命中,UI 永远显示旧内容。
        现在统一在 _persist_task_result 入口调一次,任何 task 完成都会
        失效所有 tab 缓存,各 task 分支再按需 _show_*_tab 主动刷一次。

        性能:cache 失效 → 下次切 tab 走 cache miss 路径重建 widget。
        对于分镜/视频 tab(700+ widget)会有 ~200-800ms 卡顿,这是可
        接受的代价(用户刚点了"生成"按钮,期望看到结果,卡 0.5s OK)。
        对于资产 tab(纯 list 重建,16+ 资产 × 6 widget),重建很快。
        """
        self._episode_detail_cache = None
        self._prompt_tab_cache = None
        self._video_tab_cache = None
        self._asset_tab_cache = None
        self._project_overview_cache = None

    @Slot()
    def _on_open_log(self) -> None:
        """打开日志面板。"""
        dlg = LogDialog(self.log_buffer, parent=self)
        dlg.show()  # 非模态 — 用户可继续看 Tab / 提交任务

    def _show_log_tab(self) -> None:
        """v0.7.8.2：日志 Tab（第 6 个）填上真实视图。

        之前是 "待迁移" 占位；现在直接嵌一个 QPlainTextEdit 绑 self.log_buffer.changed，
        跟状态栏 📋 日志 按钮打开的 LogDialog 共用同一份 buffer。
        """
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        # 顶部信息行
        info = QLabel("")
        info.setStyleSheet("color: #666;")
        outer.addWidget(info)

        # 日志正文
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        font = view.font()
        font.setFamily("Consolas, 'Courier New', monospace")
        view.setFont(font)
        outer.addWidget(view, 1)

        # 底部按钮
        bar = QHBoxLayout()
        btn_clear = QPushButton("🗑 清空日志")
        btn_clear.clicked.connect(self.log_buffer.clear)
        bar.addWidget(btn_clear)
        bar.addStretch(1)
        outer.addLayout(bar)

        def _refresh() -> None:
            n = len(self.log_buffer)
            info.setText(f"共 {n} 条记录（最新在上）")
            body = "\n".join(self.log_buffer.lines())
            view.setPlainText(body)
            cur = view.textCursor()
            cur.movePosition(cur.MoveOperation.Start)
            view.setTextCursor(cur)

        self.log_buffer.changed.connect(_refresh)
        _refresh()

        self._replace_tab(5, w, "📜 日志")

    # ---------- 设置 ----------
    @Slot()
    def _on_settings(self) -> None:
        dlg = SettingsDialog(ROOT / "config" / "hermes_api.json", parent=self)
        # v0.7.8.49:非模态(原 exec 会阻塞主窗口,构造时整软件冻屏)。
        # 监听 destroyed 信号:用户关闭时刷新 Config 单例。
        def _on_dlg_destroyed(_obj=None) -> None:
            from core.config import Config
            try:
                Config.reload(ROOT / "config" / "hermes_api.json")
                self.status_msg.setText("✓ 配置已刷新")
            except Exception as e:
                self.status_msg.setText(f"配置刷新失败: {e}")
        dlg.destroyed.connect(_on_dlg_destroyed)
        # 单独窗口(不挂主窗口 minimize 链),用户可一边配置一边看主窗口
        dlg.setWindowFlags(dlg.windowFlags() | Qt.WindowType.Window)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    # ---------- 帮助 ----------
    @Slot()
    def _on_about(self) -> None:
        # v0.7.8.2：版本从 APP_TITLE 派生（之前硬编码 0.1.0 跟实际 v0.7.8 不符）
        version = APP_TITLE.split(" ", 1)[-1] if " " in APP_TITLE else APP_TITLE
        QMessageBox.about(
            self, "关于",
            f"<h3>漫剧助手X-1</h3>"
            f"<p>版本: {version}</p>"
            f"<p>技术栈: Python {__import__('sys').version.split()[0]} + PySide6</p>"
            f"<p>数据库: SQLite（本地）</p>"
            f"<p>项目根: {ROOT}</p>"
            f"<p>db 路径: {ROOT / 'data' / 'projects.db'}</p>"
            f"<p>配置: {self.config.path}</p>"
            f"<p>hermes: {self.config.hermes_exe}</p>"
            f"<p>outputs: {self.config.outputs_dir}</p>"
        )

    @Slot()
    def _show_db_info(self) -> None:
        cur = self.con.cursor()
        cur.execute("SELECT key, value FROM _meta")
        meta_rows = cur.fetchall()
        cur.execute("SELECT COUNT(*) FROM projects")
        n_proj = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM episodes")
        n_eps = cur.fetchone()[0]
        text = "<h3>数据库信息</h3>"
        text += f"<p>项目: {n_proj}    剧集: {n_eps}</p><hr>"
        text += "<h4>_meta</h4><ul>"
        for k, v in meta_rows:
            text += f"<li><b>{k}</b>: {v}</li>"
        text += "</ul>"
        QMessageBox.information(self, "数据库信息", text)

    @Slot()
    def _open_outputs_dir(self) -> None:
        out = self.config.outputs_dir
        out.mkdir(parents=True, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(str(out))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["open", str(out)])
        except Exception as e:
            QMessageBox.warning(self, "提示", f"打开失败: {e}")

    # ---------- 关闭 ----------
    def closeEvent(self, event) -> None:
        log.info("MainWindow closing, shutting down task queue ...")
        try:
            self.task_queue.stop()
        except Exception:
            log.exception("task queue shutdown error")
        super().closeEvent(event)
