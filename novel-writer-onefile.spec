# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 小说写作助手 单文件版（分发简单，启动稍慢）"""

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('plugins', 'plugins'),
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
        'core.config',
        'core.database',
        'core.httpd',
        'services.script_service',
        'services.floating_song_service',
        'services.score_service',
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
    a.binaries,
    a.datas,
    [],
    name='novel-writer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    icon='icon.ico',
    version='version_info.txt',
)
