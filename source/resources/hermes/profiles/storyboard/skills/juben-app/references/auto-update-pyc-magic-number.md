# Auto-Update pyc Magic Number Bug

## The Bug

The launcher's auto-update code downloads `server.py` from the public repo and compiles it locally. The compilation used `py_compile.compile()` which runs in the **launcher's Python interpreter**.

**Problem**: The launcher is a PyInstaller EXE built with Python 3.12 (the system Python that has PyInstaller). But the bundled runtime is Python 3.11. When Python 3.12 compiles a `.pyc`, it writes a Python 3.12 magic number. The embedded Python 3.11 can't read it, and crashes:

```
RuntimeError: Bad magic number in .pyc file
```

## The Fix

Use `subprocess.run()` to call the **bundled runtime Python** to compile:

```python
# WRONG — uses launcher's Python (3.12):
import py_compile
py_compile.compile(local, local + "c")

# CORRECT — uses bundled Python (3.11):
import subprocess as sp
pyc = local + "c"
if os.path.exists(pyc):
    os.remove(pyc)
sp.run([PY, "-m", "py_compile", local], check=True, timeout=30)
# Move __pycache__/*.pyc to the expected location
import glob
for compiled in glob.glob(os.path.join(os.path.dirname(local), "__pycache__", "*.pyc")):
    shutil.move(compiled, local + "c")
    break
```

Where `PY = os.path.join(SD, "runtime", "python.exe")`.

## Prevention

1. Always delete old `.pyc` before compiling
2. Use `sp.run()` with `check=True` to catch compile errors
3. Log update failures to `update.log` instead of silent `pass`
4. Show server log tail on startup failure to aid debugging
