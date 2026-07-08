# Multi-Agent API Switching (v2)

## Architecture
- `hermes_api.json` in USER_DATA stores multiple configs + active ID
- `_inject_api_to_profile()` reads active config and writes to all 3 profile config.yaml files
- Switching is instant: next agent call uses new API

## Key Files
- `server.py` line ~3128: `PRESET_CONFIGS`, `_load_agent_configs()`, `_save_agent_configs()`, `_ensure_presets()`, `_inject_active_to_profiles()`
- `server.py` line ~414: `_inject_api_to_profile()` — FIXED: uses new multi-config format, always `encoding='utf-8'`
- Frontend: `/api/settings/agent-configs` GET/POST/DELETE, `/api/settings/agent-configs/activate` POST

## Pitfalls
1. **GBK encoding on Chinese Windows**: All file opens MUST specify `encoding='utf-8'`. Default GBK fails on API keys with special chars.
2. **Multi-config format**: `hermes_api.json` has `{"configs":[...],"active":"id"}`, NOT flat `{"api_key":"..."}`. Old code reads wrong keys.
3. **Custom provider injection**: When provider is "custom", write to `d["providers"]["<name>"]` (not "custom") and set `m["provider"]="custom"`.
4. **Active config must have key**: Empty API key → injection succeeds but agent calls fail silently. Validate before switching.
5. **Profile path**: `_inject_active_to_profiles()` uses `os.path.join(home, "profiles", prof)` where home=`HERMES_HOME`. Must match `_find_profiles_base()` structure.
6. **Windows .exe extension**: `os.path.exists()` on Windows does NOT auto-append `.exe`. `hermes` binary is actually `hermes.exe` — must use exact filename. In PyInstaller EXEs, `sys.executable` points to the EXE itself, so `os.path.dirname(os.path.dirname(sys.executable))` navigates to find sibling binaries.
7. **DB path fallback**: `_data_dir` should fall back to `os.path.dirname(os.path.abspath(__file__))` if `USER_DATA` env var is empty or directory doesn't exist. Chinese Windows paths in env vars can get corrupted. Always verify DB exists at the computed path.
8. **All file I/O must specify encoding='utf-8'**: Windows default encoding is GBK. Any file read/write (especially YAML config injection) will fail with `'gbk' codec can't decode` if encoding is not specified. This is a silent data-corruption bug.
9. **Original script (剧本原文) is only in DB `script` column**: The script content is submitted via the UI POST endpoint, never pasted in chat. If the DB gets corrupted or the column is cleared, there is no backup in git, session logs, or attachments. The `storyboard` and `prompt` columns contain the converted content but NOT the original script text.
