# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
# PyInstaller spec para MiniDeck en Windows (.exe con icono de bandeja).
# Construir desde la RAÍZ del proyecto:
#   pyinstaller build/minideck-win.spec --noconfirm
# Resultado: dist/MiniDeck/MiniDeck.exe (carpeta portable; el CI la comprime en .zip)
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.getcwd())
SERVER = os.path.join(ROOT, "server")
sys.path.insert(0, SERVER)

# OJO: de config/ solo el deck por defecto; nunca deck.json, auth_token ni discord.json.
datas = [
    (os.path.join(ROOT, "frontend"), "frontend"),
    (os.path.join(SERVER, "plugins"), "plugins"),
    (os.path.join(SERVER, "config", "deck.default.windows.json"), "config"),
    (os.path.join(ROOT, "assets", "minideck.ico"), "assets"),
]

hiddenimports = (
    collect_submodules("actions")
    + collect_submodules("uvicorn")
    + collect_submodules("websockets")
    + collect_submodules("pystray")
    + ["main", "auth", "paths", "version",
       "psutil", "segno", "pyautogui", "keyboard", "pycaw", "pycaw.pycaw", "comtypes",
       "comtypes.stream", "PIL.Image"]
)
try:  # opcional: Now Playing (no hay ruedas para todas las versiones de Python)
    import winsdk  # noqa: F401
    hiddenimports += collect_submodules("winsdk")
except ImportError:
    pass

a = Analysis(
    [os.path.join(SERVER, "app_tray.py")],
    pathex=[SERVER],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "rumps", "objc", "AppKit", "Foundation", "Quartz"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MiniDeck",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=bool(os.environ.get("MINIDECK_CONSOLE")),  # MINIDECK_CONSOLE=1 → depurar
    icon=os.path.join(ROOT, "assets", "minideck.ico"),
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="MiniDeck")
