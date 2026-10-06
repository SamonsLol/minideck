# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Fuente de estado: la app en primer plano del Mac.

El cliente usa esto para el "perfil por app": cambia de página según la
aplicación activa (VS Code → Desarrollo, Vivaldi → Web, etc.).
El mapa app→página vive en deck.json bajo "profiles".
"""
import subprocess
import sys

from . import action

if sys.platform != "darwin":
    raise ImportError("active_app solo aplica a macOS")


def _frontmost():
    # 1) NSWorkspace (rápido, sin subprocess ni permisos extra)
    try:
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is not None:
            name = app.localizedName()
            if name:
                return str(name)
    except Exception:  # noqa: BLE001
        pass
    # 2) osascript de reserva
    try:
        out = subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to get name of first '
             'application process whose frontmost is true'],
            capture_output=True, text=True, timeout=3)
        return out.stdout.strip() or None
    except Exception:  # noqa: BLE001
        return None


@action("active_app_get", state=True)
def active_app_get(params: dict):
    """Nombre de la app en primer plano. params: {}"""
    return {"state": {"activeApp": _frontmost() or ""}}
