# Episode Creation & Storyboard Generation Debug Trail

## Error Chain (in order of discovery)

1. **"确认剧本" button changes to "生成分镜" but "剧集不存在"**
   - Symptom: Episode appears created (button changed), but generate says episode not found
   - Root cause: `add_episode` function used undefined variable `mode` (line 860)
   - Fix: Changed to literal `"storyboard"` string

2. **Episode created but not in database**
   - Root cause: No `conn.commit()` after INSERT — WAL mode auto-commit not reliable
   - Fix: Added explicit `conn.commit()` after episode INSERT

3. **Generate "剧集不存在" even after episode created**
   - Root cause: Database file in `app/projects.db` (old location), not `%APPDATA%\Juben\projects.db`
   - DB_PATH used `os.environ.get("USER_DATA", ...)` but USER_DATA wasn't set
   - Fix: Added hardcoded AppData fallback: `os.path.join(os.environ.get("APPDATA", ...), "Juben")`

4. **"Unexpected token '<'" in browser**
   - Symptom: Server returns HTML error page instead of JSON
   - This is Flask returning a 500 error page — means server crashed during request

5. **Hermes "Profile 'storyboard' does not exist"**
   - Root cause: Profiles encrypted in `profiles.dat`, decrypted to `%TEMP%\MSI<random>\`
   - `HERMES_HOME` pointed to `~/.hermes/profiles/` which doesn't have the profile
   - Fix: Server now auto-discovers decrypted profiles via `_find_profiles_base()`

6. **API config not injected into profile**
   - Root cause: Launcher injects API, but old EXE doesn't set env vars properly
   - Fix: Server-side injection via `_inject_api_to_profile()` — called before EVERY Hermes invocation

7. **API save endpoint blocks on test failure**
   - Root cause: `POST /api/settings/hermes-config` tested API BEFORE saving
   - Fix: Save first, test second — return `{"ok":True,"saved":True}` even if test fails

## Testing Approach

**Use Flask test client for E2E tests** — avoids port conflicts, heartbeat kills, and socket exhaustion:
```python
sys.path.insert(0, r"D:\剧本分镜助手_打包\app")
import importlib.util
spec = importlib.util.spec_from_file_location("server", "server.pyc")
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)
with server.app.test_client() as c:
    r = c.post("/api/settings/hermes-config", json={...})
    # ... full flow test
```

## Common Code Generation Bugs

When using `execute_code` or `write_file` to generate launcher.py:
- `{repr(secret)}` → written as literal text, not evaluated
- `{{ }}` in f-strings → written as `{{ }}` not `{ }`
- Token strings → censored to `...`

**Post-write fix checklist:**
```bash
grep -n '{{' launcher.py           # Should return empty
grep -n '{repr(' launcher.py       # Should return empty  
python -c "import py_compile; py_compile.compile('launcher.py', doraise=True)"
```
