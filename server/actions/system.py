# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Acciones del sistema (multiplataforma): bloquear, apagar/suspender,
cerrar procesos, captura de pantalla y mostrar escritorio.

Detecta el sistema operativo y usa el mecanismo nativo de cada uno.
En macOS, las acciones basadas en teclado (bloquear, escritorio) requieren
dar permiso de Accesibilidad a la app desde la que se ejecuta Python:
Ajustes del Sistema → Privacidad y seguridad → Accesibilidad.
"""
import subprocess
import sys

from . import action

IS_MAC = sys.platform == "darwin"
IS_WIN = sys.platform.startswith("win")


def _osascript(script: str):
    """Ejecuta un AppleScript (solo macOS)."""
    subprocess.run(["osascript", "-e", script], check=False)


@action("lock")
def lock(params: dict):
    """Bloquea la sesión. params: {}"""
    if IS_MAC:
        # Atajo nativo de macOS 10.13+: Cmd+Ctrl+Q → bloquear pantalla
        _osascript('tell application "System Events" to keystroke "q" '
                   'using {command down, control down}')
        return {"message": "Mac bloqueado"}
    if IS_WIN:
        import ctypes
        ctypes.windll.user32.LockWorkStation()
        return {"message": "PC bloqueado"}
    # Linux (best effort)
    subprocess.run(["loginctl", "lock-session"], check=False)
    return {"message": "Sesión bloqueada"}


@action("power", schema={"mode": {"type": "str", "choices": ["shutdown", "restart", "sleep", "cancel"]}, "delay_s": {"type": "int", "min": 0}})
def power(params: dict):
    """Apaga, reinicia o suspende el equipo.
    params: {"mode": "shutdown" | "restart" | "sleep" | "cancel", "delay_s": 0}
    """
    mode = params.get("mode", "shutdown")
    delay = int(params.get("delay_s", 0))

    if IS_MAC:
        if mode == "sleep":
            subprocess.run(["pmset", "sleepnow"], check=False)
            return {"message": "Suspendiendo"}
        if mode == "shutdown":
            _osascript('tell application "System Events" to shut down')
            return {"message": "Apagando"}
        if mode == "restart":
            _osascript('tell application "System Events" to restart')
            return {"message": "Reiniciando"}
        if mode == "cancel":
            return {"message": "Nada que cancelar en macOS"}
        raise ValueError(f"Modo inválido: '{mode}'")

    if IS_WIN:
        if mode == "shutdown":
            subprocess.Popen(["shutdown", "/s", "/t", str(delay)])
            return {"message": f"Apagando en {delay}s"}
        if mode == "restart":
            subprocess.Popen(["shutdown", "/r", "/t", str(delay)])
            return {"message": f"Reiniciando en {delay}s"}
        if mode == "sleep":
            subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
            return {"message": "Suspendiendo"}
        if mode == "cancel":
            subprocess.Popen(["shutdown", "/a"])
            return {"message": "Apagado cancelado"}
        raise ValueError(f"Modo inválido: '{mode}'")

    # Linux (best effort)
    cmd = {"shutdown": ["systemctl", "poweroff"],
           "restart": ["systemctl", "reboot"],
           "sleep": ["systemctl", "suspend"]}.get(mode)
    if not cmd:
        raise ValueError(f"Modo inválido: '{mode}'")
    subprocess.run(cmd, check=False)
    return {"message": f"{mode}"}


@action("screenshot", schema={"mode": {"type": "str", "choices": ["region", "window", "full", "interactive"]}, "clipboard": {"type": "bool"}})
def screenshot(params: dict):
    """Captura de pantalla.
    params: {"mode": "region" | "window" | "full", "clipboard": true}
      - region:  seleccionar una zona (por defecto al portapapeles)
      - window:  clic en una ventana para capturarla
      - full:    pantalla completa
    Con "clipboard": true va al portapapeles; si no, se guarda en el Escritorio.
    """
    mode = params.get("mode", "region")
    if mode == "interactive":       # compatibilidad con la config anterior
        mode = "region"
    if IS_MAC:
        to_clip = params.get("clipboard", mode == "region")
        args = ["screencapture"]
        if mode == "region":
            args.append("-i")
        elif mode == "window":
            args += ["-i", "-W"]    # selección de ventana
        # 'full' no añade flag
        if to_clip:
            args.append("-c")
            subprocess.run(args, check=False)
            return {"message": "Captura al portapapeles"}
        import os
        dest = os.path.expanduser("~/Desktop/MiniDeck-captura.png")
        args.append(dest)
        subprocess.run(args, check=False)
        return {"message": "Captura guardada en el Escritorio"}
    if IS_WIN:
        raise RuntimeError("En Windows usa la acción 'hotkey' con windows+shift+s")
    raise RuntimeError("Captura no soportada en este sistema")


@action("show_desktop")
def show_desktop(params: dict):
    """Muestra el escritorio (minimiza/aparta todas las ventanas). params: {}"""
    if IS_MAC:
        # F11 = key code 103 → "Mostrar escritorio" de Mission Control
        _osascript('tell application "System Events" to key code 103')
        return {"message": "Mostrando escritorio"}
    if IS_WIN:
        raise RuntimeError("En Windows usa la acción 'hotkey' con windows+d")
    raise RuntimeError("Mostrar escritorio no soportado en este sistema")


@action("kill_process", schema={"name": {"type": "str", "required": True}})
def kill_process(params: dict):
    """Cierra un proceso por nombre.
    params: {"name": "Safari"}  (en Windows: "notepad.exe")
    """
    name = params.get("name")
    if not name:
        raise ValueError("Falta el parámetro 'name'")
    if IS_WIN:
        subprocess.run(["taskkill", "/im", name, "/f"],
                       capture_output=True, check=False)
    else:
        subprocess.run(["pkill", "-f", name], capture_output=True, check=False)
    return {"message": f"Proceso cerrado: {name}"}
