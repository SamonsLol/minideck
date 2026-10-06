# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Iconos con caché local.

El deck usa iconos de Iconify ("lucide:play", "mdi:microphone"…). En vez de
que el móvil los pida a internet, los pide al servidor, que los descarga UNA
vez, los guarda en disco y desde entonces los sirve sin conexión. Si un
servicio cae se prueba el siguiente.
"""
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from paths import ICON_CACHE_DIR

log = logging.getLogger("minideck.icons")

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,20})$")

# Servidores públicos de Iconify (mismo API) y, para lucide, el paquete npm.
_ICONIFY_HOSTS = ("https://api.iconify.design", "https://api.simplesvg.com",
                  "https://api.unisvg.com")
_FAIL_TTL = 60.0           # no reintentar un icono/servidor que falló durante 60 s
_failed: dict[str, float] = {}
_host_down: dict[str, float] = {}   # servidor sin respuesta → saltarlo un rato
_lock = threading.Lock()
_inflight: dict[str, threading.Event] = {}


def _sources(pack: str, name: str) -> list[str]:
    urls = [f"{h}/{pack}/{name}.svg" for h in _ICONIFY_HOSTS]
    if pack == "lucide":
        urls.append(f"https://cdn.jsdelivr.net/npm/lucide-static@latest/icons/{name}.svg")
    return urls


def _download(pack: str, name: str) -> str | None:
    now = time.monotonic()
    for url in _sources(pack, name):
        host = urllib.parse.urlsplit(url).netloc
        if now - _host_down.get(host, -_FAIL_TTL) < _FAIL_TTL:
            continue
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "MiniDeck"})
            with urllib.request.urlopen(req, timeout=3) as r:
                svg = r.read(200_000).decode("utf-8", errors="replace")
            if svg.lstrip().startswith("<svg"):
                return svg
        except urllib.error.HTTPError:
            continue                       # el servidor responde: el icono no existe
        except Exception:  # noqa: BLE001  (sin red / timeout: saltar este servidor)
            _host_down[host] = time.monotonic()
    return None


def get_svg(pack: str, name: str) -> str | None:
    """SVG del icono (de la caché o descargado). None si no existe/no hay red.
    pack y name deben haberse validado con NAME_RE."""
    path = ICON_CACHE_DIR / pack / f"{name}.svg"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        pass
    key = f"{pack}:{name}"
    if time.monotonic() - _failed.get(key, -_FAIL_TTL) < _FAIL_TTL:
        return None
    # una sola descarga por icono aunque lo pidan varios clientes a la vez
    with _lock:
        ev = _inflight.get(key)
        owner = ev is None
        if owner:
            ev = _inflight[key] = threading.Event()
    if not owner:
        ev.wait(15)
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return None
    try:
        return _fetch_and_store(pack, name, key, path)
    finally:
        with _lock:
            _inflight.pop(key, None)
        ev.set()


def _fetch_and_store(pack: str, name: str, key: str, path) -> str | None:
    svg = _download(pack, name)
    if svg is None:
        _failed[key] = time.monotonic()
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg, encoding="utf-8")
    except OSError as exc:
        log.warning("No se pudo guardar el icono %s en caché: %s", key, exc)
    return svg


def colorize(svg: str, color: str) -> str:
    """Los SVG de lucide/Iconify usan currentColor: se sustituye por el color."""
    return svg.replace("currentColor", color) if color else svg
