# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — 小说写作助手 (macOS .app)

注意：PyInstaller 不支持跨平台打包，本 spec 需在 macOS 上运行
（通过 GitHub Actions macos runner 构建 Apple Silicon 版）。
icon.icns 由构建脚本在打包前生成，无需提交到仓库。

用法：
  uv run pyinstaller novel-writer-mac.spec --noconfirm    # 生成 dist/novel-writer.app
"""

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
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
    [],
    exclude_binaries=True,
    name='novel-writer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='novel-writer',
)

# 打包为 macOS .app 应用包（PyInstaller 会自动做 ad-hoc 签名，无需开发者账号）
app = BUNDLE(
    coll,
    name='novel-writer.app',
    icon='icon.icns',
    bundle_identifier='com.novelwriter.app',
    info_plist={
        'CFBundleName': '马良',
        'CFBundleDisplayName': '马良',
        'CFBundleVersion': '0.0.1',
        'CFBundleShortVersionString': '0.0.1',
        'LSMinimumSystemVersion': '26.0',
        'NSHighResolutionCapable': True,
    },
)
