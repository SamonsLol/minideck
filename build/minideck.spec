# -*- mode: python ; coding: utf-8 -*-
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
# PyInstaller spec para MiniDeck (.app de barra de menú).
# Construir desde la RAÍZ del proyecto:
#   ./buildenv/bin/pyinstaller build/minideck.spec --noconfirm
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.getcwd())
SERVER = os.path.join(ROOT, "server")
sys.path.insert(0, SERVER)   # para que collect_submodules("actions") lo encuentre

# OJO: de config/ solo se empaqueta el deck por defecto. Nunca deck.json,
# auth_token ni discord.json (son datos personales / secretos).
datas = [
    (os.path.join(ROOT, "frontend"), "frontend"),
    (os.path.join(SERVER, "plugins"), "plugins"),
    (os.path.join(SERVER, "config", "deck.default.macos.json"), "config"),
    (os.path.join(ROOT, "assets", "menubar-template.png"), "assets"),
    (os.path.join(ROOT, "assets", "menubar-template@2x.png"), "assets"),
]

# Los imports pyobjc/pyautogui son perezosos y las acciones/plugins se cargan
# dinámicamente: hay que declararlos a mano.
hiddenimports = (
    collect_submodules("actions")
    + collect_submodules("uvicorn")
    # los plugins se cargan como datos: PyInstaller no ve sus imports (OBS → websockets)
    + collect_submodules("websockets")
    + [
        "main", "auth", "paths", "version",
        "objc", "Foundation", "AppKit", "Quartz", "Vision",
        "CoreFoundation", "ApplicationServices", "libdispatch",
        "psutil", "segno", "rumps", "pyautogui",
    ]
)

_icon = os.path.join(ROOT, "assets", "minideck.icns")
icon = _icon if os.path.exists(_icon) else None

a = Analysis(
    [os.path.join(SERVER, "app_menubar.py")],
    pathex=[SERVER],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["keyboard", "pycaw", "comtypes", "winsdk", "tkinter"],
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
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="MiniDeck")

app = BUNDLE(
    coll,
    name="MiniDeck.app",
    icon=icon,
    bundle_identifier="com.samons.minideck",
    info_plist={
        "LSUIElement": True,               # sin icono en el Dock (barra de menú)
        "CFBundleName": "MiniDeck",
        "CFBundleDisplayName": "MiniDeck",
        "CFBundleShortVersionString": "1.3.0",
        "NSHighResolutionCapable": True,
    },
)
