# -*- mode: python ; coding: utf-8 -*-
#
# Build with build-desktop.bat (it runs collectstatic and creates the seed db
# before calling PyInstaller). Do NOT bundle the live db.sqlite3 - only the
# clean db.seed.sqlite3 goes into the EXE.

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ('templates', 'templates'),
    ('static', 'static'),
    ('staticfiles', 'staticfiles'),      # produced by collectstatic (WhiteNoise serves this)
    ('db.seed.sqlite3', '.'),            # clean seed schema, copied on first run
]
datas += collect_data_files('django')    # admin templates + admin static files
datas += collect_data_files('tzdata')    # zoneinfo for Asia/Kolkata (USE_TZ)
datas += collect_data_files('reportlab') # PDF fonts/encodings

hiddenimports = [
    'whitenoise',
    'whitenoise.middleware',
    'whitenoise.storage',
    'waitress',
    'dotenv',
    'tzdata',
]
# pywebview Windows backends (static names only - collect_submodules('webview')
# imports the whole package at build time and can hang loading .NET).
hiddenimports += [
    'webview.platforms.winforms',
    'webview.platforms.edgechromium',
]
hiddenimports += collect_submodules('core')      # includes core.migrations.*
hiddenimports += collect_submodules('schoolsoft')
hiddenimports += collect_submodules('django')
hiddenimports += collect_submodules('reportlab')

a = Analysis(
    ['desktop.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # server/online-only packages - keep the desktop EXE lean
        'psycopg2',
        'pyodbc',
        'gunicorn',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='THPSIC SchoolSoft',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,   # UPX-packed DLLs trigger antivirus and can corrupt runtimes
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    icon='static/core/schoolsoft.ico',
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='THPSIC SchoolSoft',
)
