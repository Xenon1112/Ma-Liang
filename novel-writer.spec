# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 小说写作助手 (Windows onedir/onefile)

用法：
  uv run pyinstaller novel-writer.spec --noconfirm            # 单目录版
  uv run pyinstaller novel-writer-onefile.spec --noconfirm    # 单文件版
"""

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('icon.ico', '.'),
    ],
    hiddenimports=[
        'webview',
        'webview.platforms.winforms',
        'webview.platforms.win32',
        'webview.platforms.edgechromium',
        'clr',
        'clr_loader',
        'docx',
        'sqlite3',
        'services.project_service',
        'services.chapter_service',
        'services.draft_service',
        'services.outline_service',
        'services.character_service',
        'services.world_setting_service',
        'services.inspiration_service',
        'services.export_service',
        'services.backup_service',
        'services.recycle_service',
        'services.search_service',
        'services.config_service',
        'services.script_service',
        'services.json_transfer_service',
        'services.floating_song_service',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter', 'matplotlib', 'numpy', 'pandas', 'PIL',
        'pytest', 'unittest', 'pydoc', 'doctest',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='novel-writer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='icon.ico',
    version='version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='novel-writer',
)
