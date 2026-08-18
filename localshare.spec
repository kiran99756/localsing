# localshare.spec
# Build with:  pyinstaller localshare.spec
#
# Produces a single-file dist/LocalShare.exe (on Windows) that bundles
# templates/ and static/ as read-only resources (see config.resource_dir())
# and writes its database, uploads, and security.json next to the .exe
# (see config._app_dir()) so nothing is lost between runs.

# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hidden_imports = (
    collect_submodules("uvicorn")
    + collect_submodules("zeroconf")
    + collect_submodules("fastapi")
)

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("templates", "templates"),
        ("static", "static"),
    ],
    hiddenimports=hidden_imports,
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
    name="LocalShare",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,   # keep a console window - it prints the password + URLs on startup
    icon=None,      # put an .ico path here if you want a custom icon
    onefile=True,
)
