"""Integración profunda con Discord vía su API local (IPC/RPC).
Mute real con estado sincronizado + quién está hablando en tu canal de voz.

CONFIGURACIÓN (una sola vez, ~3 minutos):
1. https://discord.com/developers/applications → "New Application" (ej. MiniDeck)
2. Pestaña OAuth2 → Redirects → añade:  http://localhost:8765/callback
3. Copia el Client ID (pestaña OAuth2) y el Client Secret ("Reset Secret")
   en discord.json, dentro de la carpeta de config (server/config/ en
   desarrollo). Plantilla: server/config/discord.example.json
       {"client_id": "...", "client_secret": "..."}
4. Reinicia MiniDeck con la app de Discord ABIERTA. Discord mostrará un
   diálogo de autorización: acéptalo. El token queda guardado y no vuelve
   a preguntar.

Esto funciona sin aprobación de Discord porque las apps pueden usar el
scope 'rpc' con la cuenta de su propio dueño (tú).

⚠️ discord.json guarda secretos: NUNCA lo subas a git (está en .gitignore).
Funciona en Windows (named pipe) y en macOS/Linux (socket Unix).
"""
import json
import logging
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid

from paths import DISCORD_CFG_PATH

from . import action

log = logging.getLogger("minideck.discord")

CFG_PATH = DISCORD_CFG_PATH
REDIRECT = "http://localhost:8765/callback"

_state = {"connected": False, "mute": False, "deaf": False,
          "channel": None, "members": []}
_lock = threading.Lock()
_pending = {}          # nonce -> {"ev": Event, "data": respuesta}
_pipe = None
_send_lock = threading.Lock()
_channel_dirty = threading.Event()
_subscribed_channel = None


# ---------------------------------------------------------------- config ---
def _load_cfg():
    if not CFG_PATH.exists():
        return None
    try:
        cfg = json.loads(CFG_PATH.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    return cfg if cfg.get("client_id") and cfg.get("client_secret") else None


def _save_cfg(cfg):
    CFG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# ------------------------------------------------------------- protocolo ---
def _send(op, payload):
    data = json.dumps(payload).encode()
    with _send_lock:
        _pipe.write(struct.pack("<II", op, len(data)) + data)


def _read_exact(n):
    buf = b""
    while len(buf) < n:
        chunk = _pipe.read(n - len(buf))
        if not chunk:
            raise ConnectionError("Discord cerró la conexión")
        buf += chunk
    return buf


def _recv():
    _, ln = struct.unpack("<II", _read_exact(8))
    return json.loads(_read_exact(ln).decode())


def _open_ipc():
    """Abre el canal IPC de Discord: named pipe en Windows, socket Unix en
    macOS/Linux. Devuelve un objeto con read()/write() binarios, o None."""
    if sys.platform == "win32":
        for i in range(10):
            try:
                return open(rf"\\?\pipe\discord-ipc-{i}", "r+b", buffering=0)
            except OSError:
                continue
        return None
    bases = [os.environ.get(k) for k in ("XDG_RUNTIME_DIR", "TMPDIR", "TMP", "TEMP")]
    bases += [tempfile.gettempdir(), "/tmp"]
    for base in dict.fromkeys(filter(None, bases)):
        # Flatpak y Snap ponen el socket en subcarpetas
        for sub in ("", "app/com.discordapp.Discord", "snap.discord"):
            for i in range(10):
                path = os.path.join(base, sub, f"discord-ipc-{i}")
                if not os.path.exists(path):
                    continue
                try:
                    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    sock.connect(path)
                    return sock.makefile("rwb", buffering=0)
                except OSError:
                    continue
    return None


def _cmd_sync(cmd, args=None, evt=None):
    """Comando síncrono desde el hilo lector: despacha frames ajenos
    mientras espera su propia respuesta."""
    nonce = str(uuid.uuid4())
    payload = {"cmd": cmd, "nonce": nonce}
    if args is not None:
        payload["args"] = args
    if evt is not None:
        payload["evt"] = evt
    _send(1, payload)
    while True:
        msg = _recv()
        if msg.get("nonce") == nonce:
            if msg.get("evt") == "ERROR":
                raise RuntimeError(msg.get("data", {}).get("message", "error RPC"))
            return msg.get("data")
        _handle(msg)


def _cmd(cmd, args=None, timeout=8):
    """Comando desde otros hilos (acciones): el hilo lector resuelve."""
    if _pipe is None or not _state["connected"]:
        raise RuntimeError("Discord RPC no conectado")
    nonce = str(uuid.uuid4())
    ev = threading.Event()
    _pending[nonce] = {"ev": ev, "data": None}
    payload = {"cmd": cmd, "nonce": nonce}
    if args is not None:
        payload["args"] = args
    _send(1, payload)
    if not ev.wait(timeout):
        _pending.pop(nonce, None)
        raise TimeoutError(f"Discord no respondió a {cmd}")
    msg = _pending.pop(nonce)["data"]
    if msg.get("evt") == "ERROR":
        raise RuntimeError(msg.get("data", {}).get("message", "error RPC"))
    return msg.get("data")


# ---------------------------------------------------------------- eventos --
def _member_from_voice_state(v):
    return {"id": v["user"]["id"],
            "name": v.get("nick") or v["user"].get("global_name")
                    or v["user"]["username"],
            "speaking": False}


def _handle(msg):
    nonce = msg.get("nonce")
    if nonce and nonce in _pending:
        _pending[nonce]["data"] = msg
        _pending[nonce]["ev"].set()
        return

    evt = msg.get("evt")
    data = msg.get("data") or {}
    with _lock:
        if evt == "VOICE_SETTINGS_UPDATE":
            _state["mute"] = bool(data.get("mute"))
            _state["deaf"] = bool(data.get("deaf"))
        elif evt == "SPEAKING_START":
            for m in _state["members"]:
                if m["id"] == data.get("user_id"):
                    m["speaking"] = True
        elif evt == "SPEAKING_STOP":
            for m in _state["members"]:
                if m["id"] == data.get("user_id"):
                    m["speaking"] = False
        elif evt == "VOICE_STATE_CREATE":
            m = _member_from_voice_state(data)
            if not any(x["id"] == m["id"] for x in _state["members"]):
                _state["members"].append(m)
        elif evt == "VOICE_STATE_DELETE":
            uid = (data.get("user") or {}).get("id")
            _state["members"] = [m for m in _state["members"] if m["id"] != uid]
        elif evt == "VOICE_CHANNEL_SELECT":
            _channel_dirty.set()


def _resubscribe_channel():
    """Lee el canal de voz actual, actualiza miembros y (re)suscribe eventos."""
    global _subscribed_channel
    per_channel = ("SPEAKING_START", "SPEAKING_STOP",
                   "VOICE_STATE_CREATE", "VOICE_STATE_DELETE")
    if _subscribed_channel:
        for evt in per_channel:
            try:
                _cmd_sync("UNSUBSCRIBE", {"channel_id": _subscribed_channel}, evt=evt)
            except Exception:  # noqa: BLE001
                pass
        _subscribed_channel = None

    ch = _cmd_sync("GET_SELECTED_VOICE_CHANNEL")
    with _lock:
        if not ch:
            _state["channel"] = None
            _state["members"] = []
        else:
            _state["channel"] = ch.get("name")
            _state["members"] = [_member_from_voice_state(v)
                                 for v in ch.get("voice_states", [])]
    if ch:
        for evt in per_channel:
            _cmd_sync("SUBSCRIBE", {"channel_id": ch["id"]}, evt=evt)
        _subscribed_channel = ch["id"]


# --------------------------------------------------------------- conexión --
class AuthError(RuntimeError):
    """Error de autorización: reintentar despacio, sin spamear el diálogo."""


def _exchange_token(cfg, code=None, refresh=None):
    fields = {"client_id": cfg["client_id"],
              "client_secret": cfg["client_secret"]}
    if code:
        fields.update(grant_type="authorization_code", code=code,
                      redirect_uri=REDIRECT)
    else:
        fields.update(grant_type="refresh_token", refresh_token=refresh)
    req = urllib.request.Request(
        "https://discord.com/api/oauth2/token",
        data=urllib.parse.urlencode(fields).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 # Cloudflare bloquea el User-Agent por defecto de Python
                 # (error 1010): identificarse como navegador normal
                 "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/126.0.0.0 Safari/537.36")})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        # Discord explica el motivo en el cuerpo: mostrarlo tal cual
        detalle = e.read().decode(errors="replace")[:300]
        raise AuthError(f"Discord rechazó el canje de token "
                        f"(HTTP {e.code}): {detalle}") from None


def _authenticate(cfg):
    if cfg.get("access_token"):
        try:
            _cmd_sync("AUTHENTICATE", {"access_token": cfg["access_token"]})
            return
        except Exception:  # noqa: BLE001
            pass
    if cfg.get("refresh_token"):
        try:
            tok = _exchange_token(cfg, refresh=cfg["refresh_token"])
            cfg["access_token"] = tok["access_token"]
            cfg["refresh_token"] = tok.get("refresh_token", cfg["refresh_token"])
            _save_cfg(cfg)
            _cmd_sync("AUTHENTICATE", {"access_token": cfg["access_token"]})
            return
        except Exception:  # noqa: BLE001
            pass
    # primera vez: Discord muestra el diálogo de autorización
    log.info("Discord: acepta el diálogo de autorización en la app de Discord…")
    data = _cmd_sync("AUTHORIZE",
                     {"client_id": cfg["client_id"], "scopes": ["rpc"]})
    tok = _exchange_token(cfg, code=data["code"])
    cfg["access_token"] = tok["access_token"]
    cfg["refresh_token"] = tok.get("refresh_token")
    _save_cfg(cfg)
    _cmd_sync("AUTHENTICATE", {"access_token": cfg["access_token"]})


def _connect_once(cfg):
    global _pipe, _subscribed_channel
    _pipe = _open_ipc()
    if _pipe is None:
        raise ConnectionError("Discord no está abierto")

    _send(0, {"v": 1, "client_id": cfg["client_id"]})
    _recv()                    # DISPATCH READY
    _authenticate(cfg)

    vs = _cmd_sync("GET_VOICE_SETTINGS")
    with _lock:
        _state["connected"] = True
        _state["mute"] = bool(vs.get("mute"))
        _state["deaf"] = bool(vs.get("deaf"))
    _cmd_sync("SUBSCRIBE", None, evt="VOICE_SETTINGS_UPDATE")
    _cmd_sync("SUBSCRIBE", None, evt="VOICE_CHANNEL_SELECT")
    _subscribed_channel = None
    _resubscribe_channel()
    log.info("Discord RPC conectado ✓")

    while True:                # bucle lector
        _handle(_recv())
        if _channel_dirty.is_set():
            _channel_dirty.clear()
            _resubscribe_channel()


def _worker():
    last_err = None
    waiting_logged = False
    while True:
        cfg = _load_cfg()
        if not cfg:
            # Discord es opcional: avisar una vez, sin ensuciar el log.
            if not waiting_logged:
                log.info("Discord RPC desactivado (sin %s; ver "
                         "config/discord.example.json)", CFG_PATH.name)
                waiting_logged = True
            time.sleep(30)
            continue
        waiting_logged = False
        try:
            _connect_once(cfg)
        except AuthError as exc:
            with _lock:
                _state.update(connected=False, channel=None, members=[])
            log.error("Discord RPC — AUTORIZACIÓN FALLIDA: %s", exc)
            log.error("Revisa: (1) en el portal, OAuth2 → Redirects debe "
                      "contener EXACTAMENTE %s (y pulsar Save Changes); "
                      "(2) el Client Secret debe ser el vigente (Reset "
                      "Secret lo invalida). Reintento en 60s.", REDIRECT)
            time.sleep(60)
        except Exception as exc:  # noqa: BLE001
            with _lock:
                _state.update(connected=False, channel=None, members=[])
            # mismo error en bucle (p. ej. Discord cerrado): avisar una vez
            if str(exc) != last_err:
                log.warning("Discord RPC: %s — reintentando cada 10s", exc)
                last_err = str(exc)
            time.sleep(10)


threading.Thread(target=_worker, daemon=True, name="discord-rpc").start()


# ---------------------------------------------------------------- acciones -
def _snapshot():
    with _lock:
        return {"discord": {**_state,
                            "members": [dict(m) for m in _state["members"]]}}


@action("discord_get")
def discord_get(params: dict):
    """Estado actual de Discord (para el vigilante). params: {}"""
    return {"state": _snapshot()}


@action("discord_mute")
def discord_mute(params: dict):
    """Alterna (o fuerza) el mute del micro en Discord.
    params: {} o {"mute": true/false}
    """
    target = params.get("mute")
    if target is None:
        target = not _state["mute"]
    _cmd("SET_VOICE_SETTINGS", {"mute": bool(target)})
    with _lock:
        _state["mute"] = bool(target)
    return {"message": "Micro silenciado" if target else "Micro activo",
            "state": _snapshot()}


@action("discord_deafen")
def discord_deafen(params: dict):
    """Alterna (o fuerza) la sordina en Discord.
    params: {} o {"deaf": true/false}
    """
    target = params.get("deaf")
    if target is None:
        target = not _state["deaf"]
    _cmd("SET_VOICE_SETTINGS", {"deaf": bool(target)})
    with _lock:
        _state["deaf"] = bool(target)
    return {"message": "Sordina activada" if target else "Sordina quitada",
            "state": _snapshot()}
