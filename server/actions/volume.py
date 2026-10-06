# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Control de volumen del sistema. Requiere: pip install pycaw comtypes

Compatible con pycaw moderno (GetSpeakers devuelve AudioDevice con
.EndpointVolume) y con versiones antiguas (dispositivo COM con .Activate).
COM se inicializa por llamada porque cada acción corre en su propio hilo.
"""
import sys

if sys.platform != "win32":
    raise ImportError("volume solo aplica a Windows")

from comtypes import CLSCTX_ALL, CoInitialize, CoUninitialize
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

from . import action


def _endpoint():
    device = AudioUtilities.GetSpeakers()
    # pycaw moderno: AudioDevice con propiedad EndpointVolume
    if hasattr(device, "EndpointVolume"):
        return device.EndpointVolume
    # pycaw antiguo: IMMDevice crudo
    interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return interface.QueryInterface(IAudioEndpointVolume)


def _with_volume(fn):
    CoInitialize()
    try:
        return fn(_endpoint())
    finally:
        CoUninitialize()


def _snapshot(vol) -> dict:
    return {
        "volume": round(vol.GetMasterVolumeLevelScalar() * 100),
        "muted": bool(vol.GetMute()),
    }


@action("volume_get")
def volume_get(params: dict):
    """Devuelve el volumen y mute actuales, sin cambiar nada. params: {}"""
    def run(vol):
        return {"state": _snapshot(vol)}

    return _with_volume(run)


@action("volume_set", schema={"level": {"type": "int", "min": 0, "max": 100, "required": True}})
def volume_set(params: dict):
    """params: {"level": 50}  (0-100)"""
    level = max(0, min(100, int(params.get("level", 50))))

    def run(vol):
        vol.SetMasterVolumeLevelScalar(level / 100, None)
        return {"message": f"Volumen: {level}%", "state": _snapshot(vol)}

    return _with_volume(run)


@action("volume_change", schema={"delta": {"type": "int", "min": -100, "max": 100}})
def volume_change(params: dict):
    """params: {"delta": 5}  o  {"delta": -5}"""
    delta = int(params.get("delta", 5))

    def run(vol):
        current = vol.GetMasterVolumeLevelScalar() * 100
        new = max(0, min(100, current + delta))
        vol.SetMasterVolumeLevelScalar(new / 100, None)
        return {"message": f"Volumen: {round(new)}%", "state": _snapshot(vol)}

    return _with_volume(run)


@action("volume_mute", schema={"mute": {"type": "bool"}})
def volume_mute(params: dict):
    """Alterna silencio. params: {} o {"mute": true/false} para forzar."""
    def run(vol):
        target = params.get("mute")
        if target is None:
            target = not vol.GetMute()
        vol.SetMute(bool(target), None)
        return {"message": "Silenciado" if target else "Sonido activado",
                "state": _snapshot(vol)}

    return _with_volume(run)
