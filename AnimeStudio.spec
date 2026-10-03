# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification file for Anime Studio v3.

Builds a standalone Windows executable.
Usage:
    pyinstaller AnimeStudio.spec
"""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
repo_root = Path.cwd().resolve()

# 1. Collect all dynamic submodules across the architecture
hidden_modules = (
    collect_submodules("src")
    + collect_submodules("qasync")
    + collect_submodules("qdarktheme")
    + collect_submodules("fontTools")
    + collect_submodules("structlog")
    + collect_submodules("pydantic")
    + collect_submodules("pydantic_core")
    + collect_submodules("httpx")
)

# 2. Collect static data files (dark theme QSS/SVG, fontTools tables)
datas = []
datas += collect_data_files("qdarktheme")
datas += collect_data_files("fontTools")

# 3. Binaries / hooks
binaries = []

# 4. Exclude heavy, unused packages to keep binary lean and clean
excludes = [
    "tkinter",
    "matplotlib",
    "scipy",
    "numpy",
    "pandas",
    "IPython",
    "notebook",
    "pytest",
    "_pytest",
    "unittest.test",
]

a = Analysis(
    ["main.py"],
    pathex=[str(repo_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_modules,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Check if console mode is requested via environment variable for debugging
debug_console = os.environ.get("ANIME_STUDIO_DEBUG_CONSOLE", "0") == "1"

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AnimeStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=debug_console,
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
    upx=True,
    upx_exclude=[],
    name="AnimeStudio",
)
