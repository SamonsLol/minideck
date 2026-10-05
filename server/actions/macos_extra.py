"""Acciones extra de macOS: portapapeles, Mission Control / escritorios,
vaciar papelera y ejecutar Atajos de macOS (Shortcuts.app).

Ejecutar Atajos es la vía más potente para ampliar el MiniDeck: cualquier
automatización que crees en Atajos (No molestar/Focus, HomeKit, escenas,
apps, etc.) se dispara con la acción "shortcut".
"""
import subprocess
import sys

from . import action

if sys.platform != "darwin":
    raise ImportError("macos_extra solo aplica a macOS")


def _osa(script: str):
    subprocess.run(["osascript", "-e", script], check=False)


@action("clipboard_copy")
def clipboard_copy(params: dict):
    """Copia un texto al portapapeles (firmas, correos, snippets...).
    params: {"text": "..."}"""
    text = params.get("text", "")
    subprocess.run(["pbcopy"], input=text, text=True, check=False)
    return {"message": "Copiado al portapapeles"}


@action("mission_control")
def mission_control(params: dict):
    """Abre Mission Control (Ctrl+↑). params: {}"""
    _osa('tell application "System Events" to key code 126 using control down')
    return {"message": "Mission Control"}


@action("space_change")
def space_change(params: dict):
    """Cambia de escritorio (Space). params: {"dir": "left" | "right"}"""
    d = params.get("dir", "right")
    code = 123 if d == "left" else 124  # ← / →
    _osa(f'tell application "System Events" to key code {code} using control down')
    return {"message": f"Escritorio {'anterior' if d == 'left' else 'siguiente'}"}


@action("empty_trash")
def empty_trash(params: dict):
    """Vacía la papelera. params: {}"""
    _osa('tell application "Finder" to empty the trash')
    return {"message": "Papelera vaciada"}


@action("shortcut")
def shortcut(params: dict):
    """Ejecuta un Atajo de macOS (Shortcuts.app) por su nombre.
    params: {"name": "Nombre del atajo", "input": "opcional"}"""
    name = params.get("name")
    if not name:
        raise ValueError("Falta el parámetro 'name'")
    cmd = ["shortcuts", "run", name]
    text = params.get("input")
    if text:
        subprocess.run(cmd + ["--input-path", "-"], input=text,
                       text=True, check=False)
    else:
        subprocess.run(cmd, check=False)
    return {"message": f"Atajo: {name}"}
