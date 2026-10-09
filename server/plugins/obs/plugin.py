# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Control de OBS Studio mediante obs-websocket v5 (incluido en OBS 28+).

Protocolo (https://github.com/obsproject/obs-websocket/blob/master/docs/generated/protocol.md):
    1. El servidor envía Hello (op 0). Si trae "authentication" {challenge, salt}:
           secret = base64(sha256(password + salt))
           auth   = base64(sha256(secret + challenge))
    2. El cliente responde Identify (op 1) con rpcVersion 1 (y auth si hace falta).
    3. El servidor confirma con Identified (op 2).
    4. Peticiones: op 6 {requestType, requestId, requestData}
       Respuestas: op 7 {requestType, requestId, requestStatus, responseData}

Se mantiene UNA conexión persistente protegida por un lock y se reconecta
de forma perezosa si se cae. Los timeouts son cortos para que un OBS cerrado
nunca bloquee MiniDeck.

Ajustes (en deck.json → "pluginSettings" → "obs"):
    "host":     "localhost"
    "port":     4455
    "password": contraseña del servidor WebSocket de OBS ("" = sin auth)
"""
import base64
import hashlib
import json
import os
import sys
import threading
import time
import uuid

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect

from actions import action, plugin_settings

PLUGIN_ID = "obs"
TIMEOUT = 3.0          # segundos para conectar / esperar respuesta
POLL_EVERY = 2.0       # como mucho una consulta a OBS cada 2 s
RETRY_EVERY = 10.0     # si OBS está caído, no reintentar antes de 10 s

# RLock: las acciones llaman a _request varias veces con el lock tomado.
_lock = threading.RLock()
_conn = {"ws": None, "key": None}
_cache = {"data": None, "t": 0.0, "fail_t": 0.0}


def _offline() -> dict:
    return {"connected": False, "recording": False, "streaming": False,
            "paused": False, "scene": None, "scenes": []}


def _settings() -> dict:
    """Ajustes del plugin (separado para poder sustituirlo en los tests)."""
    return plugin_settings(PLUGIN_ID)


def auth_string(password: str, salt: str, challenge: str) -> str:
    """Cadena de autenticación de obs-websocket v5."""
    secret = base64.b64encode(hashlib.sha256((password + salt).encode()).digest())
    return base64.b64encode(hashlib.sha256(secret + challenge.encode()).digest()).decode()


# -------------------------------------------------------------- conexión ---
def _drop() -> None:
    ws, _conn["ws"], _conn["key"] = _conn["ws"], None, None
    if ws is not None:
        try:
            ws.close()
        except Exception:  # noqa: BLE001
            pass


def _close_code(exc: ConnectionClosed) -> int | None:
    frame = getattr(exc, "rcvd", None)
    return getattr(frame, "code", None)


def _handshake(ws, password: str) -> None:
    hello = json.loads(ws.recv(timeout=TIMEOUT))
    if hello.get("op") != 0:
        raise RuntimeError("OBS respondió algo inesperado (¿es obs-websocket v5?)")
    d = hello.get("d") or {}
    ident = {"rpcVersion": 1, "eventSubscriptions": 0}
    auth = d.get("authentication")
    if auth:
        if not password:
            raise RuntimeError("OBS pide contraseña: ponla en pluginSettings → obs → password")
        ident["authentication"] = auth_string(password, auth["salt"], auth["challenge"])
    ws.send(json.dumps({"op": 1, "d": ident}))
    msg = json.loads(ws.recv(timeout=TIMEOUT))
    if msg.get("op") != 2:
        raise RuntimeError("OBS no aceptó la identificación")


def _ensure():
    """Devuelve la conexión abierta (o la crea). Llamar con _lock tomado."""
    cfg = _settings()
    host = str(cfg.get("host") or "localhost")
    port = int(cfg.get("port") or 4455)
    password = str(cfg.get("password") or "")
    key = (host, port, password)
    if _conn["ws"] is not None and _conn["key"] == key:
        return _conn["ws"]
    _drop()
    where = f"{host}:{port}"
    try:
        # conexión de larga vida (no "with"): __enter__() devuelve la conexión
        # tanto en websockets antiguos como en los que exigen gestor de contexto
        ws = connect(f"ws://{where}", open_timeout=TIMEOUT, close_timeout=1,
                     subprotocols=["obswebsocket.json"], max_size=2 ** 22).__enter__()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"No se pudo conectar con OBS en {where}: ¿está abierto y con "
                           "el servidor WebSocket activado?") from exc
    try:
        _handshake(ws, password)
    except ConnectionClosed as exc:
        ws.close()
        if _close_code(exc) == 4009:
            raise RuntimeError("Contraseña de OBS incorrecta") from exc
        raise RuntimeError(f"OBS cerró la conexión ({_close_code(exc)})") from exc
    except RuntimeError:
        ws.close()
        raise
    except Exception as exc:  # noqa: BLE001
        ws.close()
        raise RuntimeError(f"Error al identificarse con OBS: {exc}") from exc
    _conn["ws"], _conn["key"] = ws, key
    return ws


def _request(rtype: str, data: dict | None = None) -> dict:
    """Envía una petición a OBS y devuelve su responseData (o {})."""
    with _lock:
        for attempt in (0, 1):
            ws = _ensure()
            rid = uuid.uuid4().hex
            payload = {"requestType": rtype, "requestId": rid}
            if data:
                payload["requestData"] = data
            try:
                ws.send(json.dumps({"op": 6, "d": payload}))
                while True:
                    msg = json.loads(ws.recv(timeout=TIMEOUT))
                    d = msg.get("d") or {}
                    if msg.get("op") == 7 and d.get("requestId") == rid:
                        break
            except (ConnectionClosed, OSError, TimeoutError) as exc:
                # conexión rancia (OBS reiniciado…): un reintento con conexión nueva
                _drop()
                if attempt:
                    raise RuntimeError("Se perdió la conexión con OBS") from exc
                continue
            status = d.get("requestStatus") or {}
            if not status.get("result"):
                why = status.get("comment") or f"código {status.get('code')}"
                raise RuntimeError(f"OBS rechazó {rtype}: {why}")
            return d.get("responseData") or {}
    return {}  # inalcanzable


# ---------------------------------------------------------------- estado ---
def _snapshot() -> dict:
    rec = _request("GetRecordStatus")
    stream = _request("GetStreamStatus")
    scenes = _request("GetSceneList")
    # OBS devuelve las escenas al revés de como se ven en su lista
    names = [s.get("sceneName") for s in reversed(scenes.get("scenes") or [])
             if s.get("sceneName")]
    return {"connected": True,
            "recording": bool(rec.get("outputActive")),
            "paused": bool(rec.get("outputPaused")),
            "streaming": bool(stream.get("outputActive")),
            "scene": scenes.get("currentProgramSceneName"),
            "scenes": names}


def _store(data: dict) -> dict:
    _cache["data"], _cache["t"] = data, time.monotonic()
    if data.get("connected"):
        _cache["fail_t"] = 0.0
    return data


def _state_after(patch: dict | None = None) -> dict:
    """Instantánea tras una acción (con correcciones si OBS aún no la refleja)."""
    try:
        snap = _snapshot()
    except Exception:  # noqa: BLE001
        snap = dict(_cache["data"] or _offline())
    snap.update(patch or {})
    return {"obs": _store(snap)}


@action("obs_get", state=True)
def obs_get(params: dict):
    """Estado de OBS (conexión, grabación, directo, escena actual y lista). params: {}"""
    now = time.monotonic()
    cached = _cache["data"]
    if cached is not None:
        if now - _cache["t"] < POLL_EVERY:
            return {"state": {"obs": cached}}
        if not cached.get("connected") and now - _cache["fail_t"] < RETRY_EVERY:
            return {"state": {"obs": cached}}
    # si una acción está usando la conexión, no esperamos: devolvemos la caché
    if not _lock.acquire(blocking=False):
        return {"state": {"obs": cached or _offline()}}
    try:
        data = _store(_snapshot())
    except Exception:  # noqa: BLE001
        with _lock:
            _drop()
        data = _store(_offline())
        _cache["fail_t"] = time.monotonic()
    finally:
        _lock.release()
    return {"state": {"obs": data}}


# -------------------------------------------------------------- acciones ---
@action("obs_scene")
def obs_scene(params: dict):
    """Cambia la escena de programa. params: {"scene": "Nombre"}"""
    scene = str(params.get("scene") or "").strip()
    if not scene:
        raise ValueError("Falta el nombre de la escena (params.scene)")
    with _lock:
        _request("SetCurrentProgramScene", {"sceneName": scene})
        state = _state_after({"scene": scene})
    return {"message": f"Escena: {scene}", "state": state}


def _toggle_output(rtype: str, status_rtype: str, key: str):
    with _lock:
        before = bool(_request(status_rtype).get("outputActive"))
        resp = _request(rtype)
        active = bool(resp.get("outputActive", not before))
        patch = {key: active}
        if key == "recording" and not active:
            patch["paused"] = False
        return active, _state_after(patch)


@action("obs_record_toggle")
def obs_record_toggle(params: dict):
    """Inicia/detiene la grabación. params: {}"""
    active, state = _toggle_output("ToggleRecord", "GetRecordStatus", "recording")
    return {"message": "Grabación iniciada" if active else "Grabación detenida",
            "state": state}


@action("obs_stream_toggle")
def obs_stream_toggle(params: dict):
    """Inicia/detiene la transmisión en directo. params: {}"""
    active, state = _toggle_output("ToggleStream", "GetStreamStatus", "streaming")
    return {"message": "Directo iniciado" if active else "Directo detenido",
            "state": state}


@action("obs_record_pause_toggle")
def obs_record_pause_toggle(params: dict):
    """Pausa/reanuda la grabación en curso. params: {}"""
    with _lock:
        before = _request("GetRecordStatus")
        if not before.get("outputActive"):
            raise RuntimeError("No hay ninguna grabación en curso")
        _request("ToggleRecordPause")
        paused = not before.get("outputPaused")
        state = _state_after({"paused": paused})
    return {"message": "Grabación en pausa" if paused else "Grabación reanudada",
            "state": state}


@action("obs_mute_toggle")
def obs_mute_toggle(params: dict):
    """Silencia/activa una fuente de audio. params: {"input": "Mic/Aux"}"""
    name = str(params.get("input") or "").strip()
    if not name:
        raise ValueError("Falta el nombre de la fuente de audio (params.input)")
    with _lock:
        muted = bool(_request("ToggleInputMute", {"inputName": name}).get("inputMuted"))
        state = _state_after()
    return {"message": f"{name}: {'silenciado' if muted else 'activo'}", "state": state}


@action("obs_replay_save")
def obs_replay_save(params: dict):
    """Guarda el búfer de repetición (debe estar activo en OBS). params: {}"""
    with _lock:
        _request("SaveReplayBuffer")
        state = _state_after()
    return {"message": "Repetición guardada", "state": state}


# ------------------------------------------------- webcam del móvil en OBS ---
PHONECAM_SOURCE = "MiniDeck Webcam"


def _phonecam_url() -> str:
    """URL de /phonecam/view tal como la verá OBS. En el mismo equipo no hace
    falta token (localhost); si OBS está en otro equipo, IP de la red + token."""
    import auth
    m = sys.modules.get("main") or sys.modules.get("__main__")
    port = getattr(m, "PORT", None) or int(os.environ.get("MINIDECK_PORT", "8765"))
    scheme = getattr(m, "SCHEME", "http")
    host = str(_settings().get("host") or "localhost").strip().lower()
    if host in ("localhost", "127.0.0.1", "::1"):
        return f"{scheme}://localhost:{port}/phonecam/view"
    ip = m.local_ip() if hasattr(m, "local_ip") else "localhost"
    return f"{scheme}://{ip}:{port}/phonecam/view?token={auth.TOKEN}"


def _exists(rtype: str, data: dict) -> bool:
    try:
        _request(rtype, data)
        return True
    except RuntimeError as exc:
        if "conexión" in str(exc) or "conectar" in str(exc):
            raise
        return False


@action("obs_phonecam_setup", schema={
    "scene": {"type": "str", "required": False},
    "virtualcam": {"type": "bool", "required": False},
}, timeout=20)
def obs_phonecam_setup(params: dict):
    """Añade la webcam del móvil a OBS: crea (o actualiza) la fuente de navegador
    "MiniDeck Webcam", la pone en la escena ajustada al lienzo y enciende la
    cámara virtual. params: {"scene": "" (= escena actual), "virtualcam": true}"""
    url = _phonecam_url()
    with _lock:
        video = _request("GetVideoSettings")
        w, h = int(video.get("baseWidth") or 1920), int(video.get("baseHeight") or 1080)
        scene = str(params.get("scene") or "").strip() or \
            _request("GetCurrentProgramScene").get("currentProgramSceneName")
        settings = {"url": url, "width": w, "height": h, "fps": 30,
                    "reroute_audio": False, "shutdown": False}
        if _exists("GetInputSettings", {"inputName": PHONECAM_SOURCE}):
            _request("SetInputSettings", {"inputName": PHONECAM_SOURCE,
                                          "inputSettings": settings, "overlay": True})
            if _exists("GetSceneItemId", {"sceneName": scene, "sourceName": PHONECAM_SOURCE}):
                item = _request("GetSceneItemId", {"sceneName": scene,
                                                   "sourceName": PHONECAM_SOURCE})["sceneItemId"]
            else:
                item = _request("CreateSceneItem", {"sceneName": scene,
                                                    "sourceName": PHONECAM_SOURCE})["sceneItemId"]
        else:
            item = _request("CreateInput", {"sceneName": scene, "inputName": PHONECAM_SOURCE,
                                            "inputKind": "browser_source",
                                            "inputSettings": settings,
                                            "sceneItemEnabled": True})["sceneItemId"]
        # ocupar todo el lienzo sin deformar (vertical u horizontal)
        _request("SetSceneItemTransform", {"sceneName": scene, "sceneItemId": item,
                                           "sceneItemTransform": {
                                               "positionX": 0, "positionY": 0,
                                               "boundsType": "OBS_BOUNDS_SCALE_INNER",
                                               "boundsAlignment": 0,
                                               "boundsWidth": w, "boundsHeight": h}})
        _request("SetSceneItemEnabled", {"sceneName": scene, "sceneItemId": item,
                                         "sceneItemEnabled": True})
        cam = ""
        if params.get("virtualcam", True):
            if not _request("GetVirtualCamStatus").get("outputActive"):
                _request("StartVirtualCam")
            cam = " · cámara virtual activa"
    # sin "state": así el móvil muestra el mensaje aunque no venga de un botón
    return {"message": f"Webcam añadida a OBS ({scene}){cam}"}


@action("obs_virtualcam_toggle")
def obs_virtualcam_toggle(params: dict):
    """Inicia/detiene la cámara virtual de OBS. params: {}"""
    with _lock:
        active = bool(_request("ToggleVirtualCam").get("outputActive"))
        state = _state_after()
    return {"message": "Cámara virtual activa" if active else "Cámara virtual detenida",
            "state": state}
