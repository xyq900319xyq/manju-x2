"""强制杀漫剧助手X-1.exe 进程 + 重打包。"""
import os
import shutil
import subprocess
import sys
import time
import pathlib

ROOT = pathlib.Path(r'D:\漫剧助手')
DIST = ROOT / 'dist' / '漫剧助手X-1'

# 1. 杀所有漫剧助手X-1.exe 进程
print('--- 杀进程 ---')
out = subprocess.check_output(
    ['tasklist', '/FI', 'IMAGENAME eq 漫剧助手X-1.exe', '/FO', 'CSV'],
    text=True,
)
print(f'tasklist: {out.strip()}')
pids = []
for line in out.strip().splitlines()[1:]:
    parts = line.strip().strip('"').split('","')
    if parts and parts[1].isdigit():
        pids.append(int(parts[1]))
if pids:
    for pid in pids:
        try:
            subprocess.check_call(['taskkill', '/F', '/PID', str(pid)])
            print(f'killed PID {pid}')
        except subprocess.CalledProcessError as e:
            print(f'taskkill PID {pid} failed: {e}')
else:
    print('no process to kill')

# 2. 等 2 秒让文件系统释放
time.sleep(2)

# 3. 删 dist
print()
print('--- 清 dist ---')
if DIST.exists():
    try:
        shutil.rmtree(DIST, ignore_errors=False)
        print(f'removed {DIST}')
    except Exception as e:
        # 强杀后再 retry 一次
        print(f'remove failed ({e}), retry after more sleep')
        time.sleep(3)
        try:
            shutil.rmtree(DIST, ignore_errors=False)
            print(f'removed (retry) {DIST}')
        except Exception as e2:
            print(f'remove retry failed: {e2}')
            sys.exit(2)
else:
    print('not exists')

# 4. 重 build (--clean 强制重编译,不用缓存)
print()
print('--- 重打包 (--clean 强制) ---')
# PyInstaller 直接用 spec（spec 是 v0.7.8.3 修复过的）
spec = ROOT / '漫剧助手X-1.spec'
import os as _os
_os.chdir(str(ROOT))
result = subprocess.run(
    [sys.executable, '-m', 'PyInstaller', '--clean', '--noconfirm', str(spec)],
    capture_output=True, text=True, timeout=600,
)
print(f'rc={result.returncode}')
lines = (result.stdout + result.stderr).splitlines()
print('--- last 15 lines ---')
for line in lines[-15:]:
    print(line)

# 5. 跑 fix_package.py 的 step2/step3（base_library + DLLs）但跳过 step1（不重跑 pyinstaller）
print()
print('--- fix_package.py --skip-pyinstaller ---')
result2 = subprocess.run(
    [sys.executable, str(ROOT / 'fix_package.py'), '--skip-pyinstaller'],
    capture_output=True, text=True, timeout=300,
)
print(f'rc={result2.returncode}')
lines2 = (result2.stdout + result2.stderr).splitlines()
print('--- last 15 lines ---')
for line in lines2[-15:]:
    print(line)

sys.exit(result.returncode or result2.returncode)
