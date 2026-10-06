# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Lanzar apps/archivos y ejecutar comandos en macOS.

Sustituye a launch.py (que usa APIs de Windows). 'website' se hereda de
launch.py (webbrowser funciona en todos los sistemas).
"""
import os
import shlex
import subprocess
import sys

from . import action

if sys.platform != "darwin":
    raise ImportError("launch_mac solo aplica a macOS")


@action("launch", schema={"path": {"type": "str"}, "app": {"type": "str"}, "args": {"type": "list"}, "$oneOf": [["path", "app"]]})
def launch(params: dict):
    """Abre una app, archivo o carpeta.
    params: {"app": "Visual Studio Code"}   ← por nombre de app, o
            {"path": "/Users/yo/proyecto"}  ← ruta de archivo/carpeta
            (opcional "args": ["--flag"])
    """
    app = params.get("app")
    path = params.get("path")
    args = params.get("args") or []
    if app:
        cmd = ["open", "-a", app]
        if args:
            cmd += ["--args", *args]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError(f"No se pudo abrir '{app}': {r.stderr.strip()}")
        return {"message": f"Abriendo: {app}"}
    if path:
        path = os.path.expanduser(path)
        subprocess.run(["open", path], check=False)
        return {"message": f"Abriendo: {os.path.basename(path.rstrip('/')) or path}"}
    raise ValueError("Falta 'app' o 'path'")


@action("command", schema={"cmd": {"type": "str", "required": True}, "cwd": {"type": "str"}, "terminal": {"type": "bool"}})
def command(params: dict):
    """Ejecuta un comando de terminal.
    params: {"cmd": "git pull", "cwd": "~/proyecto", "terminal": true}
      - terminal (por defecto true): lo abre en Terminal.app para ver la salida.
      - terminal false: lo ejecuta en segundo plano.
    """
    cmd = params.get("cmd")
    if not cmd:
        raise ValueError("Falta el parámetro 'cmd'")
    cwd = params.get("cwd")
    cwd = os.path.expanduser(cwd) if cwd else None

    if params.get("terminal", True):
        full = f"cd {shlex.quote(cwd)} && {cmd}" if cwd else cmd
        esc = full.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(["osascript", "-e",
                        f'tell application "Terminal" to do script "{esc}"',
                        "-e", 'tell application "Terminal" to activate'],
                       check=False)
        return {"message": "Ejecutando en Terminal"}

    subprocess.Popen(["/bin/zsh", "-lc", cmd], cwd=cwd)
    return {"message": "Comando ejecutado"}
