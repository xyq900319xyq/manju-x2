# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
import os
SRC_DIR = os.path.abspath('src')


hiddenimports = []
hiddenimports += collect_submodules('ui')
hiddenimports += collect_submodules('core')
hiddenimports += ['ui', 'core', 'ui.main_window', 'ui.asset_panel', 'ui.settings_dialog']


a = Analysis(
    ['src\\main.py'],
    pathex=[SRC_DIR],
    binaries=[],
    datas=[('resources', 'resources')],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='漫剧助手X-2',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='漫剧助手X-2',
)
