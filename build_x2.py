"""漫剧助手X-2 打包脚本。

把 D:\\漫剧助手\\manju-x2\\source\\ 用 PyInstaller 打成 EXE,
然后调 Inno Setup 编译 .iss 出 Setup.exe。

用法:
    cd D:\\漫剧助手\\manju-x2
    python build_x2.py
"""
import os
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Tuple

ROOT = Path(r'D:\漫剧助手\manju-x2')
SOURCE = ROOT / 'source'
RELEASE = ROOT / 'release'
INSTALLER = ROOT / 'installer'
SPEC = SOURCE / '漫剧助手X-2.spec'  # 拷贝后改过名
DIST = SOURCE / 'dist' / '漫剧助手X-2'

PYTHON = sys.executable

# Inno Setup 候选路径(自动扫描,user 装到哪都能找到)
_ISCC_CANDIDATES = [
    r'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
    r'C:\Program Files\Inno Setup 6\ISCC.exe',
    r'D:\InnoSetup6\ISCC.exe',
    r'D:\Inno Setup 6\ISCC.exe',
    r'E:\InnoSetup6\ISCC.exe',
    r'E:\Inno Setup 6\ISCC.exe',
    # user 自定义目录
    r'C:\ISCC\ISCC.exe',
    r'D:\ISCC\ISCC.exe',
]


def _find_iscc() -> str | None:
    """扫描 PATH + 常见安装目录找 ISCC.exe。"""
    # 1) PATH
    w = shutil.which('ISCC')
    if w:
        return w
    # 2) 候选路径
    for p in _ISCC_CANDIDATES:
        if Path(p).exists():
            return p
    # 3) 扫 Program Files (x86) / Program Files
    import os
    bases = [
        r'C:\Program Files (x86)',
        r'C:\Program Files',
        'D:' + os.sep,
        'E:' + os.sep,
    ]
    for base in bases:
        try:
            for name in os.listdir(base):
                if name.lower().startswith('inno setup'):
                    cand = Path(base) / name / 'ISCC.exe'
                    if cand.exists():
                        return str(cand)
        except (FileNotFoundError, PermissionError, OSError):
            pass
    return None


def step(msg: str):
    print(f'\n=== {msg} ===')


def run(cmd: list, cwd: Path = None, check: bool = True):
    print(f'$ {" ".join(cmd)}  (cwd={cwd or os.getcwd()})')
    r = subprocess.run(cmd, cwd=str(cwd) if cwd else None)
    if check and r.returncode != 0:
        sys.exit(f'FAIL: {" ".join(cmd)} exit={r.returncode}')


def rename_spec():
    src = SOURCE / '漫剧助手X-1.spec'
    dst = SOURCE / '漫剧助手X-2.spec'
    if src.exists() and not dst.exists():
        shutil.copy2(src, dst)
    return dst


def main():
    step('0) 准备 spec')
    spec = rename_spec()
    if not spec.exists():
        sys.exit(f'找不到 spec: {spec}')
    print(f'  spec: {spec}')

    step('1) 清理旧 dist / build')
    for d in [SOURCE / 'dist', SOURCE / 'build']:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
            print(f'  rm {d}')

    step('2) PyInstaller 打包 manju')
    run([PYTHON, '-m', 'PyInstaller', '--clean', '--noconfirm', str(spec)], cwd=SOURCE)
    if not DIST.exists():
        sys.exit(f'PyInstaller 没产出 {DIST}')

    step('3) 把 hermes.exe 拷到 <install_root>\\hermes\\\(独立于 manju EXE,便于单独更新)')
    hermes_dist = SOURCE / 'hermes_dist'
    if not hermes_dist.exists():
        print(f'  ⚠ 找不到 {hermes_dist},跳过 hermes 嵌入(需先跑 PyInstaller 打包 hermes)')
        print(f'  单独跑: pyinstaller D:\\漫剧助手\\manju-x2\\installer\\hermes.spec --clean --noconfirm')
        print(f'  然后:  xcopy /E /I /Y D:\\hermes\\hermes-agent\\dist\\hermes D:\\漫剧助手\\manju-x2\\source\\hermes_dist')
    else:
        target = DIST / 'hermes'
        target.mkdir(parents=True, exist_ok=True)
        for item in hermes_dist.iterdir():
            dst = target / item.name
            if item.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(item, dst)
            else:
                shutil.copy2(item, dst)
        print(f'  ✓ hermes 嵌入 {target} (随 Inno Setup Source dist\\漫剧助手X-2\\* → {{app}}\\hermes\\)')

    # v1.1.5.1【关键修复】:把 manju 自带的 hermes profiles 拷到 <dist>/resources/hermes/profiles/
    # 原因:Config.hermes_home 探测顺序第 2 优先选 <project_root>/resources/hermes/ (config.py:657-658)
    # + ensure_local_hermes_profile 把 profiles 写到
    # <project_root>/resources/hermes/profiles/<name>/ (config.py:1151)。
    # 旧 build_x2.py step 3 只拷了 hermes.exe 到 dist/.../hermes/,**没**拷 profiles,
    # 导致 EXE 安装后 <install_root>/resources/hermes/profiles/ 目录不存在,
    # 探测 fallback 到 <hermes.exe>/../ 找 profiles/ 也没有 → hermes 子进程加载
    # profile 时找不到 SOUL.md / config.yaml / skills/ → 输出"skill 未在系统中安装"。
    # (user 反馈 v1.1.5 三个智能体文件夹都是空的,根因在此)
    src_profiles = SOURCE / 'resources' / 'hermes' / 'profiles'
    dst_profiles = DIST / 'resources' / 'hermes' / 'profiles'
    if src_profiles.is_dir():
        if dst_profiles.exists():
            shutil.rmtree(dst_profiles, ignore_errors=True)
        shutil.copytree(src_profiles, dst_profiles)
        # 算一下拷了多少个 profile 文件
        n_profiles = sum(1 for p in dst_profiles.iterdir() if p.is_dir())
        print(f'  ✓ 拷 {src_profiles} → {dst_profiles} ({n_profiles} 个 profile: '
              f'{", ".join(p.name for p in dst_profiles.iterdir() if p.is_dir())})')
    else:
        print(f'  ⚠ 找不到 {src_profiles},跳过 hermes profiles 嵌入')

    step('4) 准备 config\ / data\ / outputs\ / logs\ 空目录(首次安装)')
    for sub in ['config', 'data', 'outputs', 'logs']:
        d = DIST / sub
        d.mkdir(parents=True, exist_ok=True)
        (d / '.gitkeep').write_text('# 漫剧助手X-2 首次启动会自动初始化\n')
    # 拷 hermes_api.json 模板
    template = SOURCE / 'config' / 'hermes_api.json'
    if template.exists():
        shutil.copy2(template, DIST / 'config' / 'hermes_api.json')
        print(f'  ✓ 拷 {template} → config\\hermes_api.json')

    step('5) 写 release/version.txt')
    RELEASE.mkdir(parents=True, exist_ok=True)
    (RELEASE / 'version.txt').write_text('v1.0.0\n', encoding='utf-8')

    step('6) 调 Inno Setup 编译 .iss')
    iscc = _find_iscc()
    if not iscc:
        print('  ⚠ 找不到 Inno Setup 编译器(ISCC.exe)')
        print('  请先装 Inno Setup 6: https://jrsoftware.org/isdl.php')
        print('  装到任意位置,build_x2.py 会自动扫描以下候选路径:')
        for p in _ISCC_CANDIDATES:
            print(f'    - {p}')
        print('  手动跑完 ISCC 编译后,继续 step 7')
    else:
        print(f'  找到 ISCC: {iscc}')
        run([iscc, str(INSTALLER / '漫剧助手X-2.iss')], cwd=INSTALLER)
        # 算 md5 + sha256
        import hashlib
        # v1.1.4:glob pattern 兼容老 "漫剧助手X-2_v*_Setup.exe" + 新
        # "X-2_v*_Setup.exe"(v1.1.3.1 起 .iss 改纯 ASCII 文件名)
        setup_exes = sorted(
            set(RELEASE.glob('漫剧助手X-2_v*_Setup.exe')) | set(RELEASE.glob('X-2_v*_Setup.exe'))
        )
        for f in setup_exes:
            data = f.read_bytes()
            md5 = hashlib.md5(data).hexdigest()
            sha256 = hashlib.sha256(data).hexdigest()
            (RELEASE / f.name).with_suffix('.exe.md5').write_text(md5)
            (RELEASE / f.name).with_suffix('.exe.sha256').write_text(sha256)
            print(f'  ✓ {f.name}')
            print(f'    md5    = {md5}')
            print(f'    sha256 = {sha256}')

    step('7) 写 update.json(给自更新检查用)')
    import datetime
    import json
    import re
    # v1.1.4:兼容老 "漫剧助手X-2_v*_Setup.exe" + 新 "X-2_v*_Setup.exe"
    setup_exes = sorted(
        set(RELEASE.glob('漫剧助手X-2_v*_Setup.exe')) | set(RELEASE.glob('X-2_v*_Setup.exe'))
    )
    # v1.1.4:按 semver 排序(字符串排序"X" < "漫" 错位 → 取错 latest)
    def _ver_key(p: Path) -> Tuple[int, ...]:
        m = re.search(r'_v(\d+(?:\.\d+){0,3})_Setup', p.name)
        if m:
            return tuple(int(x) for x in m.group(1).split('.'))
        return (0,)
    setup_files = sorted(setup_exes, key=_ver_key)
    if setup_files:
        latest = setup_files[-1]
        m = re.search(r'_v(.+?)_Setup', latest.name)
        ver = m.group(1) if m else '1.0.0'
        data = latest.read_bytes()
        md5 = hashlib.md5(data).hexdigest()
        sha256 = hashlib.sha256(data).hexdigest()
        update = {
            'version': ver,
            # v1.1.3.1:tag 必带 v 前缀(实际 GitHub tag 是 "v1.1.3"),
            # 否则 .../download/1.1.3/... 404
            'url': f'https://github.com/xyq900319xyq/manju-x2/releases/download/v{ver}/{urllib.parse.quote(latest.name, safe="")}',
            'md5': md5,
            'sha256': sha256,
            'size': latest.stat().st_size,
            # v1.1.3:改纯英文 URL(原 docs/更新日志.md 含中文,Qt 弹
            # QMessageBox 时 native MessageBox 用 ascii 编码会爆)。
            'changelog_url': 'https://github.com/xyq900319xyq/manju-x2/releases',
            'release_date': datetime.date.today().isoformat(),
        }
        (RELEASE / 'update.json').write_text(json.dumps(update, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'  ✓ update.json: {ver} md5={md5} sha256={sha256[:16]}...')

    print('\n=== 完成 ===')
    print(f'manju EXE: {DIST}')
    print(f'release:   {RELEASE}')


if __name__ == '__main__':
    main()
