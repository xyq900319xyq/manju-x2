# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('..\\resources', 'resources')],
    hiddenimports=['core', 'ui', 'core.config', 'core.database', 'core.generators', 'core.hermes', 'core.image_api', 'core.prompts', 'core.asset_parser', 'core.task_queue', 'core.dreamina', 'core.dreamina_models', 'core.image_models', 'core.video', 'core.asset_browser', 'ui.main_window', 'ui.asset_panel', 'ui.dialogs', 'ui.project_tree', 'ui.task_status', 'ui.settings_dialog', 'ui.ref_images_widget', 'ui.asset_browser_dialog', 'ui.image_preview_dialog', 'ui.log_dialog'],
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
    name='漫剧助手X-1',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='漫剧助手X-1',
)
