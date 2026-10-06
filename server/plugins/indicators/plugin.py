# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Indicadores en vivo: clima, red, estado de Git y de Docker.

Una sola fuente de estado ("indicators_get") que el vigilante sondea cada
segundo, pero con cachés internas para no abusar (clima cada 10 min, git/docker
cada pocos segundos).

Ajustes (en deck.json → "pluginSettings" → "indicators"):
    "git_repo":          ruta del repo a vigilar ("" = desactivado)
    "weather_location":  "Bogota", "Madrid"… ("" = detecta por IP)
    "weather_enabled":   false para no consultar wttr.in
"""
import os
import subprocess
import time
import urllib.parse
import urllib.request

import psutil

from actions import action, plugin_settings

# sin ventanas de consola fugaces en Windows
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_c = {"data": {}, "git_t": 0, "docker_t": 0, "weather_t": 0, "net": None}


def _git():
    repo = os.path.expanduser(plugin_settings("indicators").get("git_repo") or "")
    if not repo:
        return None
    try:
        b = subprocess.run(["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, timeout=3,
                           creationflags=_NO_WINDOW)
        if b.returncode != 0:
            return None
        s = subprocess.run(["git", "-C", repo, "status", "--porcelain"],
                           capture_output=True, text=True, timeout=3,
                           creationflags=_NO_WINDOW)
        changes = len([ln for ln in s.stdout.splitlines() if ln.strip()])
        return {"branch": b.stdout.strip(), "changes": changes}
    except Exception:  # noqa: BLE001
        return None


def _docker():
    try:
        r = subprocess.run(["docker", "ps", "-q"],
                           capture_output=True, text=True, timeout=3,
                           creationflags=_NO_WINDOW)
        if r.returncode != 0:
            return None   # daemon apagado
        return {"running": len([ln for ln in r.stdout.splitlines() if ln.strip()])}
    except Exception:  # noqa: BLE001
        return None


def _weather():
    cfg = plugin_settings("indicators")
    if not cfg.get("weather_enabled", True):
        return None
    loc = urllib.parse.quote(cfg.get("weather_location") or "")
    try:
        url = f"https://wttr.in/{loc}?format=%l|%t|%C"
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8"})
        with urllib.request.urlopen(req, timeout=6) as r:
            out = r.read().decode().strip()
        city, temp, desc = (out.split("|", 2) + ["", "", ""])[:3]
        return {"city": city, "temp": temp, "desc": desc}
    except Exception:  # noqa: BLE001
        return None


def _net():
    io = psutil.net_io_counters()
    now = time.time()
    prev = _c["net"]
    _c["net"] = (io.bytes_recv, io.bytes_sent, now)
    if not prev:
        return {"down": 0, "up": 0}
    dt = max(0.2, now - prev[2])
    return {"down": round((io.bytes_recv - prev[0]) / dt / 1024),
            "up": round((io.bytes_sent - prev[1]) / dt / 1024)}


@action("indicators_get", state=True)
def indicators_get(params: dict):
    now = time.time()
    d = _c["data"]
    d["net"] = _net()
    if now - _c["git_t"] > 4:
        d["git"] = _git()
        _c["git_t"] = now
    if now - _c["docker_t"] > 6:
        d["docker"] = _docker()
        _c["docker_t"] = now
    if now - _c["weather_t"] > 600 or "weather" not in d:
        w = _weather()
        if w:
            d["weather"] = w
        _c["weather_t"] = now
    return {"state": {"indicators": dict(d)}}
