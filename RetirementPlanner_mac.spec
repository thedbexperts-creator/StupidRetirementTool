# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Retirement Planner — Mac .app bundle
# Run via:  bash build_mac_app.sh
#   (or directly: pyinstaller RetirementPlanner_mac.spec)

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[('index.html', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='RetirementPlanner',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,          # No terminal window — cleaner on Mac
    disable_windowed_traceback=False,
    argv_emulation=False,   # Must be False for onefile mode
    target_arch=None,       # None = current arch; set 'universal2' for M1+Intel
    codesign_identity=None,
    entitlements_file=None,
    onefile=True,
)

# Wrap in a .app bundle (Mac only)
app = BUNDLE(
    exe,
    name='RetirementPlanner.app',
    icon=None,              # Add a .icns file path here if you have one
    bundle_identifier='com.retirementplanner.app',
    info_plist={
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '1.0',
        'CFBundleName': 'Retirement Planner',
    },
)
