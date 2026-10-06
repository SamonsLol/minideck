# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Atajos de teclado y escritura de texto en macOS.

En Windows esto lo hace keys.py (módulo `keyboard`, no instalable en Mac).
Aquí usamos pyautogui para las combinaciones y osascript para escribir texto
(maneja bien acentos y unicode). Requiere permiso de Accesibilidad.
"""
import subprocess
import sys

from . import action

if sys.platform != "darwin":
    raise ImportError("keys_mac solo aplica a macOS")

# Alias de modificadores/teclas → nombres que entiende pyautogui.
_MOD = {
    "win": "command", "windows": "command", "cmd": "command", "command": "command",
    "super": "command", "meta": "command",
    "ctrl": "ctrl", "control": "ctrl",
    "alt": "option", "option": "option", "opt": "option",
    "shift": "shift", "fn": "fn",
}
_KEY = {
    "esc": "escape", "del": "delete", "return": "enter", "intro": "enter",
    "pgup": "pageup", "pgdn": "pagedown", "ins": "insert", "espacio": "space",
    "arriba": "up", "abajo": "down", "izquierda": "left", "derecha": "right",
}


def _tok(t: str) -> str:
    t = t.strip().lower()
    return _MOD.get(t, _KEY.get(t, t))


@action("hotkey")
def hotkey(params: dict):
    """Envía una combinación de teclas. params: {"keys": "cmd+shift+4"}
    Alias: win/cmd→⌘, alt/option→⌥, ctrl, shift. También teclas sueltas."""
    keys = params.get("keys")
    if not keys:
        raise ValueError("Falta el parámetro 'keys'")
    parts = [_tok(k) for k in keys.split("+") if k.strip()]
    import pyautogui
    pyautogui.hotkey(*parts)
    return {"message": f"Atajo: {keys}"}


@action("type_text")
def type_text(params: dict):
    """Escribe texto como si lo teclearas. params: {"text": "hola mundo"}"""
    text = params.get("text", "")
    if not text:
        raise ValueError("Falta el parámetro 'text'")
    safe = text.replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(
        ["osascript", "-e",
         f'tell application "System Events" to keystroke "{safe}"'],
        check=False)
    return {"message": f"Texto escrito ({len(text)} caracteres)"}
