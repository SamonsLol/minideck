# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Control de volumen del sistema en macOS (vía `osascript`).

Equivalente a volume.py/mixer.py de Windows (que usan pycaw y no cargan en
Mac). macOS no expone volumen por-aplicación como Windows, así que el
"mezclador" muestra una sola entrada: el volumen general del sistema.
"""
import subprocess
import sys

from . import action

if sys.platform != "darwin":
    raise ImportError("volume_mac solo aplica a macOS")


def _osa(script: str) -> str:
    try:
        out = subprocess.run(["osascript", "-e", script],
                             capture_output=True, text=True, timeout=3)
        return (out.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _get() -> dict:
    """Volumen (0-100) y mute actuales del sistema."""
    raw = _osa('set v to (get volume settings)\n'
               'return (output volume of v as text) & "|" & (output muted of v as text)')
    vol, muted = 0, False
    if "|" in raw:
        a, b = raw.split("|", 1)
        try:
            vol = int(float(a))
        except ValueError:
            vol = 0
        muted = b.strip().lower() == "true"
    return {"volume": vol, "muted": muted}


def _set_volume(level: int):
    _osa(f"set volume output volume {max(0, min(100, level))}")


def _set_muted(muted: bool):
    _osa(f"set volume output muted {'true' if muted else 'false'}")


# --- volumen maestro (botón Silenciar, sliders de volumen) -----------------

@action("volume_get")
def volume_get(params: dict):
    """Volumen y mute actuales, sin cambiar nada. params: {}"""
    return {"state": _get()}


@action("volume_set")
def volume_set(params: dict):
    """params: {"level": 50}  (0-100)"""
    level = max(0, min(100, int(params.get("level", 50))))
    _set_volume(level)
    return {"message": f"Volumen: {level}%", "state": _get()}


@action("volume_change")
def volume_change(params: dict):
    """params: {"delta": 5}  o  {"delta": -5}"""
    delta = int(params.get("delta", 5))
    new = max(0, min(100, _get()["volume"] + delta))
    _set_volume(new)
    return {"message": f"Volumen: {new}%", "state": _get()}


@action("volume_mute")
def volume_mute(params: dict):
    """Alterna silencio. params: {} o {"mute": true/false} para forzar."""
    target = params.get("mute")
    if target is None:
        target = not _get()["muted"]
    _set_muted(bool(target))
    return {"message": "Silenciado" if target else "Sonido activado",
            "state": _get()}


# --- "mezclador": en macOS, solo el volumen general del sistema -------------

def _mixer_snapshot():
    g = _get()
    return [{"app": "system", "name": "Sistema",
             "volume": g["volume"], "muted": g["muted"]}]


@action("mixer_get")
def mixer_get(params: dict):
    """En Windows lista el volumen por app; en macOS solo el del sistema."""
    return {"state": {"mixer": _mixer_snapshot()}}


@action("mixer_set")
def mixer_set(params: dict):
    """params: {"app": "system", "level": 40}. En macOS ajusta el volumen
    general (macOS no permite volumen por-aplicación desde fuera)."""
    level = max(0, min(100, int(params.get("level", 50))))
    _set_volume(level)
    return {"message": f"Volumen: {level}%", "state": {"mixer": _mixer_snapshot()}}


@action("mixer_mute")
def mixer_mute(params: dict):
    """Alterna (o fuerza) el silencio del sistema."""
    target = params.get("mute")
    if target is None:
        target = not _get()["muted"]
    _set_muted(bool(target))
    return {"message": "Silenciado" if target else "Sonido activado",
            "state": {"mixer": _mixer_snapshot()}}
