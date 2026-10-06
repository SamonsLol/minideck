# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Now Playing: lee y controla lo que suena en el PC (YT Music en el
navegador, Spotify, etc.) vía SMTC de Windows. Requiere: pip install winsdk

Funciona con cualquier reproductor que publique su sesión multimedia en
Windows — Chrome/Edge lo hacen automáticamente con YT Music, YouTube, etc.
"""
import asyncio
import datetime as _dt
import json
import sys
import urllib.parse
import urllib.request

if sys.platform != "win32":
    raise ImportError("media_session solo aplica a Windows")

import winsdk.windows.media.control as wmc
from winsdk.windows.storage.streams import Buffer, DataReader, InputStreamOptions

from . import action

_STATUS = {4: "playing", 5: "paused"}

# Caché de carátula: se sirve por HTTP en /api/artwork (ver main.py).
# Al cambiar de canción se espera un sondeo antes de leer (el navegador
# puede tener aún la imagen anterior) y se reintenta hasta conseguirla.
_thumb = {"key": None, "data": None, "tries": 0}


def get_thumb_bytes():
    """Bytes JPEG de la carátula actual, o None. Usado por main.py."""
    return _thumb["data"]


def _run(coro):
    """Las APIs de winsdk son async; cada acción corre en su propio hilo,
    así que abrimos un event loop propio por llamada."""
    return asyncio.run(coro)


async def _get_session():
    mgr = await wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
    return mgr.get_current_session()


import logging

log = logging.getLogger("minideck.nowplaying")


async def _read_thumb(props):
    ref = props.thumbnail
    if ref is None:
        raise RuntimeError("el reproductor no publica carátula (thumbnail=None)")
    stream = await ref.open_read_async()
    size = int(stream.size)
    if size == 0:
        raise RuntimeError("carátula vacía (0 bytes)")
    if size > 1_000_000:
        raise RuntimeError(f"carátula demasiado grande ({size} bytes)")
    buf = Buffer(size)
    await stream.read_async(buf, size, InputStreamOptions.READ_AHEAD)

    # La API para extraer bytes cambia entre versiones de winsdk:
    # 1) el Buffer soporta el protocolo buffer de Python directamente
    try:
        data = bytes(buf)
        if data:
            return data
    except TypeError:
        pass
    # 2) DataReader.read_bytes(n) devuelve la lista de bytes
    reader = DataReader.from_buffer(buf)
    try:
        out = reader.read_bytes(size)
        if out is not None:
            return bytes(bytearray(out))
    except TypeError:
        pass
    # 3) DataReader.read_bytes(bytearray) rellena el buffer que le pasas
    data = bytearray(size)
    reader.read_bytes(data)
    return bytes(data)


async def _refresh_thumb(props, key):
    if key != _thumb["key"]:
        # canción nueva: invalidar y esperar al siguiente sondeo para leer,
        # así no capturamos la carátula de la canción anterior
        _thumb.update(key=key, data=None, tries=0)
        return
    if _thumb["data"] is None and _thumb["tries"] < 10:
        _thumb["tries"] += 1
        try:
            data = await _read_thumb(props)
            if data:
                _thumb["data"] = data
                log.info("Carátula cargada (%d bytes) en el intento %d",
                         len(data), _thumb["tries"])
        except Exception as exc:  # noqa: BLE001
            if _thumb["tries"] in (1, 5, 10):
                log.warning("Carátula: fallo en intento %d: %s",
                            _thumb["tries"], exc)


async def _snapshot():
    """Estado actual: {"nowplaying": {...}}. La carátula se cachea y el
    cliente la pide por HTTP cuando cambia thumbId."""
    s = await _get_session()
    if s is None:
        _thumb.update(key=None, data=None, tries=0)
        return {"nowplaying": {"active": False}}

    props = await s.try_get_media_properties_async()
    tl = s.get_timeline_properties()
    info = s.get_playback_info()
    status = _STATUS.get(int(info.playback_status), "stopped")

    # Chrome/Edge NO actualizan la posición continuamente: la reportan solo
    # en eventos (play/pausa/seek) junto con last_updated_time. La posición
    # real ahora = posición reportada + tiempo transcurrido desde entonces.
    pos = tl.position.total_seconds()
    dur = tl.end_time.total_seconds()
    if status == "playing":
        try:
            elapsed = (_dt.datetime.now(_dt.timezone.utc)
                       - tl.last_updated_time).total_seconds()
            if 0 < elapsed < 7200:  # descartar marcas absurdas
                pos += elapsed
        except Exception:  # noqa: BLE001
            pass
    if dur > 0:
        pos = min(pos, dur)

    key = f"{props.title}|{props.artist}"
    await _refresh_thumb(props, key)

    np = {
        "active": True,
        "title": props.title or "",
        "artist": props.artist or "",
        "status": status,
        "position": round(pos, 2),   # decimales: evita hasta 1s de desfase
        "duration": int(dur),
        "thumbId": key if _thumb["data"] else None,
    }
    return {"nowplaying": np}


@action("now_playing_get")
def now_playing_get(params: dict):
    """Estado de la reproducción actual, sin cambiar nada. params: {}"""
    return {"state": _run(_snapshot())}


@action("now_playing")
def now_playing(params: dict):
    """Controla la sesión multimedia activa.
    params: {"cmd": "play_pause" | "next" | "previous" | "seek", "position": 90}
    (position en segundos, solo para seek)
    """
    cmd = params.get("cmd", "play_pause")

    async def go():
        s = await _get_session()
        if s is None:
            raise RuntimeError("No hay nada reproduciéndose")
        if cmd == "play_pause":
            await s.try_toggle_play_pause_async()
        elif cmd == "next":
            await s.try_skip_next_async()
        elif cmd == "previous":
            await s.try_skip_previous_async()
        elif cmd == "seek":
            ticks = int(float(params.get("position", 0)) * 10_000_000)
            await s.try_change_playback_position_async(ticks)
        else:
            raise ValueError(f"cmd inválido: '{cmd}'")
        await asyncio.sleep(0.15)  # dar tiempo a que el estado se refleje
        return await _snapshot()

    return {"state": _run(go())}


@action("lyrics_get")
def lyrics_get(params: dict):
    """Busca la letra de la canción actual (o de title/artist dados) en
    lrclib.net, una base de datos de letras abierta y gratuita.
    params: {} o {"title": "...", "artist": "..."}
    """
    title = params.get("title")
    artist = params.get("artist")
    if not title:
        snap = _run(_snapshot())["nowplaying"]
        if not snap.get("active"):
            return {"message": "No hay nada reproduciéndose"}
        title, artist = snap.get("title"), snap.get("artist")

    q = urllib.parse.urlencode({"track_name": title, "artist_name": artist or ""})
    try:
        req = urllib.request.Request(
            f"https://lrclib.net/api/get?{q}",
            headers={"User-Agent": "MiniDeck/1.0"})
        with urllib.request.urlopen(req, timeout=6) as r:
            data = json.loads(r.read().decode())
        lyrics = data.get("plainLyrics")
        synced = data.get("syncedLyrics")
    except Exception:  # noqa: BLE001
        lyrics = synced = None

    if not lyrics and not synced:
        return {"message": f"Letra no encontrada para: {title}"}
    return {"lyrics": lyrics, "syncedLyrics": synced,
            "lyricsTitle": f"{title} — {artist or ''}".strip(" —")}
