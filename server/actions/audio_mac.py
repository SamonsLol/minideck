# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Cambiar el dispositivo de salida/entrada de audio en macOS.

Usa SwitchAudioSource (brew install switchaudio-osx). Sin él, avisa cómo
instalarlo. Sin "device" en params, alterna al siguiente dispositivo.
"""
import shutil
import subprocess
import sys

from . import action

if sys.platform != "darwin":
    raise ImportError("audio_mac solo aplica a macOS")


def _switch(kind: str, params: dict):
    exe = shutil.which("SwitchAudioSource")
    if not exe:
        return {"message": "Instala: brew install switchaudio-osx"}
    dev = params.get("device")
    if dev:
        subprocess.run([exe, "-t", kind, "-s", dev], check=False)
        return {"message": f"Audio {kind}: {dev}"}
    devs = [d.strip() for d in subprocess.run(
        [exe, "-t", kind, "-a"], capture_output=True, text=True).stdout.splitlines()
        if d.strip()]
    cur = subprocess.run([exe, "-t", kind, "-c"],
                         capture_output=True, text=True).stdout.strip()
    if not devs:
        return {"message": "Sin dispositivos"}
    i = devs.index(cur) if cur in devs else -1
    nxt = devs[(i + 1) % len(devs)]
    subprocess.run([exe, "-t", kind, "-s", nxt], check=False)
    return {"message": f"Audio {kind}: {nxt}"}


@action("audio_output")
def audio_output(params: dict):
    """Cambia la salida de audio. params: {"device": "..."} o vacío = siguiente."""
    return _switch("output", params)


@action("audio_input")
def audio_input(params: dict):
    """Cambia el micrófono. params: {"device": "..."} o vacío = siguiente."""
    return _switch("input", params)
