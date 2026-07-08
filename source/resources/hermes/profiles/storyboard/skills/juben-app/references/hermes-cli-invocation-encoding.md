# Hermes Agent CLI Invocation & GBK Encoding Fix

## The GBK UnicodeDecodeError Problem (CRITICAL)

On Chinese Windows, the default system encoding is GBK (cp936). When the Python subprocess reads text output from Hermes, the reader thread crashes with:
```
UnicodeDecodeError: 'gbk' codec can't decode byte 0x80 in position 586
```

This kills the reader thread, resulting in **empty stdout** from `subprocess.run()`. The frontend sees "生成超时或出错" (generation timeout or error) but the real issue is invisible.

### The Fix (3 locations in server.py)

All three `subprocess.run()` calls must use:
```python
result = subprocess.run(
    cmd,
    capture_output=True, text=True,
    encoding='utf-8', errors='replace',  # ← MANDATORY on Chinese Windows
    timeout=timeout, env=env,
    cwd=os.path.expanduser("~"),
)
```

Four locations:
- `run_hermes_agent()` — storyboard generation (~line 487)
- `extract_project_assets()` — asset extraction (~line 767)
- `run_seedance_agent()` — seedance prompt generation (~line 1238)
- Plus any other Hermes invocation

### Why It Keeps Coming Back

The **launcher auto-update** (lines 194-223) downloads `server.py` from the PUBLIC GitHub repo and compiles it, **overwriting any local fixes**. If the public repo's `server.py` doesn't have the encoding fix, every restart resets it.

**Solution**: Add version check to auto-update — only download when remote version differs from stored `.app_version`:
```python
version_file = os.path.join(UD, ".app_version")
last_version = open(version_file).read().strip() if os.path.exists(version_file) else ""
rv = urllib.urlopen(f"{PUB}/version.txt").read().decode().strip()
if rv and rv != last_version:
    # ... download and update ...
    with open(version_file, 'w') as f: f.write(rv)
```

## Hermes CLI Invocation Pattern

### The `main()` Function Quirk

Hermes CLI's `main()` function takes **zero arguments** — it reads from `sys.argv`. So you CANNOT do:
```python
main(["-p", "storyboard", "chat", "-q", "hi"])
# TypeError: main() takes 0 positional arguments but N was given
```

Instead, pass args as command-line arguments to the subprocess:
```python
HERMES_CMD = [sys.executable, "-c", "from hermes_cli.main import main;main()"]
result = subprocess.run(HERMES_CMD + ["-p", "storyboard", "chat", "-q", prompt, "--quiet"], ...)
```

### When `-p profile_name` Returns "Profile not found"

Hermes looks for `$HERMES_HOME/profiles/<name>/config.yaml`. Check:
1. Is `HERMES_HOME` set to the root containing `profiles/` (not the profile subdir)?
2. Does the extracted profiles.dat actually have a `profiles/` wrapper directory?
3. Try both structures: `profiles/storyboard/config.yaml` AND `storyboard/config.yaml`

### Unified `_run_hermes()` Helper

Extract all three identical subprocess calls into one:
```python
def _run_hermes(args, env, timeout=7200):
    """Run Hermes CLI, handles encoding and timeout consistently."""
    try:
        cmd = HERMES_CMD + list(args)
        result = subprocess.run(
            cmd,
            capture_output=True, text=True,
            encoding='utf-8', errors='replace',
            timeout=timeout, env=env,
            cwd=os.path.expanduser("~"),
        )
        combined = result.stdout + "\n" + (result.stderr or "")
        if not combined.strip() and result.returncode == 0:
            logging.warning("Hermes stdout empty — possible encoding issue")
        return combined.strip()
    except subprocess.TimeoutExpired:
        return f"Agent execution timeout (>{timeout//60} min)"
    except Exception as e:
        logging.exception("Hermes CLI execution failed")
        return f"Agent error: {e}"
```

## Dependency Checklist

### When Hermes says "No module named X"

These are the most common missing dependencies in order of discovery:
1. `hermes_constants` — config resolution
2. `utils` — atomic file operations
3. `toolsets` — get_toolset_names, resolve_toolset
4. `agent/` — agent adapters (98+ files)
5. `cli.py` — main CLI entry point
6. `tools/` — tool implementations (90+ files)
7. `httpx` — HTTP client
8. `rich` — terminal formatting
9. `python-dotenv` — env file
10. `prompt_toolkit` — interactive input
11. `concurrent-log-handler` — logging
12. `pydantic` — validation

### How to get ALL of them at once

Either:
```bash
# From the hermes-agent venv
runtime/python.exe -m pip freeze > requirements.txt
runtime/python.exe -m pip install -r requirements.txt
```

Or copy the entire venv's Lib/site-packages/ directly:
```bash
robocopy venv/Lib/site-packages runtime/Lib/site-packages /E
```

**Never** install one at a time — you will miss transitive dependencies.

## Avoid: python311._pth Corruption

Adding `Lib` to python311._pth multiple times causes:
```
python311.zip
.
import site
Lib
Lib      ← DUPLICATE causes import deadlock!
Lib      ← TRIPLICATE causes subprocess timeout
```

The ._pth file should be exactly:
```
python311.zip
.
import site
Lib
```

## When User Says "没有任何变化" (Nothing Changed)

This means the fix you think you applied IS NOT reaching the user. Check in order:
1. **Old EXE**: PyInstaller EXE cannot auto-update. User MUST re-extract zip.
2. **Old cached files**: Browser cache, old `app/` files not overwritten.
3. **Auto-update overwrote fix**: Launcher downloads old server.py from public repo.
4. **Fix not in compiled pyc**: Verify with `marshal.load` — check co_consts for fix strings.
5. **Database mismatch**: Old DB at wrong path (app/ vs AppData).
