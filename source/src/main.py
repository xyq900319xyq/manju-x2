"""漫剧助手X-1 入口。"""
import logging
import os
import sys
from pathlib import Path


def _ensure_home_env() -> None:
    """v0.7.4：补 USERPROFILE / HOME / HERMES_HOME 到 os.environ。

    背景：
    - EXE 启动时（PyInstaller / 双击）可能缺 USERPROFILE，导致 hermes 子进程
      调 `Path.home()` 抛 `RuntimeError("Could not determine home directory.")`，
      profile override 失败，hermes 用 default profile（不是 asset-designer 等），
      LLM 调用走错配置，95s 后 exit 1。
    - 老软件 launcher.py 之前在系统里设了 `HERMES_HOME=D:\\hermes`（stale 值），
      EXE 进程从 explorer 继承后传给 hermes 子进程。hermes 内部按
      `Path(hermes_home or HERMES_HOME or Path.home()/.hermes)` 找 HOME，
      直接用了 D:\\hermes，在 D:\\hermes\\profiles\\asset-designer\\ 找 config.yaml
      —— 不存在（profile 在 C:\\Users\\Administrator\\.hermes\\），
      导致 asset designer 失败。
    - 本函数在 EXE 启动时（非源码模式）把 USERPROFILE 和 HERMES_HOME 设好，
      确保后续所有 subprocess 都能正确找到 hermes 配置。

    v0.7.8 修：PyInstaller 打包后 bootloader 的 Python 环境缺少标准库路径，
    需要设置 PYTHONHOME 指向 _internal 目录。
    """
    # v0.7.8: 设置 PYTHONHOME 让打包后的 Python 能找到标准库
    # - _internal/base_library.zip 是 stdlib（fix_package.py step2 打的）
    # - _internal/*.pyd 是扩展模块（fix_package.py step3 复制的）
    # - PYTHONHOME 指向 _internal，base_library.zip 在该目录下被识别
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        # exe_dir = dist/漫剧助手X-1/
        # _internal = dist/漫剧助手X-1/_internal/
        internal = exe_dir / "_internal"
        if internal.exists():
            os.environ["PYTHONHOME"] = str(internal)
            sys.prefix = str(internal)
            sys.exec_prefix = str(internal)

    # 确保 USERPROFILE 存在（hermes 子进程需要）
    need = [k for k in ("USERPROFILE", "HOME") if not os.environ.get(k)]
    home = None
    if need:
        home = os.path.expanduser("~")
        if not home or home == "~":
            home = r"C:\Users\Administrator"
            logging.getLogger("manju").warning(
                "os.path.expanduser('~') 拿不到 home，用 fallback: %s", home
            )
        for k in need:
            os.environ[k] = home
            logging.getLogger("manju").info("补 env %s=%s", k, home)

    # 显式重写 HERMES_HOME = config.hermes_home（覆盖 stale 值）
    try:
        from core.config import Config
        c = Config.get()
        hermes_home = str(c.hermes_home)
        old = os.environ.get("HERMES_HOME", "")
        if old != hermes_home:
            os.environ["HERMES_HOME"] = hermes_home
            logging.getLogger("manju").info(
                "重写 HERMES_HOME: %r -> %r", old, hermes_home
            )

        # v0.7.6：首次启动时从 D 盘复制完整 SKILL.md / SOUL.md / config.yaml
        # 到 manju 自带 resources/hermes/profiles/<name>/。D 盘是老 software
        # 用的资源（SKILL.md v2.2.0 完整版 240 行，定义所有输出字段格式），
        # manju 跟老 software 调 hermes 时加载的资源完全一致，LLM 输出
        # manju parser 能解析的 `### 人物1：陈戈` 格式。
        # 只复制一次（用 config.yaml 是否存在判重），后续启动零成本。
        try:
            profiles_to_init = set()
            for prof_id in ("storyboard", "video_prompt", "asset"):
                try:
                    pname = c.profile_for(prof_id)
                except Exception:
                    continue
                profiles_to_init.add(pname)
            for pname in profiles_to_init:
                c.ensure_local_hermes_profile(pname)
                # v0.7.6 强化：复制完 D 盘 config.yaml 后立刻 inject 一次
                # 用户 active model，避免首次启动到首次调 hermes 之间窗口期
                # manju profile 还残留 D 盘默认的 agnes 配置。
                # 没写死 model：inject_api_to_profile 每次都从 hermes_api.json
                # 读 "active" 字段，用户在 settings 切换后下次启动就生效。
                try:
                    c.inject_api_to_profile(pname)
                except Exception as _ie:
                    logging.getLogger("manju").warning(
                        "启动时 inject_api 失败 %s: %s", pname, _ie,
                    )
        except Exception as e:
            logging.getLogger("manju").warning("初始化本地 hermes profile 失败: %s", e)
    except Exception as e:
        logging.getLogger("manju").warning("重写 HERMES_HOME 失败: %s", e)


def _find_project_root() -> Path:
    """找项目根（包含 config/hermes_api.json 的目录）。

    优先级：
    1. 源码运行（python src/main.py）：main.py 的 parent.parent
    2. PyInstaller 打包后：从 EXE 目录向上找（最多 5 层），找到含 config/hermes_api.json 的目录
    3. 找不到：EXE 所在目录
    """
    if getattr(sys, "frozen", False):
        # PyInstaller 模式：从 EXE 所在目录向上找
        cur = Path(sys.executable).parent
        for _ in range(5):
            if (cur / "config" / "hermes_api.json").exists():
                return cur
            if cur.parent == cur:
                break
            cur = cur.parent
        return Path(sys.executable).parent
    # 源码运行
    return Path(__file__).resolve().parent.parent


ROOT = _find_project_root()
# v0.7.8.17:把 ROOT 写到 sys._manju_root,generators.py 用它找 hermes_hijack 目录
sys._manju_root = ROOT
# 让 import 能找到 src 包（源码运行）
SRC = ROOT / "src"
if not getattr(sys, "frozen", False) and str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _setup_logging() -> None:
    """把 Python logging 落到 logs/manju.log。

    EXE `--windowed` 模式下 stderr 看不到，必须落盘才能调试。
    关键路径（_on_click_extract / _enqueue_task / _on_task_failed 等）都会
    log.warning / log.exception，落地到 logs/manju.log 用户可查。

    v0.7.8.37c fix:FileHandler 必须 line-buffered (delay=False + flush)，
    否则 taskkill /F 杀进程时 Python log buffer 没 flush,关键诊断 log
    (如 _reload_projects / 启动失败) 全丢。line buffered = 每次 write 立即
    进 OS buffer,Windows 上 OS 进程被杀时也能保留一部分。
    """
    log_dir = ROOT / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "manju.log"
    fmt = "%(asctime)s %(levelname)s %(name)s: %(message)s"
    # v0.7.8.37c fix:delay=False 让 FileHandler 不缓冲,line-buffered
    fh = logging.FileHandler(log_path, encoding="utf-8", mode="a", delay=False)
    sh = logging.StreamHandler(sys.stderr)
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[fh, sh],
        force=True,  # 覆盖之前的 basicConfig
    )
    logging.getLogger("manju").info("=" * 60)
    logging.getLogger("manju").info(f"启动  ROOT={ROOT}  log={log_path}")


from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from ui.main_window import MainWindow


def _load_theme(app: QApplication) -> bool:
    """v0.7.0：加载暗色卡片主题 QSS。

    找 QSS 优先级：
    1. ROOT/assets/theme.qss（开发模式 + 打包后的 EXE 都能用）
    2. _MEIPASS/assets/theme.qss（PyInstaller 单文件模式）
    """
    candidates = []
    # 1. 相对 ROOT
    candidates.append(ROOT / "assets" / "theme.qss")
    # 2. PyInstaller 单文件 _MEIPASS
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "assets" / "theme.qss")
    # 3. EXE 旁
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent / "assets" / "theme.qss")

    for p in candidates:
        if p.exists():
            try:
                qss = p.read_text(encoding="utf-8")
                app.setStyleSheet(qss)
                logging.getLogger("manju").info(f"已加载主题: {p}")
                return True
            except Exception as e:  # noqa: BLE001
                logging.getLogger("manju").warning(f"加载主题失败 {p}: {e}")
    logging.getLogger("manju").warning("未找到 theme.qss，使用默认样式")
    return False


def _run_first_run_wizard(project_root: Path) -> bool:
    """v1.0.0 用户版:首次启动检测 + QWizard 弹窗。

    触发条件(任一满足即跳过):
    1. config/secrets.bin 已存在 → 已配过 → 跳过
    2. hermes_api.json 里任意 LLM config 的 api_key 非空(dev 模式手动填过)→ 跳过

    取消:返回 False(main.py 应 sys.exit(0))。
    完成:返回 True(继续 main)。
    """
    from core import secret_store
    from ui.first_run_wizard import FirstRunWizard

    if secret_store.has_secrets(project_root):
        log.info("secrets.bin 已存在,跳过首次启动 wizard")
        return True
    # dev 模式兜底:hermes_api.json 已有非空 api_key → 跳过
    try:
        with open(project_root / "config" / "hermes_api.json", "r", encoding="utf-8") as f:
            import json as _json
            _d = _json.load(f)
        has_any_key = any(
            (c.get("api_key") or "").strip()
            for c in (_d.get("configs") or [])
        )
        if has_any_key:
            log.info("hermes_api.json 已有 LLM api_key(dev 模式),跳过首次启动 wizard")
            return True
    except Exception as e:  # noqa: BLE001
        log.warning("检测 hermes_api.json 现有 key 失败: %s", e)

    log.info("首次启动,弹出配置 wizard")
    w = FirstRunWizard(project_root, parent=None)
    from PySide6.QtWidgets import QWizard
    if w.exec() == QWizard.DialogCode.Accepted:
        return True
    log.info("用户取消首次启动 wizard,退出")
    return False


def main() -> int:
    # v0.7.3:必须在 QApplication 之前补 home env(影响 hermes 子进程找 profile)
    _ensure_home_env()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("漫剧助手X-2")
    app.setApplicationDisplayName("漫剧助手X-2")
    app.setOrganizationName("ManjuTools")
    app.setApplicationVersion("1.0.0")

    _setup_logging()

    # v1.0.0 用户版：创建单实例 mutex，让 Inno Setup 的 NeedRestart() 检测到
    # Inno 脚本里的 CheckForMutexes('漫剧助手X-2_InstanceMutex') 据此判断
    # 旧 EXE 是不是在跑。如果在跑，提示用户关掉再装（或自动 kill）。
    from PySide6.QtCore import QSharedMemory
    _single_instance = QSharedMemory("漫剧助手X-2_InstanceMutex")
    if not _single_instance.create(1):
        # 已经在跑（理论上 OS 会阻止双开，这里是兜底）
        log.warning("检测到漫剧助手X-2 已在运行（mutex 已存在），继续启动（多窗口）")

    # v0.7.0：先加载 QSS，再创建窗口
    _load_theme(app)

    # v1.0.0 用户版：首次启动检测 + QWizard 弹窗
    # 必须在 MainWindow 之前，让用户在第一次看到主窗口前就填好 API key
    if not _run_first_run_wizard(ROOT):
        return 0

    try:
        window = MainWindow(ROOT)
    except Exception as e:
        logging.getLogger("manju").exception("MainWindow 构造失败")
        print(f"FATAL: {e}", file=sys.stderr)
        return 1
    window.show()

    # v1.0.0 用户版：启动后台检查更新
    # 必须在 window.show() 之后，让 UI 先渲染出来再拉 GitHub
    try:
        from core.updater import UpdateChecker
        window._updater = UpdateChecker(
            project_root=ROOT,
            current_version="1.0.0",
            parent=window,
        )
        # 监听信号：红点 / 状态栏提示
        window._updater.update_available.connect(window._on_update_available)
        window._updater.no_update.connect(window._on_no_update)
        window._updater.start_async(force=False)
    except Exception as e:  # noqa: BLE001
        logging.getLogger("manju").warning("启动 updater 失败: %s", e)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
