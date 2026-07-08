# -*- mode: python ; coding: utf-8 -*-
"""Hermes Agent PyInstaller spec (漫剧助手X-2 用户版用)。

打包 D:\\hermes\\hermes-agent\\ 成单目录 hermes_exe (含 hermes.exe + _internal/)。
简化原则:manju 只用 `hermes -p <profile> chat -q <prompt> --quiet`,不需要 web / tui / gateway。
"""
import os
import sys
from pathlib import Path

HERMES_ROOT = Path('D:/hermes/hermes-agent').resolve()

block_cipher = None

# 排除 web/tui/gateway 等 manju 用不到的大块,减包体积
EXCLUDES = [
    'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'wx', 'tkinter',
    'IPython', 'jupyter', 'notebook',
    'pywebview', 'playwright', 'selenium', 'flask', 'django', 'fastapi',
    'tornado', 'uvicorn', 'starlette',
    'flaat', 'dask', 'distributed',
    'sox', 'pydub',
    # hermes 自带的 tui/web 大块
    'tui_gateway', 'textual', 'rich_pixels',
    # 关键:cli.py 直接 import prompt_toolkit,排除后启动崩
    # 'prompt_toolkit' 必须保留
    # 关键:不要排除 stdlib 'http' / 'http.server',setuptools._vendor.jaraco.context
    # 链 urllib.request -> http;hermes_cli/auth.py 39 行 import http.server。
    # 排除后启动崩 "No module named 'http'" / "No module named 'http.server'"。
]

HIDDEN_IMPORTS = [
    # 实际包名是 hermes_cli / agent / providers,不是 hermes_agent
    'hermes_cli.main', 'hermes_cli.commands',
    'hermes_cli.fallback_config', 'hermes_cli.cli_agent_setup_mixin',
    'hermes_cli.cli_commands_mixin', 'hermes_cli.banner',
    'hermes_cli.browser_connect', 'hermes_cli.env_loader',
    'hermes_cli.callbacks',
    'hermes_constants',
    'agent', 'agent.skills', 'agent.providers', 'agent.cron',
    'agent.redactor', 'agent.curator', 'agent.lsp', 'agent.moa_loop',
    'openai', 'httpx', 'fire', 'rich', 'yaml', 'dotenv',
    'utils',
]

# 必备 data files (相对 HERMES_ROOT)
DATAS = [
    ('hermes_cli', 'hermes_cli'),
    ('agent', 'agent'),
    ('providers', 'providers'),
    ('skills/creative', 'skills/creative'),
    ('skills/apple', 'skills/apple'),
    ('skills/computer-use', 'skills/computer-use'),
    ('skills/data-science', 'skills/data-science'),
    ('skills/dogfood', 'skills/dogfood'),
    ('skills/email', 'skills/email'),
    ('skills/github', 'skills/github'),
    ('skills/media', 'skills/media'),
    ('skills/mlops', 'skills/mlops'),
    ('skills/note-taking', 'skills/note-taking'),
    ('skills/productivity', 'skills/productivity'),
    ('skills/research', 'skills/research'),
    ('skills/smart-home', 'skills/smart-home'),
    ('skills/social-media', 'skills/social-media'),
    ('skills/software-development', 'skills/software-development'),
    ('locales', 'locales'),
    ('assets', 'assets'),
    ('acp_registry', 'acp_registry'),
    ('optional-mcps', 'optional-mcps'),
    ('SOUL.md', '.'),
    ('package.json', '.'),
]

a = Analysis(
    # 关键:入口必须是 hermes_cli.main(走 `_apply_profile_override()` 处理 `-p`),
    # 不能用 cli.py(cli.py 没这层,直接 fire.Fire 看到 -p 就报 "ambiguous")。
    [str(HERMES_ROOT / 'hermes_cli' / 'main.py')],
    pathex=[str(HERMES_ROOT)],
    binaries=[],
    datas=[(str(HERMES_ROOT / s), d) for s, d in DATAS if (HERMES_ROOT / s).exists()],
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='hermes',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='hermes',
)
