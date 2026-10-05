"""Mezclador de volumen por aplicación (como el de Windows).
Usa las sesiones de audio de pycaw: cada app que reproduce sonido
aparece con su propio volumen y mute, agrupada por ejecutable.
"""
import re
import sys

if sys.platform != "win32":
    raise ImportError("mixer solo aplica a Windows")

from comtypes import CoInitialize, CoUninitialize
from pycaw.pycaw import AudioUtilities

from . import action


def _with_com(fn):
    CoInitialize()
    try:
        return fn()
    finally:
        CoUninitialize()


def _session_name(s):
    """Nombre de la app de una sesión, con tres niveles de fallback:
    1) el proceso (falla para apps elevadas/protegidas, ej. juegos)
    2) el identificador de la sesión (contiene la ruta del .exe)
    3) 'Sistema'
    """
    try:
        proc = s.Process
        if proc:
            return proc.name()
    except Exception:  # noqa: BLE001
        pass
    for attr in ("Identifier", "InstanceIdentifier"):
        try:
            ident = getattr(s, attr, "") or ""
            m = re.search(r"([^\\/%|]+\.exe)", ident, re.IGNORECASE)
            if m:
                return m.group(1)
        except Exception:  # noqa: BLE001
            pass
    return "Sistema"


def _sessions_by_app():
    """{'chrome.exe': [SimpleAudioVolume, ...], 'Sistema': [...]}"""
    try:
        sessions = AudioUtilities.GetAllSessions()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"GetAllSessions falló: {type(exc).__name__}: {exc}") from exc
    apps = {}
    for s in sessions:
        try:
            vol = s.SimpleAudioVolume
            if vol is None:
                continue
            apps.setdefault(_session_name(s), []).append(vol)
        except Exception:  # noqa: BLE001
            continue  # una sesión rota no debe tumbar la lista
    return apps


def _snapshot_unlocked():
    out = []
    for name, vols in sorted(_sessions_by_app().items(),
                             key=lambda x: x[0].lower()):
        try:
            v = vols[0]
            pretty = name[:-4] if name.lower().endswith(".exe") else name
            out.append({"app": name,
                        "name": pretty.capitalize() if pretty.islower() else pretty,
                        "volume": round(v.GetMasterVolume() * 100),
                        "muted": bool(v.GetMute())})
        except Exception:  # noqa: BLE001
            continue
    return out


@action("mixer_get")
def mixer_get(params: dict):
    """Apps con audio activo y sus volúmenes. params: {}"""
    return {"state": {"mixer": _with_com(_snapshot_unlocked)}}


@action("mixer_set")
def mixer_set(params: dict):
    """Volumen de UNA aplicación (todas sus sesiones).
    params: {"app": "chrome.exe", "level": 40}
    """
    app = params.get("app")
    level = max(0, min(100, int(params.get("level", 50))))
    if not app:
        raise ValueError("Falta el parámetro 'app'")

    def run():
        vols = _sessions_by_app().get(app)
        if not vols:
            raise ValueError(f"'{app}' no tiene audio activo")
        for v in vols:
            v.SetMasterVolume(level / 100, None)
        return _snapshot_unlocked()

    return {"message": f"{app}: {level}%",
            "state": {"mixer": _with_com(run)}}


@action("mixer_mute")
def mixer_mute(params: dict):
    """Alterna (o fuerza) el mute de una aplicación.
    params: {"app": "chrome.exe"} o {"app": "...", "mute": true/false}
    """
    app = params.get("app")
    if not app:
        raise ValueError("Falta el parámetro 'app'")

    def run():
        vols = _sessions_by_app().get(app)
        if not vols:
            raise ValueError(f"'{app}' no tiene audio activo")
        target = params.get("mute")
        if target is None:
            target = not vols[0].GetMute()
        for v in vols:
            v.SetMute(bool(target), None)
        return bool(target), _snapshot_unlocked()

    muted, snap = _with_com(run)
    return {"message": f"{app}: {'silenciado' if muted else 'con sonido'}",
            "state": {"mixer": snap}}
