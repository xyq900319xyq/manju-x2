# Embedded Python Setup for 剧本分镜助手

## Problem
The Python `python-3.11.9-embed-amd64.zip` from python.org is a minimal distribution that lacks:
- pip (no module named pip)
- tkinter (used by activation dialog)
- Full standard library
- Proper site-packages support

## Complete Setup Recipe

### 1. Extract and configure
```bash
unzip python-3.11.9-embed-amd64.zip -d runtime/
```

### 2. Edit `runtime/python311._pth`
Change:
```
python311.zip
.
# import site
```
To:
```
python311.zip
.
import site
Lib
```

### 3. Install pip
```bash
curl -sL https://bootstrap.pypa.io/get-pip.py -o runtime/get-pip.py
runtime/python.exe runtime/get-pip.py
```

### 4. Install dependencies
```bash
runtime/python.exe -m pip install flask waitress pyyaml requests
```

### 5. Copy hermes_cli
```bash
cp -r hermes/hermes_cli/ runtime/Lib/site-packages/hermes_cli/
```

### 6. Verify
```bash
runtime/python.exe -c "import flask,waitress,yaml,requests,hermes_cli;print('OK')"
```

## Tkinter Alternative
The embedded Python CANNOT use tkinter (Tcl/Tk DLLs are missing even after copying from full Python). Use VBScript InputBox instead:
```python
import subprocess, tempfile
vbs = tempfile.mktemp(suffix=".vbs")
with open(vbs, "w") as f:
    f.write('result = InputBox("请输入激活码：","剧本分镜助手")\nWScript.Echo result\n')
r = subprocess.run(["cscript","//Nologo",vbs], capture_output=True, text=True, timeout=30)
code = r.stdout.strip()
```

## PyInstaller Build
PyInstaller must be run from a FULL Python installation (not the embedded one). Use Python 3.12 from `C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe`:
```bash
"$PY312" -m PyInstaller --onefile --noconsole --name "剧本分镜助手" launcher.py
```
