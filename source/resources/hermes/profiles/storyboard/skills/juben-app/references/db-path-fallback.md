# DB Path Fallback (2026-06-23)

## Problem
`_data_dir` relied on `USER_DATA` env var. On Chinese Windows, env vars with Chinese characters can get corrupted or lost, causing the server to fall back to `%APPDATA%/Juben/` instead of the project directory. This resulted in empty data (DB existed but was empty).

## Fix
```python
_data_dir = os.environ.get("USER_DATA")
if not _data_dir or not os.path.isdir(_data_dir):
    _data_dir = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(_data_dir, "projects.db")
```

Also copy `hermes_api.json` to the same directory.

## Lesson
Never rely on env vars with Chinese paths for critical file resolution. Always fall back to `__file__` directory.