# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 小说写作助手 单文件版（分发简单，启动稍慢）"""

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
        'flask',
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
    console=True,
    icon='icon.ico',
    version='version_info.txt',
)
