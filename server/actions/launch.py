# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Lanzar aplicaciones, ejecutar comandos y abrir sitios web."""
import os
import subprocess
import sys
import webbrowser

from . import action


@action("launch", schema={"path": {"type": "str"}, "app": {"type": "str"}, "args": {"type": "list"}, "$oneOf": [["path", "app"]]})
def launch(params: dict):
    """Abre una aplicación o archivo con su programa asociado.
    params: {"path": "C:/Program Files/.../app.exe", "args": ["--flag"]}
    También acepta rutas de archivos (.mp3, .docx...) o carpetas, o
    {"app": "chrome"} con un nombre registrado en el sistema (como Win+R).
    """
    path = params.get("path")
    app = params.get("app")
    if not path and app:
        # Decks compartidos con macOS usan "app": se intenta por nombre.
        if sys.platform.startswith("win"):
            subprocess.Popen(["cmd", "/c", "start", "", app],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        else:
            subprocess.Popen([app])
        return {"message": f"Abriendo: {app}"}
    if not path:
        raise ValueError("Falta el parámetro 'path' (o 'app')")
    args = params.get("args") or []
    if args:
        subprocess.Popen([path, *args])
    elif hasattr(os, "startfile"):
        os.startfile(path)  # respeta asociaciones de Windows
    else:
        subprocess.Popen(["xdg-open", os.path.expanduser(path)])  # Linux
    return {"message": f"Abriendo: {os.path.basename(path)}"}


@action("command", schema={"cmd": {"type": "str", "required": True}, "shell": {"type": "str", "choices": ["cmd", "powershell"]}})
def command(params: dict):
    """Ejecuta un comando de consola (cmd o PowerShell).
    params: {"cmd": "shutdown /s /t 60", "shell": "powershell"}  # shell opcional
    """
    cmd = params.get("cmd")
    if not cmd:
        raise ValueError("Falta el parámetro 'cmd'")
    shell = params.get("shell", "cmd")
    if not sys.platform.startswith("win"):
        full = ["sh", "-c", cmd]                     # Linux (macOS: launch_mac)
    elif shell == "powershell":
        full = ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", cmd]
    else:
        full = ["cmd", "/c", cmd]
    subprocess.Popen(full, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return {"message": "Comando ejecutado"}


@action("website", schema={"url": {"type": "str", "required": True}})
def website(params: dict):
    """Abre una URL en el navegador por defecto.
    params: {"url": "https://youtube.com"}
    """
    url = params.get("url")
    if not url:
        raise ValueError("Falta el parámetro 'url'")
    webbrowser.open(url)
    return {"message": f"Abriendo: {url}"}
