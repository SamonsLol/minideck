"""Atajos de teclado y escritura de texto. Requiere: pip install keyboard"""
import sys

if sys.platform != "win32":
    raise ImportError("keys solo aplica a Windows")

import keyboard

from . import action


@action("hotkey")
def hotkey(params: dict):
    """Envía una combinación de teclas.
    params: {"keys": "ctrl+shift+m"}
    Referencia de nombres: https://github.com/boppreh/keyboard
    """
    keys = params.get("keys")
    if not keys:
        raise ValueError("Falta el parámetro 'keys'")
    keyboard.send(keys)
    return {"message": f"Atajo: {keys}"}


@action("type_text")
def type_text(params: dict):
    """Escribe texto como si lo teclearas.
    params: {"text": "hola mundo", "interval": 0.01}
    """
    text = params.get("text", "")
    if not text:
        raise ValueError("Falta el parámetro 'text'")
    keyboard.write(text, delay=float(params.get("interval", 0)))
    return {"message": f"Texto escrito ({len(text)} caracteres)"}
