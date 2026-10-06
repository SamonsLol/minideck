# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Home Assistant mediante su API REST (https://developers.home-assistant.io/docs/api/rest/).

Solo usa la biblioteca estándar (urllib). Autenticación con un token de
acceso de larga duración (Perfil → Seguridad → Tokens de acceso de larga duración).

Ajustes (en deck.json → "pluginSettings" → "homeassistant"):
    "url":      "http://homeassistant.local:8123"
    "token":    token de acceso de larga duración
    "entities": ["light.salon", "switch.ventilador"]  ← se envían como estado en vivo
"""
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from actions import action, plugin_settings

PLUGIN_ID = "homeassistant"
TIMEOUT = 5.0          # segundos por petición HTTP
POLL_EVERY = 5.0       # refresco de entidades como mucho cada 5 s
RETRY_EVERY = 15.0     # si HA no responde, esperar antes de reintentar

_NAME_RE = re.compile(r"^[a-z0-9_]+$")
_ENTITY_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")

_lock = threading.Lock()
_cache = {"data": None, "t": 0.0, "fail_t": 0.0, "key": None}


def _offline() -> dict:
    return {"connected": False, "entities": {}}


def _settings() -> dict:
    """Ajustes del plugin (separado para poder sustituirlo en los tests)."""
    return plugin_settings(PLUGIN_ID)


def _base() -> tuple[str, str]:
    cfg = _settings()
    url = str(cfg.get("url") or "").strip().rstrip("/")
    token = str(cfg.get("token") or "").strip()
    if not url:
        raise RuntimeError("Falta la URL de Home Assistant (pluginSettings → homeassistant → url)")
    if not url.startswith(("http://", "https://")):
        raise RuntimeError("La URL de Home Assistant debe empezar por http:// o https://")
    if not token:
        raise RuntimeError("Falta el token de Home Assistant "
                           "(pluginSettings → homeassistant → token)")
    return url, token


def _http(method: str, path: str, body: dict | None = None):
    """Petición a la API de HA; devuelve el JSON de la respuesta (o None)."""
    url, token = _base()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url + path, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read()
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise RuntimeError("Home Assistant rechazó el token (401)") from exc
        if exc.code == 404:
            raise RuntimeError(f"Home Assistant: no existe {path} (404)") from exc
        if exc.code == 400:
            raise RuntimeError("Home Assistant: petición no válida (400). "
                               "Revisa el servicio y sus datos") from exc
        raise RuntimeError(f"Home Assistant respondió con error HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        why = getattr(exc, "reason", exc)
        raise RuntimeError(f"No se pudo conectar con Home Assistant en {url}: {why}") from exc
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _check_entity(entity_id) -> str:
    eid = str(entity_id or "").strip()
    if not _ENTITY_RE.match(eid):
        raise ValueError(f"entity_id no válido: '{eid}' (ej. light.salon)")
    return eid


def _entity_info(st: dict) -> dict:
    attrs = st.get("attributes") or {}
    return {"state": st.get("state"),
            "name": attrs.get("friendly_name") or st.get("entity_id")}


def _merge_changed(changed) -> dict | None:
    """Actualiza la caché con los estados que devuelve una llamada a servicio."""
    data = _cache["data"]
    if not isinstance(changed, list) or not data:
        return None
    wanted = set(_entities())
    ents = dict(data.get("entities") or {})
    for st in changed:
        if isinstance(st, dict) and st.get("entity_id") in wanted:
            ents[st["entity_id"]] = _entity_info(st)
    data = {"connected": True, "entities": ents}
    _cache["data"] = data
    return data


def _call_service(domain: str, service: str, body: dict) -> dict:
    if not _NAME_RE.match(domain or ""):
        raise ValueError(f"Dominio no válido: '{domain}' (solo a-z, 0-9 y _)")
    if not _NAME_RE.match(service or ""):
        raise ValueError(f"Servicio no válido: '{service}' (solo a-z, 0-9 y _)")
    changed = _http("POST", f"/api/services/{domain}/{service}", body)
    out = {"message": f"Home Assistant: {domain}.{service}"}
    data = _merge_changed(changed)
    if data is not None:
        out["state"] = {"ha": data}
    return out


# -------------------------------------------------------------- acciones ---
@action("ha_service")
def ha_service(params: dict):
    """Llama a cualquier servicio de HA.
    params: {"domain": "light", "service": "toggle", "entity_id": "light.salon",
             "data": {"brightness_pct": 50}}"""
    domain = str(params.get("domain") or "").strip()
    service = str(params.get("service") or "").strip()
    extra = params.get("data") or {}
    if not isinstance(extra, dict):
        raise ValueError("params.data debe ser un objeto JSON")
    body = dict(extra)
    eid = params.get("entity_id")
    if eid:
        body["entity_id"] = ([_check_entity(e) for e in eid] if isinstance(eid, list)
                             else _check_entity(eid))
    return _call_service(domain, service, body)


@action("ha_toggle")
def ha_toggle(params: dict):
    """Conmuta una entidad (luz, interruptor…). params: {"entity_id": "light.salon"}"""
    eid = _check_entity(params.get("entity_id"))
    out = _call_service("homeassistant", "toggle", {"entity_id": eid})
    out["message"] = f"Home Assistant: {eid} conmutado"
    return out


@action("ha_scene")
def ha_scene(params: dict):
    """Activa una escena. params: {"entity_id": "scene.cine"}"""
    eid = _check_entity(params.get("entity_id"))
    out = _call_service("scene", "turn_on", {"entity_id": eid})
    out["message"] = f"Escena activada: {eid}"
    return out


# ---------------------------------------------------------------- estado ---
def _entities() -> list[str]:
    ents = _settings().get("entities") or []
    if isinstance(ents, str):
        ents = [ents]
    return [e for e in ents if isinstance(e, str) and _ENTITY_RE.match(e.strip())]


def _fetch(entities: list[str]) -> dict:
    out = {}
    for eid in entities:
        try:
            st = _http("GET", f"/api/states/{urllib.parse.quote(eid, safe='')}")
        except RuntimeError as exc:
            if "404" in str(exc):
                out[eid] = {"state": "unavailable", "name": eid}
                continue
            raise   # conexión/token: abortar el resto
        out[eid] = _entity_info(st or {})
    return {"connected": True, "entities": out}


@action("ha_get", state=True)
def ha_get(params: dict):
    """Estado de las entidades configuradas en "entities". params: {}"""
    cfg = _settings()
    entities = _entities()
    if not entities or not cfg.get("url") or not cfg.get("token"):
        return {"state": {"ha": _offline()}}
    now = time.monotonic()
    key = (cfg.get("url"), cfg.get("token"), tuple(entities))
    cached = _cache["data"]
    if cached is not None and _cache["key"] == key:
        if now - _cache["t"] < POLL_EVERY:
            return {"state": {"ha": cached}}
        if not cached.get("connected") and now - _cache["fail_t"] < RETRY_EVERY:
            return {"state": {"ha": cached}}
    if not _lock.acquire(blocking=False):
        return {"state": {"ha": cached or _offline()}}
    try:
        try:
            data = _fetch(entities)
        except Exception:  # noqa: BLE001
            data = _offline()
            _cache["fail_t"] = time.monotonic()
        _cache.update(data=data, t=time.monotonic(), key=key)
    finally:
        _lock.release()
    return {"state": {"ha": data}}
