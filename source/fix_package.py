"""v0.7.8.1：PyInstaller 6 + uv Python 打包修正。

PyInstaller 6.10.0 + uv 管理的 Python 3.11 联动有几个已知坑：
1. stdlib .py 没被打包（PyInstaller 走 site-packages 路线，uv 把 stdlib
   放在 cpython-3.11-windows-x86_64-none/Lib/，不在 site-packages）。
   → 强制把 stdlib .py 打包到 base_library.zip。
2. DLLs/ 里的 .pyd（_sqlite3.pyd / _ssl.pyd / _tkinter.pyd 等）没被复制。
   → 必须手动从 cpython-3.11-windows-x86_64-none/DLLs/ 复制到 _internal/。
3. ui/ core/ 本地包需要 `pathex=[src]`（spec 文件已加）。

本脚本：
- 调用 pyinstaller 重新打包（用 漫剧助手X-1.spec）
- 修 base_library.zip：把 stdlib 的 .py 加进去
- 复制 DLLs/ 下的 .pyd 和 .dll 到 _internal/

前置：build_full.bat 已跑过 pyinstaller --onedir --name "漫剧助手X-1" --add-data
"resources;resources" src\main.py 至少一次（产生 dist/ 目录）。
本脚本是修补脚本。
"""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPEC = ROOT / "漫剧助手X-1.spec"
DIST = ROOT / "dist" / "漫剧助手X-1"
INTERNAL = DIST / "_internal"

# uv 管理的 Python 3.11.15 stdlib 位置
UV_PYTHON = Path(
    r"C:\Users\Administrator\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none"
)
UV_LIB = UV_PYTHON / "Lib"
UV_DLLS = UV_PYTHON / "DLLs"


def step0_patch_spec() -> None:
    """v0.7.8.2:PyInstaller 初始命令(`pyinstaller src/main.py`)会生成默认 spec,
    覆盖手改的 pathex=[SRC_DIR] / hiddenimports 显式包名,导致 EXE 启动报
    ModuleNotFoundError: No module named 'ui'。本步在跑 pyinstaller spec 之前
    自动把这两处加回 spec,让 spec 文件幂等。
    """
    print("[0/3] Patching spec file (idempotent)...")
    if not SPEC.exists():
        sys.exit(f"Spec not found: {SPEC}")

    text = SPEC.read_text(encoding="utf-8")
    original = text

    # 0. SRC_DIR 定义(pathex 引用)——PyInstaller 自动 spec 里没这个,需要补
    src_dir_def = "SRC_DIR = os.path.abspath('src')"
    if "SRC_DIR" not in text:
        # 在 from PyInstaller... 行后面插入 import os + SRC_DIR 定义
        if "from PyInstaller.utils.hooks import collect_submodules" in text:
            text = text.replace(
                "from PyInstaller.utils.hooks import collect_submodules",
                "from PyInstaller.utils.hooks import collect_submodules\n"
                "import os\n"
                f"\n{src_dir_def}\n",
                1,
            )
            print("  + SRC_DIR 定义已补")
        else:
            print("  WARNING: 找不到 from PyInstaller.utils.hooks 行,SRC_DIR 未补")

    # 1. pathex=[] → pathex=[SRC_DIR]
    #    只匹配 a.Analysis 块里的 "pathex=[]"(行级别),不误改注释里的字符串
    if "pathex=[SRC_DIR]" not in text:
        new_lines = []
        replaced = False
        for line in text.splitlines(keepends=True):
            stripped = line.lstrip()
            if not replaced and stripped.startswith("pathex=") and "[]" in line:
                # 找到 pathex=[] 形式,替换
                line = line.replace("pathex=[]", "pathex=[SRC_DIR]", 1)
                replaced = True
                print("  + pathex=[] → pathex=[SRC_DIR] (a.Analysis)")
            new_lines.append(line)
        text = "".join(new_lines)

    # 2. hiddenimports 末尾追加 ui / core 显式入口(避免 collect_submodules 漏)
    #    缩进 0——跟 hiddenimports 列表顶部的 "hiddenimports += ..." 同一级
    sentinel = "hiddenimports += ['ui', 'core', 'ui.main_window', 'ui.asset_panel', 'ui.settings_dialog']"
    if sentinel not in text:
        marker = "hiddenimports += collect_submodules('core')\n"
        if marker in text:
            text = text.replace(
                marker,
                marker + sentinel + "\n",
                1,
            )
            print("  + hiddenimports 显式入口已追加")

    if text != original:
        SPEC.write_text(text, encoding="utf-8")
        print("  spec 已写入")
    else:
        print("  spec 已是最新,无需改动")

    # v0.7.8.20:EXE 块 console=True 会弹黑色运行框,改为 False 隐藏
    # 改 build_full.bat 重生成 spec 时也会被覆盖,这里幂等 patch
    text2 = SPEC.read_text(encoding="utf-8")
    if "console=True" in text2:
        text2 = text2.replace("console=True", "console=False", 1)
        SPEC.write_text(text2, encoding="utf-8")
        print("  console=True → console=False (EXE 隐藏黑框)")


def step1_rerun_pyinstaller() -> None:
    """重跑 pyinstaller 用新 spec。"""
    print("[1/3] Running PyInstaller with fixed spec...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        SPEC.name,
    ]
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        sys.exit(f"PyInstaller failed (rc={result.returncode})")


def step2_fix_base_library() -> None:
    """把 stdlib 的 .py 打进 base_library.zip。"""
    print("[2/3] Patching base_library.zip with stdlib .py...")
    blz = INTERNAL / "base_library.zip"
    # v0.7.8.30:PyInstaller 6.10 + uv 联动,COLLECT 偶尔不会把 base_library.zip
    # 拷进 _internal/。如果 _internal 里没有,从 build/<name>/ 拿一个补上。
    if not blz.exists():
        build_blz = ROOT / "build" / SPEC.stem / "base_library.zip"
        if build_blz.exists():
            print(f"  + _internal 缺失,补 build/{SPEC.stem}/base_library.zip")
            shutil.copy2(build_blz, blz)
        else:
            sys.exit(f"base_library.zip not found at {blz} (build 也没)")
    # 二次校验:补完后必须存在
    if not blz.exists():
        sys.exit(f"base_library.zip still missing at {blz}")

    # 临时移到 site-packages 旁的位置（PyInstaller 期望它在那里）
    site_packages = INTERNAL / "site-packages"
    site_packages.mkdir(exist_ok=True)
    shutil.move(str(blz), str(site_packages / "base_library.zip"))

    # 把 stdlib 的 .py 全部塞进去
    with zipfile.ZipFile(site_packages / "base_library.zip", "a", zipfile.ZIP_DEFLATED) as z:
        count = 0
        for py in UV_LIB.rglob("*.py"):
            # base_library.zip 里路径是相对 Python Lib 的
            arc = str(py.relative_to(UV_LIB)).replace("\\", "/")
            try:
                z.write(py, arcname=arc)
                count += 1
            except Exception as e:  # noqa: BLE001
                print(f"  skip {arc}: {e}")
        print(f"  +{count} stdlib .py files added")

    # 移回 _internal
    shutil.move(str(site_packages / "base_library.zip"), str(blz))
    shutil.rmtree(site_packages, ignore_errors=True)


def step3_copy_dlls() -> None:
    """复制 DLLs/ 下的 .pyd 和 .dll 到 _internal/。

    PyInstaller 6 + uv 漏打包这些。手动从 cpython DLLs/ 复制。
    """
    print("[3/3] Copying DLLs/ → _internal/...")
    if not UV_DLLS.exists():
        sys.exit(f"uv Python DLLs/ not found at {UV_DLLS}")

    # 关键 .pyd：app 用到的 _sqlite3, _ssl, _ctypes, _hashlib, _tkinter 等
    needed = [
        # .pyd 扩展模块
        "_asyncio.pyd",
        "_bz2.pyd",
        "_ctypes.pyd",
        "_decimal.pyd",
        "_elementtree.pyd",
        "_hashlib.pyd",
        "_lzma.pyd",
        "_msi.pyd",
        "_multiprocessing.pyd",
        "_overlapped.pyd",
        "_queue.pyd",
        "_socket.pyd",
        "_sqlite3.pyd",
        "_ssl.pyd",
        "_uuid.pyd",
        "_zoneinfo.pyd",
        "pyexpat.pyd",
        "select.pyd",
        "unicodedata.pyd",
        "winsound.pyd",
        # .dll 动态库
        "libcrypto-3-x64.dll",
        "libffi-8.dll",
        "libssl-3-x64.dll",
        "sqlite3.dll",
    ]
    copied = 0
    for name in needed:
        s = UV_DLLS / name
        d = INTERNAL / name
        if s.exists() and not d.exists():
            shutil.copy2(s, d)
            copied += 1
    print(f"  Copied {copied} files (out of {len(needed)} needed)")
    print(f"  EXE size: {sum(p.stat().st_size for p in INTERNAL.rglob('*') if p.is_file()) / 1024 / 1024:.1f} MB")


def step4_copy_hermes_hijack() -> None:
    """v0.7.8.17:把 hermes_hijack/ 复制到 dist/ 根目录(不是 _internal/)。
    generators.py 设 PYTHONPATH=DIST/hermes_hijack 给 hermes 子进程,
    PyInstaller 启动时 import sitecustomize 强制 aiohttp trust_env=True。
    """
    src = ROOT / "hermes_hijack"
    if not src.exists():
        print(f"  [warn] {src} 不存在,跳过 (跳过 sitecustomize hook)")
        return
    dst = DIST / "hermes_hijack"
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(src, dst)
    print(f"  + copied hermes_hijack/ to {dst}")


def main() -> None:
    if not SPEC.exists():
        sys.exit(f"Spec file not found: {SPEC}")
    # v0.7.8.3:不再要求 dist 必须预先存在。PyInstaller 自己会创建 dist/<name>/
    # (DIST 缺失时,以前 fix_package.py 直接 sys.exit,现在 step1 让 pyinstaller
    # 自己建。前提:用户需要先跑过 build_full.bat 一次,生成默认 spec+dist,
    # 或者在没 dist 时先手动跑一次 `pyinstaller --onedir ... src\main.py`
    # 再跑 fix_package.py。
    if not DIST.exists():
        print(f"[warn] {DIST} 不存在,PyInstaller 会自己创建。继续。")
    # 允许 build_full.bat 先跑 pyinstaller，跳过本脚本的 step1
    skip_pyinstaller = "--skip-pyinstaller" in sys.argv
    # v0.7.8.2:无论是否 skip,都先 patch spec 一次(spec 幂等),
    # 这样 spec 文件不依赖人手维护,build_full.bat 跑下来一定包含 pathex/hiddenimports
    step0_patch_spec()
    if not skip_pyinstaller:
        step1_rerun_pyinstaller()
    step2_fix_base_library()
    step3_copy_dlls()
    step4_copy_hermes_hijack()
    print("\n✓ Build fixed. EXE at: dist\\漫剧助手X-1\\漫剧助手X-1.exe")
    print("  Now set PYTHONHOME to dist\\漫剧助手X-1\\_internal or just double-click.")


if __name__ == "__main__":
    main()
