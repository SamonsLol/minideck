# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Atajos de teclado y escritura de texto en Linux (X11) con pyautogui.

En Wayland la simulación de teclado está restringida por diseño: usa una
sesión X11 o la acción 'command' con herramientas como ydotool.
"""
import sys

if not sys.platform.startswith("linux"):
    raise ImportError("keys_linux solo aplica a Linux")

from . import action

_ALIAS = {
    "win": "winleft", "windows": "winleft", "super": "winleft", "meta": "winleft",
    "cmd": "winleft", "control": "ctrl", "option": "alt", "opt": "alt",
    "esc": "escape", "del": "delete", "return": "enter", "print": "printscreen",
    "print screen": "printscreen", "pgup": "pageup", "pgdn": "pagedown",
}


def _tok(t: str) -> str:
    t = t.strip().lower()
    return _ALIAS.get(t, t)


@action("hotkey", schema={"keys": {"type": "str", "required": True}})
def hotkey(params: dict):
    """Envía una combinación de teclas. params: {"keys": "ctrl+alt+t"}"""
    import pyautogui
    keys = [_tok(k) for k in params["keys"].split("+") if k.strip()]
    pyautogui.hotkey(*keys)
    return {"message": f"Atajo: {params['keys']}"}


@action("type_text", schema={"text": {"type": "str", "required": True}})
def type_text(params: dict):
    """Escribe texto como si lo teclearas. params: {"text": "hola"}"""
    import pyautogui
    pyautogui.write(params["text"], interval=float(params.get("interval", 0)))
    return {"message": f"Texto escrito ({len(params['text'])} caracteres)"}
