# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Now Playing para macOS (vía AppleScript).

En Windows se usa la sesión multimedia global (SMTC, ver media_session.py).
macOS 15.4+ bloqueó el "Now Playing" global del sistema (framework privado
MediaRemote) para apps no firmadas por Apple, así que aquí leemos cada
reproductor por separado con AppleScript:

  - Apple Music (Music.app)  → metadatos + posición + control completos
  - Spotify                  → metadatos + posición + control completos
  - Navegador (YouTube, YouTube Music, Amazon Music web...) → SOLO título de
    la pestaña activa (macOS no permite leer posición ni controlar la
    reproducción de una web desde fuera del navegador).

Requiere permiso de Automatización: la primera vez macOS preguntará si la app
(Terminal/VS Code) puede controlar Music, Spotify o el navegador. Acepta.
"""
import subprocess
import sys

from . import action

# Este módulo es solo para macOS; en otros sistemas no se registra.
if sys.platform != "darwin":
    raise ImportError("media_mac solo aplica a macOS")

# Navegadores basados en Chromium (misma sintaxis AppleScript) y Safari aparte.
_CHROMIUM = ["Google Chrome", "Brave Browser", "Microsoft Edge",
             "Arc", "Vivaldi", "Chromium", "Opera"]

# Sufijos de título de pestaña que delatan reproducción web, con su plataforma.
# SOLO servicios de música dedicados: cuando reproducen, el título de la pestaña
# lleva "Canción | YouTube Music"; en pausa/inactivo baja a solo "YouTube Music"
# (que descartamos). Así evitamos falsos positivos de pestañas de YouTube normal
# abiertas que no están sonando (macOS no permite saber qué pestaña emite audio).
_WEB_MATCHERS = [
    (" - YouTube Music", "YouTube Music", 0),
    (" | YouTube Music", "YouTube Music", 0),
    (" - Amazon Music", "Amazon Music", 0),
    (" | Amazon Music", "Amazon Music", 0),
    (" • Spotify", "Spotify", 0),
    (" - Spotify", "Spotify", 0),
    (" | Spotify", "Spotify", 0),
    (" - SoundCloud", "SoundCloud", 0),
    (" | SoundCloud", "SoundCloud", 0),
    # YouTube normal (vídeos): prioridad baja, la música dedicada gana.
    (" - YouTube", "YouTube", 5),
    (" | YouTube", "YouTube", 5),
]


def _osa(script: str) -> str:
    """Ejecuta un AppleScript y devuelve stdout sin saltos de línea finales."""
    try:
        out = subprocess.run(["osascript", "-e", script],
                             capture_output=True, text=True, timeout=4)
        return (out.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def _running_apps() -> set:
    """Nombres de proceso de las apps abiertas ahora mismo (vía `ps`, rápido).
    Evita lanzar un osascript por cada reproductor/navegador que ni existe."""
    try:
        out = subprocess.run(["ps", "-Axco", "comm"],
                             capture_output=True, text=True, timeout=3)
        return {ln.strip() for ln in out.stdout.splitlines() if ln.strip()}
    except Exception:  # noqa: BLE001
        return set()


# --- lectura de reproductores nativos (Music / Spotify) --------------------

_PLAYER_SNAPSHOT = '''
try
  if application "%s" is running then
    tell application "%s"
      set ps to (player state as text)
      if ps is "playing" or ps is "paused" then
        set nm to name of current track
        set ar to artist of current track
        set pp to (player position as text)
        set dd to (%s as text)
        return "%s" & "|||" & nm & "|||" & ar & "|||" & ps & "|||" & pp & "|||" & dd
      end if
    end tell
  end if
end try
return ""
'''


def _read_player(app: str, duration_expr: str, source: str):
    script = _PLAYER_SNAPSHOT % (app, app, duration_expr, source)
    raw = _osa(script)
    if not raw or raw.count("|||") < 5:
        return None
    src, title, artist, status, pos, dur = raw.split("|||", 5)
    try:
        position = float(pos)
    except ValueError:
        position = 0.0
    try:
        duration = float(dur)
    except ValueError:
        duration = 0.0
    np = {
        "active": True,
        "source": src,
        "title": title,
        "artist": artist,
        "status": "playing" if status == "playing" else "paused",
        "position": round(position, 2),
        "duration": int(duration),
        "thumbId": None,
    }
    if src == "Spotify":                     # Spotify expone la URL de la carátula
        art = _osa('tell application "Spotify" to get artwork url of current track')
        if art.startswith("http"):
            np["artwork"] = art
    return np


# --- lectura del navegador (solo título) -----------------------------------

import re

_COUNT_PREFIX = re.compile(r"^\(\d+\)\s*")  # "(310) " que YouTube añade al título


def _match_web_title(title: str):
    """Si el título es de una web multimedia, devuelve (título limpio,
    plataforma, prioridad). Si no, None."""
    for suf, platform, prio in _WEB_MATCHERS:
        if title.endswith(suf):
            clean = _COUNT_PREFIX.sub("", title[: -len(suf)].strip())
            if clean:  # descartar la pestaña inactiva (solo "YouTube Music")
                return clean, platform, prio
    return None


def _browser_tabs(app: str, is_safari: bool = False):
    """(ventana, pestaña, título) de todas las pestañas. Índices 1-based.
    La música suele estar en una pestaña de fondo, no en la activa."""
    prop = "name" if is_safari else "title"
    raw = _osa(f'''
        try
          tell application "{app}"
            set out to ""
            set wi to 0
            repeat with w in windows
              set wi to wi + 1
              set ti to 0
              repeat with t in tabs of w
                set ti to ti + 1
                set out to out & wi & ":::" & ti & ":::" & ({prop} of t) & linefeed
              end repeat
            end repeat
            return out
          end tell
        end try
        return ""''')
    tabs = []
    for ln in raw.splitlines():
        parts = ln.split(":::", 2)
        if len(parts) == 3:
            try:
                tabs.append((int(parts[0]), int(parts[1]), parts[2]))
            except ValueError:
                pass
    return tabs


def _find_browser_media(running: set):
    """Localiza la pestaña de música/vídeo de mayor prioridad (música gana a
    YouTube genérico). Devuelve {app, is_safari, win, tab, title, platform}."""
    browsers = [(a, False) for a in _CHROMIUM if a in running]
    if "Safari" in running:
        browsers.append(("Safari", True))

    best = None  # (prioridad, app, is_safari, win, tab, título, plataforma)
    for app, is_safari in browsers:
        for win, tab, raw in _browser_tabs(app, is_safari):
            m = _match_web_title(raw)
            if m and (best is None or m[2] < best[0]):
                best = (m[2], app, is_safari, win, tab, m[0], m[1])
        if best and best[0] == 0:
            break

    if best is None:
        return None
    _, app, is_safari, win, tab, title, platform = best
    return {"app": app, "is_safari": is_safari, "win": win, "tab": tab,
            "title": title, "platform": platform}


# JavaScript inyectado en la pestaña para leer/controlar el <video>/<audio>.
# Requiere activar "Permitir JavaScript desde Apple Events" en el navegador.
# Solo comillas simples (van dentro de una cadena AppleScript de comillas dobles).
_JS_READ = (
    "(function(){var v=document.querySelector('video')||document.querySelector('audio');"
    "if(!v||!v.duration)return 'NONE';"
    "var m=navigator.mediaSession&&navigator.mediaSession.metadata;var art='';"
    "if(m&&m.artwork&&m.artwork.length)art=m.artwork[m.artwork.length-1].src;"
    "return JSON.stringify({t:v.currentTime,d:v.duration,p:v.paused,art:art,"
    "ti:(m&&m.title)||'',ar:(m&&m.artist)||''});})()")
_JS_PLAYPAUSE = ("(function(){var v=document.querySelector('video')||"
                 "document.querySelector('audio');if(!v)return 'no';"
                 "if(v.paused)v.play();else v.pause();return 'ok';})()")
_JS_NEXT = ("(function(){var s=['.next-button','.ytp-next-button'];"
            "for(var i=0;i<s.length;i++){var e=document.querySelector(s[i]);"
            "if(e){e.click();return 'ok';}}return 'no';})()")
_JS_PREV = ("(function(){var s=['.previous-button','.ytp-prev-button'];"
            "for(var i=0;i<s.length;i++){var e=document.querySelector(s[i]);"
            "if(e){e.click();return 'ok';}}return 'no';})()")


def _js(app: str, win: int, tab: int, js: str):
    """Ejecuta JS en una pestaña Chromium. Devuelve (ok, valor)."""
    script = (f'tell application "{app}" to execute tab {tab} of window {win} '
              f'javascript "{js}"')
    try:
        out = subprocess.run(["osascript", "-e", script],
                             capture_output=True, text=True, timeout=4)
        if out.returncode != 0:
            return False, (out.stderr or "").strip()
        return True, (out.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return False, ""


def _read_browser(running: set):
    """Localiza la pestaña de música/vídeo y, si el navegador permite JS desde
    Apple Events, lee posición/duración/estado reales del <video>."""
    media = _find_browser_media(running)
    if media is None:
        return None
    np = {"active": True, "source": media["app"], "title": media["title"],
          "artist": media["platform"], "status": "playing",
          "position": 0, "duration": 0, "thumbId": None}
    if not media["is_safari"]:
        ok, val = _js(media["app"], media["win"], media["tab"], _JS_READ)
        if ok and val and val != "NONE":
            try:
                import json
                d = json.loads(val)
                np["position"] = round(float(d.get("t", 0)), 2)
                np["duration"] = int(float(d.get("d", 0)))
                np["status"] = "paused" if d.get("p") else "playing"
                if d.get("art"):
                    np["artwork"] = d["art"]           # carátula del vídeo/tema
                if d.get("ti"):                        # metadatos mediaSession
                    np["title"] = d["ti"]
                    np["artist"] = d.get("ar") or media["platform"]
            except (ValueError, KeyError):
                pass
    return np


def _snapshot():
    """Estado actual, probando fuentes por orden de fiabilidad.
    Solo consulta apps que estén realmente abiertas."""
    running = _running_apps()
    np = None
    if "Music" in running:
        np = _read_player("Music", "duration of current track", "Music")
    if np is None and "Spotify" in running:
        np = _read_player("Spotify", "(duration of current track) / 1000", "Spotify")
    if np is None:
        np = _read_browser(running)
    if np is None:
        return {"nowplaying": {"active": False}}
    return {"nowplaying": np}


# Teclas multimedia del sistema (las mismas que usa el Dock/teclado). Controlan
# la sesión de audio activa del sistema, incluido el navegador (YouTube, etc.).
NX_KEYTYPE_PLAY = 16
NX_KEYTYPE_NEXT = 17
NX_KEYTYPE_PREVIOUS = 18


def _media_key(key_code: int) -> bool:
    """Envía una tecla multimedia (play/pausa, siguiente, anterior) al sistema.
    Requiere PyObjC (viene en el venv) y permiso de Accesibilidad."""
    try:
        import Quartz
        from AppKit import NSEvent
    except Exception:  # noqa: BLE001
        return False
    try:
        for down in (True, False):
            data1 = (key_code << 16) | ((0xA if down else 0xB) << 8)
            ev = NSEvent.otherEventWithType_location_modifierFlags_timestamp_windowNumber_context_subtype_data1_data2_(  # noqa: E501
                14,               # NSSystemDefined
                (0, 0), 0xA00 if down else 0xB00, 0, 0, None,
                8, data1, -1)
            Quartz.CGEventPost(0, ev.CGEvent())
        return True
    except Exception:  # noqa: BLE001
        return False


def _active_source():
    """Fuente que suena ahora: 'Music', 'Spotify', nombre de navegador o None."""
    snap = _snapshot()["nowplaying"]
    return snap.get("source") if snap.get("active") else None


# --- acciones registradas ---------------------------------------------------

@action("now_playing_get")
def now_playing_get(params: dict):
    """Estado de la reproducción actual, sin cambiar nada. params: {}"""
    return {"state": _snapshot()}


@action("now_playing", schema={"cmd": {"type": "str", "choices": ["play_pause", "next", "previous", "seek"]}, "position": {"type": "float", "min": 0}})
def now_playing(params: dict):
    """Controla la reproducción.
    params: {"cmd": "play_pause" | "next" | "previous" | "seek", "position": 90}

    - Music / Spotify: control completo por AppleScript (incluida la barra).
    - Navegador (YouTube, etc.): play/pausa, siguiente y anterior vía teclas
      multimedia del sistema. La barra (seek) no es posible en el navegador.
    """
    cmd = params.get("cmd", "play_pause")
    app = _active_source()
    if app is None:
        return {"message": "Nada sonando", "state": _snapshot()}

    if app in ("Music", "Spotify"):
        if cmd == "play_pause":
            _osa(f'tell application "{app}" to playpause')
        elif cmd == "next":
            _osa(f'tell application "{app}" to next track')
        elif cmd == "previous":
            _osa(f'tell application "{app}" to previous track')
        elif cmd == "seek":
            pos = float(params.get("position", 0))
            _osa(f'tell application "{app}" to set player position to {pos}')
        else:
            raise ValueError(f"cmd inválido: '{cmd}'")
        return {"state": _snapshot()}

    return _browser_control(cmd, params)


def _browser_control(cmd: str, params: dict):
    """Control del navegador. Prefiere JavaScript (play/pausa, barra y
    siguiente/anterior por pestaña); si el navegador no permite JS desde Apple
    Events, cae a las teclas multimedia del sistema (sin barra)."""
    media = _find_browser_media(_running_apps())
    if media is None:
        return {"message": "Nada sonando en el navegador", "state": _snapshot()}

    # 1) Vía JavaScript (la mejor: por pestaña y con barra)
    if not media["is_safari"]:
        js = None
        if cmd == "play_pause":
            js = _JS_PLAYPAUSE
        elif cmd == "next":
            js = _JS_NEXT
        elif cmd == "previous":
            js = _JS_PREV
        elif cmd == "seek":
            pos = float(params.get("position", 0))
            js = ("(function(){var v=document.querySelector('video')||"
                  "document.querySelector('audio');if(!v)return 'no';"
                  f"v.currentTime={pos};return 'ok';}})()")
        if js is not None:
            ok, val = _js(media["app"], media["win"], media["tab"], js)
            if ok and val == "ok":
                return {"state": _snapshot()}

    # 2) Fallback: teclas multimedia (no sirven para la barra)
    if cmd == "seek":
        return {"message": "Para mover la barra en el navegador activa "
                           "'Permitir JavaScript desde Apple Events' en el navegador",
                "state": _snapshot()}
    key = {"play_pause": NX_KEYTYPE_PLAY, "next": NX_KEYTYPE_NEXT,
           "previous": NX_KEYTYPE_PREVIOUS}.get(cmd)
    if key is None:
        raise ValueError(f"cmd inválido: '{cmd}'")
    if not _media_key(key):
        return {"message": "No se pudo controlar (¿permiso de Accesibilidad?)",
                "state": _snapshot()}
    return {"message": "Enviado al navegador", "state": _snapshot()}


@action("lyrics_get")
def lyrics_get(params: dict):
    """Busca la letra de la canción actual (o de title/artist dados) en
    lrclib.net. params: {} o {"title": "...", "artist": "..."}"""
    import json
    import urllib.parse
    import urllib.request

    title = params.get("title")
    artist = params.get("artist")
    if not title:
        snap = _snapshot()["nowplaying"]
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
