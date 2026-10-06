# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""
Modo básico: MiniDeck SIN JavaScript.

Todo funciona con enlaces y formularios HTML renderizados en el servidor:
emparejar, usar el deck (botones, carpetas, pulsación larga como segundo
botón, sliders, mezclador, Now Playing, OBS, Home Assistant…) y editarlo.
La app con JavaScript (/) es una mejora sobre esto; sin JS, / redirige aquí.

Seguridad sin JS:
  - el token viaja en una cookie HttpOnly + SameSite=Strict (los formularios
    no pueden enviar cabeceras); ?token= del QR la crea y se quita de la URL.
  - los POST exigen el mismo origen (anti-CSRF), además de SameSite.

Las funciones del servidor (cargar/guardar config, ejecutar acciones, estado)
se inyectan con configure() para no importar main (evita ciclos).
"""
import html
import json
import time
from urllib.parse import parse_qs, quote, urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

import auth
from version import LICENSE, SOURCE_URL, __version__

router = APIRouter()
COOKIE = auth.COOKIE
THEME_COOKIE = "minideck_theme"
LANG_COOKIE = "minideck_lang"
_YEAR = 365 * 24 * 3600
_srv: dict = {}


def configure(**funcs) -> None:
    """load_config, save_config, validate_config, run_action, collect_state,
    restore_backup, list_actions, plugin_widget_types."""
    _srv.update(funcs)


# ------------------------------------------------------------------ textos ---
_T = {
    "es": {
        "pair.title": "Emparejar MiniDeck", "pair.help":
        "En el equipo abre {url} y escribe aquí el código que aparece bajo el QR "
        "(o escanea el QR con la cámara del móvil).",
        "pair.code": "Código", "pair.go": "Emparejar",
        "pair.bad": "Ese código no es válido para este equipo.",
        "refresh": "Actualizar", "edit": "Editar", "theme": "Tema", "full": "Versión completa",
        "done": "Hecho", "error": "Error", "long": "Mantener", "back": "Volver",
        "needs_js": "Este widget necesita JavaScript.", "ok": "OK", "nothing": "Nada sonando",
        "mute": "Silenciar", "deaf": "Sordina", "connected": "conectado",
        "disconnected": "desconectado", "no_audio": "Sin audio activo",
        "ed.title": "Editar deck", "ed.page": "Página", "ed.edit": "Editar",
        "ed.up": "Subir", "ed.down": "Bajar", "ed.del": "Eliminar", "ed.add": "Añadir botón",
        "ed.addpage": "Nueva página", "ed.rename": "Renombrar", "ed.delpage": "Eliminar página",
        "ed.undo": "Deshacer último cambio", "ed.export": "Exportar deck",
        "ed.import": "Importar deck (pega el JSON)", "ed.save": "Guardar",
        "ed.name": "Nombre", "ed.icon": "Icono", "ed.color": "Color", "ed.type": "Tipo",
        "ed.action": "Acción", "ed.params": "Parámetros (JSON)", "ed.longaction":
        "Pulsación larga (acción, opcional)", "ed.longparams": "Parámetros de la pulsación larga",
        "ed.when": "Estado del botón (JSON, opcional)", "ed.w": "Ancho", "ed.h": "Alto",
        "ed.cancel": "Cancelar", "ed.view": "Ver deck", "ed.new": "Nuevo",
        "ed.confirm_page": "Se eliminará la página y todos sus botones.",
        "saved": "Guardado ✓", "badjson": "JSON inválido en «{f}»: {e}",
        "lang": "English",
        "ed.advanced": "Avanzado (JSON)", "ed.default": "— por defecto —",
        "ed.yes": "Sí", "ed.no": "No", "ed.lines": "uno por línea",
        "ed.newaction": "Pulsa Guardar para ver los campos de la acción elegida.",
        "ed.wkey": "Dato en vivo (p. ej. obs.recording)", "ed.wequals": "Cuando valga (opcional)",
        "ed.wlabel": "Texto cuando esté activo", "ed.wicon": "Icono cuando esté activo",
        "ed.wcolor": "Usar este color cuando esté activo", "ed.back": "← Volver a la página anterior",
    },
    "en": {
        "pair.title": "Pair MiniDeck", "pair.help":
        "On the computer open {url} and type here the code shown under the QR code "
        "(or scan the QR code with your phone's camera).",
        "pair.code": "Code", "pair.go": "Pair",
        "pair.bad": "That code isn't valid for this computer.",
        "refresh": "Refresh", "edit": "Edit", "theme": "Theme", "full": "Full version",
        "done": "Done", "error": "Error", "long": "Hold", "back": "Back",
        "needs_js": "This widget needs JavaScript.", "ok": "OK", "nothing": "Nothing playing",
        "mute": "Mute", "deaf": "Deafen", "connected": "connected",
        "disconnected": "disconnected", "no_audio": "No active audio",
        "ed.title": "Edit deck", "ed.page": "Page", "ed.edit": "Edit",
        "ed.up": "Up", "ed.down": "Down", "ed.del": "Delete", "ed.add": "Add button",
        "ed.addpage": "New page", "ed.rename": "Rename", "ed.delpage": "Delete page",
        "ed.undo": "Undo last change", "ed.export": "Export deck",
        "ed.import": "Import deck (paste the JSON)", "ed.save": "Save",
        "ed.name": "Name", "ed.icon": "Icon", "ed.color": "Color", "ed.type": "Type",
        "ed.action": "Action", "ed.params": "Parameters (JSON)", "ed.longaction":
        "Long press (action, optional)", "ed.longparams": "Long-press parameters",
        "ed.when": "Button state (JSON, optional)", "ed.w": "Width", "ed.h": "Height",
        "ed.cancel": "Cancel", "ed.view": "View deck", "ed.new": "New",
        "ed.confirm_page": "The page and all its buttons will be deleted.",
        "saved": "Saved ✓", "badjson": "Invalid JSON in “{f}”: {e}",
        "lang": "Español",
        "ed.advanced": "Advanced (JSON)", "ed.default": "— default —",
        "ed.yes": "Yes", "ed.no": "No", "ed.lines": "one per line",
        "ed.newaction": "Press Save to see the fields of the selected action.",
        "ed.wkey": "Live value (e.g. obs.recording)", "ed.wequals": "When it equals (optional)",
        "ed.wlabel": "Text while active", "ed.wicon": "Icon while active",
        "ed.wcolor": "Use this color while active", "ed.back": "← Back to the previous page",
    },
}


_PARAM_LABELS = {
    "es": {"keys": "Teclas", "text": "Texto", "path": "Ruta (archivo o carpeta)",
           "app": "Aplicación", "args": "Argumentos", "cmd": "Comando", "shell": "Consola",
           "url": "Dirección web", "level": "Volumen", "delta": "Cuánto sube o baja",
           "mute": "Silenciar", "mode": "Modo", "delay_s": "Retraso (segundos)", "name": "Nombre",
           "x": "Posición X", "y": "Posición Y", "clicks": "Clics", "button": "Botón del ratón",
           "steps": "Pasos", "method": "Método", "scene": "Escena", "input": "Fuente de audio",
           "entity_id": "Entidad", "domain": "Dominio", "service": "Servicio", "page": "Página",
           "position": "Posición (segundos)"},
    "en": {"keys": "Keys", "text": "Text", "path": "Path (file or folder)", "app": "App",
           "args": "Arguments", "cmd": "Command", "shell": "Shell", "url": "Web address",
           "level": "Volume", "delta": "Step up/down", "mute": "Mute", "mode": "Mode",
           "delay_s": "Delay (seconds)", "name": "Name", "x": "X position", "y": "Y position",
           "clicks": "Clicks", "button": "Mouse button", "steps": "Steps", "method": "Method",
           "scene": "Scene", "input": "Audio source", "entity_id": "Entity", "domain": "Domain",
           "service": "Service", "page": "Page", "position": "Position (seconds)"},
}


def _lang(req: Request) -> str:
    c = req.cookies.get(LANG_COOKIE)
    if c in _T:
        return c
    al = (req.headers.get("accept-language") or "").lower()
    return "es" if al.startswith("es") else "en"


def _t(req, key, **kw):
    s = _T[_lang(req)].get(key) or _T["es"].get(key, key)
    for k, v in kw.items():
        s = s.replace("{" + k + "}", str(v))
    return s


e = html.escape


# ------------------------------------------------------------------- auth ---
def authed(req: Request) -> bool:
    return auth.check(req.cookies.get(COOKIE))


def set_token_cookie(resp: Response, token: str) -> None:
    resp.set_cookie(COOKIE, token, max_age=_YEAR, httponly=True, samesite="strict", path="/")


def _post_ok(req: Request) -> bool:
    """Anti-CSRF: Origin (si lo hay) del mismo host. SameSite=Strict ya impide
    que otra web envíe la cookie; esto es una segunda barrera."""
    return auth.same_origin(req.headers)


async def _form(req: Request) -> dict:
    """application/x-www-form-urlencoded sin dependencias extra."""
    body = (await req.body()).decode("utf-8", errors="replace")
    return {k: v[-1] for k, v in parse_qs(body, keep_blank_values=True).items()}


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _back(page: str = "", msg: str = "", ok: bool = True, base: str = "/basic", **extra):
    q = {k: v for k, v in {"page": page, "msg": msg, "ok": "1" if ok else "0",
                           **extra}.items() if v}
    if not msg:
        q.pop("ok", None)
    return _redirect(base + ("?" + urlencode(q) if q else ""))


# ----------------------------------------------------------------- helpers ---
def _icon(icon: str, color: str) -> str:
    icon = icon or ""
    if icon.startswith("img:"):
        src = icon[4:]
        src = src if src.startswith(("http://", "https://")) else f"/icons/{src}"
        return f'<img src="{e(src)}" alt="">'
    if ":" in icon and icon.replace(":", "").replace("-", "").isalnum() and icon.islower():
        pack, name = icon.split(":", 1)
        return (f'<img src="/iconify/{e(pack)}/{e(name)}.svg?color={quote(color or "#c9d1dd")}"'
                ' alt="">')
    return f"<span>{e(icon or '●')}</span>"


def state_path(obj, path: str):
    """Igual que statePath() del cliente: admite claves con puntos."""
    parts = str(path).split(".")
    cur, i = obj, 0
    while i < len(parts):
        if not isinstance(cur, dict):
            return None
        for j in range(len(parts), i, -1):
            k = ".".join(parts[i:j])
            if k in cur:
                cur, i = cur[k], j
                break
        else:
            return None
    return cur


def when_active(when: dict, state: dict) -> bool:
    v = state_path(state, when.get("key", ""))
    if "equals" in when:
        return str(v).lower() == str(when["equals"]).lower()
    return bool(v) and v not in ("off", "unavailable")


def _coerce(v: str):
    """Valor de un campo de formulario → tipo JSON razonable."""
    s = v.strip()
    if s in ("true", "false"):
        return s == "true"
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        pass
    if s[:1] in "[{":
        try:
            return json.loads(s)
        except ValueError:
            pass
    return v


def _page(cfg, pid):
    pages = cfg.get("pages") or []
    return next((p for p in pages if p.get("id") == pid), pages[0] if pages else None)


def _shell(req: Request, title: str, body: str, *, theme_back: str = "/basic") -> HTMLResponse:
    theme = req.cookies.get(THEME_COOKIE, "")
    lang = _lang(req)
    th = f' data-theme="{e(theme)}"' if theme in ("lcd",) else ""
    page = f"""<!doctype html>
<html lang="{lang}"{th}><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark light">
<title>{e(title)}</title>
<link rel="icon" href="/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="stylesheet" href="/basic.css?v={__version__}">
</head><body>{body}
<footer class="b-foot">MiniDeck {__version__} · {e(LICENSE)} ·
<a href="{e(SOURCE_URL)}">source</a></footer>
</body></html>"""
    return HTMLResponse(page, headers={"Cache-Control": "no-store"})


def _topbar(req: Request, page_id: str, editing=False) -> str:
    here = "/basic/edit" if editing else "/basic"
    pq = f"?page={quote(page_id)}" if page_id else ""
    other = (f'<a class="b-btn" href="/basic{pq}">▦ {e(_t(req, "ed.view"))}</a>' if editing
             else f'<a class="b-btn" href="/basic/edit{pq}">✎ {e(_t(req, "edit"))}</a>')
    return f"""<header class="b-top">
  <a class="b-brand" href="/basic"><img src="/icons/icon-192.png" alt="" width="28" height="28">
    MiniDeck</a>
  <nav class="b-tools">
    <a class="b-btn" href="{here}{pq}">↻ {e(_t(req, "refresh"))}</a>
    {other}
    <form method="post" action="/basic/prefs"><input type="hidden" name="back" value="{e(here + pq)}">
      <button class="b-btn" name="toggle" value="theme">◑ {e(_t(req, "theme"))}</button>
      <button class="b-btn" name="toggle" value="lang">{e(_t(req, "lang"))}</button></form>
    <a class="b-btn" href="/?full=1">⚡ {e(_t(req, "full"))}</a>
  </nav></header>"""


def _tabs(cfg, current, base="/basic") -> str:
    out = []
    for p in cfg.get("pages") or []:
        cls = "b-tab on" if p["id"] == current else "b-tab"
        out.append(f'<a class="{cls}" href="{base}?page={quote(p["id"])}">'
                   f'{e(p.get("name") or p["id"])}</a>')
    return f'<nav class="b-tabs">{"".join(out)}</nav>'


def _flash(req: Request) -> str:
    msg = req.query_params.get("msg")
    if not msg:
        return ""
    ok = req.query_params.get("ok") == "1"
    return f'<p class="b-flash {"ok" if ok else "err"}" role="status">{e(msg)}</p>'


def _span(btn) -> str:
    st = []
    if btn.get("w") == "full":
        st.append("grid-column:1/-1")
    elif btn.get("w"):
        st.append(f"grid-column:span {int(btn['w'])}")
    if btn.get("h"):
        st.append(f"grid-row:span {int(btn['h'])}")
    return ";".join(st)


def _run_form(page_id, action, params, label, cls="b-mini", extra="") -> str:
    """Formulario de una acción con params fijos (botones de widgets)."""
    fields = "".join(f'<input type="hidden" name="p_{e(k)}" value="{e(json.dumps(v) if not isinstance(v, str) else v)}">'
                     for k, v in (params or {}).items())
    return (f'<form method="post" action="/basic/run" class="b-inline">'
            f'<input type="hidden" name="page" value="{e(page_id)}">'
            f'<input type="hidden" name="action" value="{e(action)}">{fields}'
            f'<button class="{cls}"{extra}>{label}</button></form>')


# ------------------------------------------------------------ widgets HTML ---
def _w_key(req, btn, page_id, state, origin) -> str:
    when = btn.get("when") or {}
    on = bool(when.get("key")) and when_active(when, state)
    color = (when.get("color") if on else None) or btn.get("color") or "#8a93a3"
    icon = (when.get("icon") if on else None) or btn.get("icon")
    label = (when.get("label") if on else None) or btn.get("label") or ""
    style = f'--led:{e(color)};{_span(btn)}'
    inner = f'<span class="b-ic">{_icon(icon, color)}</span><span class="b-lb">{e(label)}</span>'
    if btn.get("action") == "page":
        target = (btn.get("params") or {}).get("page", "")
        href = (f"/basic?page={quote(origin)}" if target == "back" and origin
                else f"/basic?page={quote(target)}&from={quote(page_id)}")
        return f'<a class="b-key{" on" if on else ""}" style="{style}" href="{e(href)}">{inner}</a>'
    long_btn = ""
    if btn.get("longAction"):
        long_btn = (f'<button class="b-long" name="long" value="1" '
                    f'title="{e(btn["longAction"])}">⋯ {e(_t(req, "long"))}</button>')
    return (f'<form method="post" action="/basic/press" class="b-keyform" style="{_span(btn)}">'
            f'<input type="hidden" name="id" value="{e(btn.get("id", ""))}">'
            f'<input type="hidden" name="page" value="{e(page_id)}">'
            f'<button class="b-key{" on" if on else ""}" style="--led:{e(color)}">{inner}</button>'
            f'{long_btn}</form>')


def _w_slider(req, w, page_id, state):
    bind = w.get("bind")
    val = state_path(state, bind) if bind else None
    val = val if isinstance(val, (int, float)) else (w.get("min", 0) + w.get("max", 100)) // 2
    vp = w.get("valueParam", "level")
    base = {k: v for k, v in (w.get("params") or {}).items() if k != vp}
    hidden = "".join(f'<input type="hidden" name="p_{e(k)}" value="{e(str(v))}">'
                     for k, v in base.items())
    return (f'<form method="post" action="/basic/run" class="b-card" style="--led:{e(w.get("color") or "#60a5fa")};{_span(w)}">'
            f'<input type="hidden" name="page" value="{e(page_id)}">'
            f'<input type="hidden" name="action" value="{e(w.get("action", ""))}">{hidden}'
            f'<label class="b-row"><span>{_icon(w.get("icon"), "#c9d1dd")} {e(w.get("label") or "")}</span>'
            f'<input type="range" name="p_{e(vp)}" min="{int(w.get("min", 0))}" '
            f'max="{int(w.get("max", 100))}" value="{int(val)}"></label>'
            f'<button class="b-mini">{e(_t(req, "ok"))}</button></form>')


def _w_nowplaying(req, w, page_id, state):
    np = state.get("nowplaying") or {}
    title = np.get("title") if np.get("active") else _t(req, "nothing")
    ctl = "".join(_run_form(page_id, "now_playing", {"cmd": c}, lb)
                  for c, lb in (("previous", "⏮"), ("play_pause", "⏯"), ("next", "⏭")))
    return (f'<div class="b-card" style="{_span(w)}"><strong>{e(title or "")}</strong>'
            f'<small>{e(np.get("artist") or "")}</small><div class="b-ctl">{ctl}</div></div>')


def _w_mixer(req, w, page_id, state):
    rows = []
    for a in state.get("mixer") or []:
        rows.append(
            f'<form method="post" action="/basic/run" class="b-row">'
            f'<input type="hidden" name="page" value="{e(page_id)}">'
            f'<input type="hidden" name="action" value="mixer_set">'
            f'<input type="hidden" name="p_app" value="{e(a.get("app", ""))}">'
            f'<span>{e(a.get("name") or a.get("app") or "")}</span>'
            f'<input type="range" name="p_level" min="0" max="100" value="{int(a.get("volume", 0))}">'
            f'<button class="b-mini">{e(_t(req, "ok"))}</button></form>'
            + _run_form(page_id, "mixer_mute", {"app": a.get("app", "")},
                        "🔇" if a.get("muted") else "🔊"))
    body = "".join(rows) or f'<small>{e(_t(req, "no_audio"))}</small>'
    return f'<div class="b-card" style="{_span(w)}">{body}</div>'


def _w_discord(req, w, page_id, state):
    d = state.get("discord") or {}
    st = _t(req, "connected") if d.get("connected") else _t(req, "disconnected")
    members = ", ".join(m.get("name", "") for m in d.get("members") or [])
    return (f'<div class="b-card" style="{_span(w)}"><strong>Discord</strong>'
            f'<small>{e(st)}{" · " + e(d.get("channel")) if d.get("channel") else ""}</small>'
            f'<small>{e(members)}</small><div class="b-ctl">'
            + _run_form(page_id, "discord_mute", {}, ("🔇 " if d.get("mute") else "🎙 ")
                        + e(_t(req, "mute")))
            + _run_form(page_id, "discord_deafen", {}, ("🔕 " if d.get("deaf") else "🎧 ")
                        + e(_t(req, "deaf")))
            + "</div></div>")


def _w_obs(req, w, page_id, state):
    o = state.get("obs") or {}
    st = _t(req, "connected") if o.get("connected") else _t(req, "disconnected")
    scenes = "".join(_run_form(page_id, "obs_scene", {"scene": s}, e(s),
                               "b-mini on" if s == o.get("scene") else "b-mini")
                     for s in o.get("scenes") or [])
    return (f'<div class="b-card" style="{_span(w)}"><strong>OBS · {e(st)}</strong>'
            f'<small>{e(o.get("scene") or "")}</small><div class="b-ctl">'
            + _run_form(page_id, "obs_record_toggle", {}, "⏺ REC",
                        "b-mini on" if o.get("recording") else "b-mini")
            + _run_form(page_id, "obs_stream_toggle", {}, "📡 LIVE",
                        "b-mini on" if o.get("streaming") else "b-mini")
            + f'</div><div class="b-ctl">{scenes}</div></div>')


def _w_ha(req, w, page_id, state):
    ents = ((state.get("ha") or {}).get("entities") or {})
    rows = "".join(_run_form(page_id, "ha_toggle", {"entity_id": k},
                             f'{e(v.get("name") or k)} · {e(str(v.get("state")))}',
                             "b-mini on" if v.get("state") == "on" else "b-mini")
                   for k, v in ents.items())
    return f'<div class="b-card" style="{_span(w)}"><strong>Home Assistant</strong>{rows}</div>'


def _w_text(req, w, title, lines):
    body = "".join(f"<small>{e(str(x))}</small>" for x in lines if x not in (None, ""))
    return f'<div class="b-card" style="{_span(w)}"><strong>{e(title)}</strong>{body}</div>'


def _render_widget(req, w, page_id, state, origin) -> str:
    t = w.get("type") or "button"
    if t == "button":
        return _w_key(req, w, page_id, state, origin)
    if t == "slider":
        return _w_slider(req, w, page_id, state)
    if t == "nowplaying":
        return _w_nowplaying(req, w, page_id, state)
    if t == "mixer":
        return _w_mixer(req, w, page_id, state)
    if t == "discord":
        return _w_discord(req, w, page_id, state)
    if t == "obs":
        return _w_obs(req, w, page_id, state)
    if t == "ha":
        return _w_ha(req, w, page_id, state)
    if t == "clock":
        return _w_text(req, w, time.strftime("%H:%M"), [time.strftime("%d/%m/%Y")])
    if t == "sysmon":
        s = state.get("sysmon") or {}
        return _w_text(req, w, "CPU · RAM · Disco",
                       [f"CPU {s.get('cpu', '–')}%", f"RAM {s.get('ram', '–')}%",
                        f"Disco {s.get('disk', '–')}%"])
    if t == "indicators":
        i = state.get("indicators") or {}
        net, wt = i.get("net") or {}, i.get("weather") or {}
        return _w_text(req, w, "Indicadores",
                       [f"↓{net.get('down', 0)} ↑{net.get('up', 0)} KB/s",
                        " ".join(filter(None, [wt.get("city"), wt.get("temp")]))])
    return _w_text(req, w, w.get("label") or t, [_t(req, "needs_js")])


# ------------------------------------------------------------------ rutas ---
@router.get("/basic")
async def basic_home(req: Request):
    if not authed(req):
        return _pair_page(req)
    cfg = _srv["load_config"]()
    page = _page(cfg, req.query_params.get("page", ""))
    if page is None:
        return _shell(req, "MiniDeck", "<p>Deck vacío</p>")
    state = await _srv["collect_state"]()
    origin = req.query_params.get("from", "")
    items = "".join(_render_widget(req, w, page["id"], state, origin)
                    for w in page.get("buttons") or [])
    cols = int((cfg.get("grid") or {}).get("columns", 4))
    body = (_topbar(req, page["id"]) + _tabs(cfg, page["id"]) + _flash(req)
            + f'<main class="b-grid" style="--cols:{cols}">{items}</main>')
    return _shell(req, f"MiniDeck · {page.get('name', '')}", body)


def _pair_page(req: Request, error: str = "") -> HTMLResponse:
    url = f"http://localhost:{req.url.port or 80}/qr"
    err = f'<p class="b-flash err">{e(error)}</p>' if error else ""
    body = f"""<main class="b-pair"><img src="/icons/icon-192.png" alt="" width="72" height="72">
<h1>{e(_t(req, "pair.title"))}</h1><p>{e(_t(req, "pair.help", url=url))}</p>{err}
<form method="post" action="/basic/pair">
<input name="code" required autocomplete="off" autocapitalize="off" spellcheck="false"
       placeholder="{e(_t(req, "pair.code"))}" aria-label="{e(_t(req, "pair.code"))}">
<button class="b-primary">{e(_t(req, "pair.go"))}</button></form></main>"""
    return _shell(req, _t(req, "pair.title"), body)


@router.post("/basic/pair")
async def basic_pair(req: Request):
    if not _post_ok(req):
        return Response(status_code=403)
    code = (await _form(req)).get("code", "").strip()
    if not code or not auth.check(code):
        return _pair_page(req, _t(req, "pair.bad"))
    resp = _redirect("/basic")
    set_token_cookie(resp, code)
    return resp


@router.post("/basic/prefs")
async def basic_prefs(req: Request):
    if not _post_ok(req):
        return Response(status_code=403)
    f = await _form(req)
    back = f.get("back") or "/basic"
    if not back.startswith("/basic"):
        back = "/basic"
    resp = _redirect(back)
    if f.get("toggle") == "theme":
        new = "" if req.cookies.get(THEME_COOKIE) == "lcd" else "lcd"
        resp.set_cookie(THEME_COOKIE, new, max_age=_YEAR, samesite="lax", path="/")
    elif f.get("toggle") == "lang":
        resp.set_cookie(LANG_COOKIE, "en" if _lang(req) == "es" else "es",
                        max_age=_YEAR, samesite="lax", path="/")
    return resp


def _find(cfg, bid):
    for p in cfg.get("pages") or []:
        for b in p.get("buttons") or []:
            if b.get("id") == bid:
                return p, b
    return None, None


@router.post("/basic/press")
async def basic_press(req: Request):
    if not authed(req) or not _post_ok(req):
        return Response(status_code=403)
    f = await _form(req)
    _p, btn = _find(_srv["load_config"](), f.get("id", ""))
    page = f.get("page", "")
    if btn is None:
        return _back(page, "?", ok=False)
    if f.get("long") and btn.get("longAction"):
        act, prm = btn["longAction"], btn.get("longParams") or {}
    else:
        act, prm = btn.get("action", ""), btn.get("params") or {}
    res = await _srv["run_action"](act, prm)
    return _back(page, res.get("message") or _t(req, "done" if res.get("ok") else "error"),
                 ok=bool(res.get("ok")))


@router.post("/basic/run")
async def basic_run(req: Request):
    """Acciones de los widgets (slider, mezclador, OBS…): action + p_<param>."""
    if not authed(req) or not _post_ok(req):
        return Response(status_code=403)
    f = await _form(req)
    params = {k[2:]: _coerce(v) for k, v in f.items() if k.startswith("p_")}
    res = await _srv["run_action"](f.get("action", ""), params)
    return _back(f.get("page", ""), res.get("message") or _t(req, "done" if res.get("ok")
                                                                else "error"),
                 ok=bool(res.get("ok")))


# ----------------------------------------------------------------- editor ---
BUILTIN_TYPES = ["button", "slider", "nowplaying", "mixer", "discord"]


def _types(cfg) -> list[str]:
    seen = list(BUILTIN_TYPES) + list(_srv.get("plugin_widget_types", lambda: [])())
    for p in cfg.get("pages") or []:
        for b in p.get("buttons") or []:
            t = b.get("type")
            if t and t not in seen:
                seen.append(t)
    return seen


def _opt(value, current, label=None):
    sel = " selected" if str(value) == str(current) else ""
    return f'<option value="{e(str(value))}"{sel}>{e(label or str(value))}</option>'


def _post_btn(action, fields: dict, label, cls="b-mini", confirm_text="") -> str:
    hidden = "".join(f'<input type="hidden" name="{e(k)}" value="{e(str(v))}">'
                     for k, v in fields.items())
    note = f'<small class="b-warn">{e(confirm_text)}</small>' if confirm_text else ""
    return (f'<form method="post" action="{action}" class="b-inline">{hidden}'
            f'<button class="{cls}">{label}</button>{note}</form>')


@router.get("/basic/edit")
async def basic_edit(req: Request):
    if not authed(req):
        return _pair_page(req)
    cfg = _srv["load_config"]()
    page = _page(cfg, req.query_params.get("page", ""))
    pid = page["id"]
    rows = []
    for i, b in enumerate(page.get("buttons") or []):
        kind = b.get("type") or "button"
        desc = b.get("action", "") if kind == "button" else kind
        rows.append(
            f'<li class="b-item"><span class="b-ic">{_icon(b.get("icon"), b.get("color"))}</span>'
            f'<span class="b-grow"><strong>{e(b.get("label") or b.get("id", ""))}</strong>'
            f'<small>{e(desc)}</small></span>'
            f'<a class="b-mini" href="/basic/edit/item?page={quote(pid)}&id={quote(b.get("id", ""))}">'
            f'✎ {e(_t(req, "ed.edit"))}</a>'
            + _post_btn("/basic/edit/move", {"page": pid, "id": b.get("id", ""), "dir": -1}, "↑")
            + _post_btn("/basic/edit/move", {"page": pid, "id": b.get("id", ""), "dir": 1}, "↓")
            + _post_btn("/basic/edit/delete", {"page": pid, "id": b.get("id", "")}, "🗑",
                        "b-mini danger")
            + f'<!-- {i} --></li>')
    body = (_topbar(req, pid, editing=True) + _tabs(cfg, pid, "/basic/edit") + _flash(req)
            + f'<main class="b-edit"><h1>{e(_t(req, "ed.title"))} · {e(page.get("name", ""))}</h1>'
            f'<ul class="b-list">{"".join(rows)}</ul>'
            + _post_btn("/basic/edit/add", {"page": pid}, "＋ " + e(_t(req, "ed.add")),
                        "b-primary")
            + f"""<section class="b-sec"><h2>{e(_t(req, "ed.page"))}</h2>
<form method="post" action="/basic/edit/page" class="b-inline">
<input type="hidden" name="page" value="{e(pid)}"><input type="hidden" name="op" value="rename">
<input name="name" value="{e(page.get("name", ""))}" required aria-label="{e(_t(req, "ed.name"))}">
<button class="b-mini">{e(_t(req, "ed.rename"))}</button></form>
<form method="post" action="/basic/edit/page" class="b-inline">
<input type="hidden" name="op" value="add">
<input name="name" placeholder="{e(_t(req, "ed.addpage"))}" required aria-label="{e(_t(req, "ed.addpage"))}">
<button class="b-mini">＋ {e(_t(req, "ed.addpage"))}</button></form>"""
            + _post_btn("/basic/edit/page", {"page": pid, "op": "delete"},
                        "🗑 " + e(_t(req, "ed.delpage")), "b-mini danger",
                        _t(req, "ed.confirm_page"))
            + "</section><section class='b-sec'>"
            + _post_btn("/basic/edit/undo", {"page": pid}, "↶ " + e(_t(req, "ed.undo")))
            + f' <a class="b-mini" href="/basic/export" download>⇩ {e(_t(req, "ed.export"))}</a>'
            + f"""<form method="post" action="/basic/edit/import" class="b-col">
<label>{e(_t(req, "ed.import"))}<textarea name="json" rows="4" spellcheck="false"></textarea></label>
<button class="b-mini">⇧ {e(_t(req, "ed.save"))}</button></form></section></main>""")
    return _shell(req, _t(req, "ed.title"), body)


@router.get("/basic/edit/item")
async def basic_edit_item(req: Request, page: str = "", id: str = ""):  # noqa: A002
    if not authed(req):
        return _pair_page(req)
    cfg = _srv["load_config"]()
    _p, b = _find(cfg, id)
    if b is None:
        return _back(page, "?", ok=False, base="/basic/edit")
    return _item_form(req, cfg, page, b)


def _rules(action: str, values: dict) -> dict:
    """Reglas de los campos: esquema de la acción + claves ya presentes."""
    if action == "page":
        return {"page": {"type": "page", "required": True}}
    rules = {k: dict(v) for k, v in (_srv.get("action_schema", lambda a: {})(action) or {}).items()
             if not k.startswith("$")}
    for k, v in (values or {}).items():
        if k not in rules:
            rules[k] = {"type": "bool" if isinstance(v, bool) else
                        "int" if isinstance(v, int) else "float" if isinstance(v, float) else
                        "list" if isinstance(v, list) else "dict" if isinstance(v, dict) else "str"}
    return rules


def _simple_list(v) -> bool:
    return isinstance(v, list) and all(not isinstance(x, (dict, list)) for x in v)


def _param_fields(req, prefix: str, action: str, values: dict, cfg) -> str:
    """Campos de formulario (sin JSON) para los params de `action`."""
    if not action:
        return ""
    labels = _PARAM_LABELS[_lang(req)]
    out = [f'<input type="hidden" name="{prefix}_action" value="{e(action)}">']
    for key, r in _rules(action, values).items():
        name = f"{prefix}_{key}"
        cur = (values or {}).get(key)
        lab = e(labels.get(key, key.replace("_", " ").capitalize())) + (" *" if r.get("required") else "")
        if r.get("type") == "page":
            opts = _opt("back", cur, _t(req, "ed.back")) + "".join(
                _opt(p["id"], cur, p.get("name") or p["id"]) for p in cfg.get("pages") or [])
            field = f'<select name="{name}">{opts}</select>'
        elif r.get("choices"):
            opts = ("" if r.get("required") else _opt("", cur if cur is not None else "", _t(req, "ed.default")))
            opts += "".join(_opt(c, cur) for c in r["choices"])
            field = f'<select name="{name}">{opts}</select>'
        elif r.get("type") == "bool":
            val = "" if cur is None else str(cur).lower()
            field = (f'<select name="{name}">{_opt("", val, _t(req, "ed.default"))}'
                     f'{_opt("true", val, _t(req, "ed.yes"))}{_opt("false", val, _t(req, "ed.no"))}</select>')
        elif r.get("type") in ("int", "float"):
            mn = f' min="{r["min"]}"' if "min" in r else ""
            mx = f' max="{r["max"]}"' if "max" in r else ""
            step = "1" if r["type"] == "int" else "any"
            field = (f'<input type="number" name="{name}" step="{step}"{mn}{mx} '
                     f'value="{e("" if cur is None else str(cur))}">')
        elif r.get("type") == "list" and (cur is None or _simple_list(cur)):
            txt = "\n".join(map(str, cur or []))
            field = (f'<textarea name="{name}" rows="3" placeholder="{e(_t(req, "ed.lines"))}">'
                     f'{e(txt)}</textarea>')
        elif r.get("type") in ("list", "dict"):
            continue          # estructuras complejas: solo en "Avanzado"
        else:
            field = f'<input name="{name}" value="{e("" if cur is None else str(cur))}">'
        out.append(f"<label>{lab}{field}</label>")
    return "".join(out)


def _read_fields(f: dict, prefix: str, action: str, base: dict) -> dict:
    """Params desde los campos del formulario (si eran de esta misma acción)."""
    if f.get(f"{prefix}_action") != action:
        return base          # acción nueva: sus campos aparecerán al recargar
    params = dict(base)
    for key, r in _rules(action, base).items():
        name = f"{prefix}_{key}"
        if name not in f:
            continue
        raw = f[name]
        if raw.strip() == "":
            params.pop(key, None)
            continue
        t = r.get("type")
        if t == "bool":
            params[key] = raw == "true"
        elif t == "int":
            try:
                params[key] = int(float(raw))
            except ValueError:
                params[key] = raw
        elif t == "float":
            try:
                params[key] = float(raw)
            except ValueError:
                params[key] = raw
        elif t == "list":
            params[key] = [x.strip() for x in raw.splitlines() if x.strip()]
        else:
            params[key] = raw
    return params


def _when_fields(req, when: dict) -> str:
    w = when or {}
    color = w.get("color") or "#f87171"
    checked = " checked" if w.get("color") else ""
    return (f'<label>{e(_t(req, "ed.wkey"))}<input name="w_key" value="{e(str(w.get("key", "")))}"></label>'
            f'<label>{e(_t(req, "ed.wequals"))}<input name="w_equals" value="{e("" if "equals" not in w else str(w["equals"]))}"></label>'
            f'<label>{e(_t(req, "ed.wlabel"))}<input name="w_label" value="{e(str(w.get("label", "")))}"></label>'
            f'<label>{e(_t(req, "ed.wicon"))}<input name="w_icon" value="{e(str(w.get("icon", "")))}"></label>'
            f'<div class="b-row"><label class="b-check"><input type="checkbox" name="w_usecolor" value="1"{checked}> '
            f'{e(_t(req, "ed.wcolor"))}</label><input type="color" name="w_color" value="{e(color)}"></div>')


def _read_when(f: dict) -> dict | None:
    key = (f.get("w_key") or "").strip()
    if not key:
        return None
    w = {"key": key}
    if (f.get("w_equals") or "").strip():
        w["equals"] = _coerce(f["w_equals"])
    for k in ("label", "icon"):
        if (f.get(f"w_{k}") or "").strip():
            w[k] = f[f"w_{k}"].strip()
    if f.get("w_usecolor"):
        w["color"] = f.get("w_color") or "#f87171"
    return w


def _item_form(req, cfg, page, b, error="") -> HTMLResponse:
    actions = ["", "page"] + list(_srv["list_actions"]())
    kind = b.get("type") or "button"
    w = str(b.get("w", 1))
    err = f'<p class="b-flash err">{e(error)}</p>' if error else ""

    def ta(name, value):
        """JSON en "Avanzado". Se guarda también el original: si no se toca,
        manda el formulario; si se edita, manda el JSON."""
        txt = "" if value in (None, {}, "") else json.dumps(value, ensure_ascii=False, indent=2)
        return (f'<details class="b-adv"><summary>{e(_t(req, "ed.advanced"))}</summary>'
                f'<textarea name="{name}" rows="3" spellcheck="false">{e(txt)}</textarea></details>'
                f'<input type="hidden" name="{name}__orig" value="{e(txt)}">')

    act = b.get("action", "")
    long_act = b.get("longAction", "")

    body = (_topbar(req, page, editing=True) + err
            + f"""<main class="b-edit"><h1>✎ {e(b.get("label") or b.get("id", ""))}</h1>
<form method="post" action="/basic/edit/item" class="b-col">
<input type="hidden" name="page" value="{e(page)}"><input type="hidden" name="id" value="{e(b.get("id", ""))}">
<label>{e(_t(req, "ed.name"))}<input name="label" value="{e(b.get("label") or "")}"></label>
<label>{e(_t(req, "ed.icon"))} <small>lucide:play · 🎮 · img:custom/x.png</small>
  <input name="icon" value="{e(b.get("icon") or "")}"></label>
<label>{e(_t(req, "ed.color"))}<input name="color" type="color" value="{e(b.get("color") or "#60a5fa")}"></label>
<label>{e(_t(req, "ed.type"))}<select name="type">{"".join(_opt(t, kind) for t in _types(cfg))}</select></label>
<div class="b-row"><label>{e(_t(req, "ed.w"))}<select name="w">{"".join(_opt(v, w) for v in ("1", "2", "3", "full"))}</select></label>
<label>{e(_t(req, "ed.h"))}<select name="h">{"".join(_opt(v, b.get("h", 1)) for v in range(1, 6))}</select></label></div>
<label>{e(_t(req, "ed.action"))}<select name="action">{"".join(_opt(a, b.get("action", "")) for a in actions)}</select></label>
<fieldset class="b-fs"><legend>{e(_t(req, "ed.params"))}</legend>
{_param_fields(req, "pf", act, b.get("params") or {}, cfg)}<small>{e(_t(req, "ed.newaction"))}</small>
{ta("params", b.get("params"))}</fieldset>
<label>{e(_t(req, "ed.longaction"))}<select name="longAction">{"".join(_opt(a, long_act) for a in actions)}</select></label>
<fieldset class="b-fs"><legend>{e(_t(req, "ed.longparams"))}</legend>
{_param_fields(req, "lp", long_act, b.get("longParams") or {}, cfg)}
{ta("longParams", b.get("longParams"))}</fieldset>
<fieldset class="b-fs"><legend>{e(_t(req, "ed.when"))}</legend>
{_when_fields(req, b.get("when"))}
{ta("when", b.get("when"))}</fieldset>
<div class="b-row"><button class="b-primary">{e(_t(req, "ed.save"))}</button>
<a class="b-mini" href="/basic/edit?page={quote(page)}">{e(_t(req, "ed.cancel"))}</a></div>
</form></main>""")
    return _shell(req, _t(req, "ed.title"), body)


def _json_field(req, f, name, empty):
    raw = (f.get(name) or "").strip()
    if not raw:
        return empty
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise ValueError(_t(req, "badjson", f=name, e=str(exc)[:60])) from None


async def _guard(req):
    return authed(req) and _post_ok(req)


@router.post("/basic/edit/item")
async def basic_edit_item_save(req: Request):
    if not await _guard(req):
        return Response(status_code=403)
    f = await _form(req)
    cfg = _srv["load_config"]()
    _p, b = _find(cfg, f.get("id", ""))
    if b is None:
        return _back(f.get("page", ""), "?", ok=False, base="/basic/edit")
    def edited(name):
        return (f.get(name) or "").strip() != (f.get(name + "__orig") or "").strip()
    try:
        params = _json_field(req, f, "params", {})
        long_params = _json_field(req, f, "longParams", {})
        when = _json_field(req, f, "when", None)
    except ValueError as exc:
        return _item_form(req, cfg, f.get("page", ""), b, str(exc))
    # el formulario manda, salvo que se haya editado el JSON de "Avanzado"
    if not edited("params"):
        params = _read_fields(f, "pf", f.get("action", ""), params if isinstance(params, dict) else {})
    if not edited("longParams"):
        long_params = _read_fields(f, "lp", f.get("longAction", ""),
                                   long_params if isinstance(long_params, dict) else {})
    if not edited("when") and "w_key" in f:
        when = _read_when(f)
    b["label"] = f.get("label", "").strip()
    b["icon"] = f.get("icon", "").strip()
    b["color"] = f.get("color") or "#8a93a3"
    kind = f.get("type") or "button"
    if kind == "button":
        b.pop("type", None)
    else:
        b["type"] = kind
    w = f.get("w", "1")
    if w == "1":
        b.pop("w", None)
    else:
        b["w"] = "full" if w == "full" else int(w)
    h = int(f.get("h") or 1)
    if h > 1:
        b["h"] = h
    else:
        b.pop("h", None)
    if f.get("action"):
        b["action"] = f["action"]
    else:
        b.pop("action", None)
    b["params"] = params
    if f.get("longAction"):
        b["longAction"], b["longParams"] = f["longAction"], long_params
    else:
        b.pop("longAction", None)
        b.pop("longParams", None)
    if when and when.get("key"):
        b["when"] = when
    else:
        b.pop("when", None)
    _srv["save_config"](cfg)
    return _back(f.get("page", ""), _t(req, "saved"), base="/basic/edit")


def _edit_op(fn):
    async def handler(req: Request):
        if not await _guard(req):
            return Response(status_code=403)
        f = await _form(req)
        cfg = _srv["load_config"]()
        try:
            page = fn(cfg, f, req)
            _srv["save_config"](cfg)
        except (ValueError, KeyError, StopIteration) as exc:
            return _back(f.get("page", ""), str(exc) or "?", ok=False, base="/basic/edit")
        return _back(page if page is not None else f.get("page", ""), _t(req, "saved"),
                     base="/basic/edit")
    return handler


def _op_move(cfg, f, req):
    page, b = _find(cfg, f["id"])
    btns = page["buttons"]
    i = btns.index(b)
    j = max(0, min(len(btns) - 1, i + int(f.get("dir", 0))))
    btns.insert(j, btns.pop(i))


def _op_delete(cfg, f, req):
    page, b = _find(cfg, f["id"])
    page["buttons"].remove(b)


def _op_add(cfg, f, req):
    page = _page(cfg, f.get("page", ""))
    page.setdefault("buttons", []).append({
        "id": f"w_{int(time.time() * 1000) % 10**9:x}", "label": _t(req, "ed.new"),
        "icon": "lucide:square", "color": "#60a5fa", "action": "hotkey", "params": {"keys": ""}})


def _op_page(cfg, f, req):
    op = f.get("op")
    pages = cfg["pages"]
    if op == "add":
        pid = f"p_{int(time.time() * 1000) % 10**9:x}"
        pages.append({"id": pid, "name": f.get("name", "").strip() or pid, "buttons": []})
        return pid
    page = _page(cfg, f.get("page", ""))
    if op == "rename":
        page["name"] = f.get("name", "").strip() or page["name"]
    elif op == "delete":
        if len(pages) <= 1:
            raise ValueError("No puedes eliminar la única página")
        pages.remove(page)
        return pages[0]["id"]
    return None


router.post("/basic/edit/move")(_edit_op(_op_move))
router.post("/basic/edit/delete")(_edit_op(_op_delete))
router.post("/basic/edit/add")(_edit_op(_op_add))
router.post("/basic/edit/page")(_edit_op(_op_page))


@router.post("/basic/edit/undo")
async def basic_undo(req: Request):
    if not await _guard(req):
        return Response(status_code=403)
    f = await _form(req)
    try:
        _srv["restore_backup"]()
        return _back(f.get("page", ""), "↶ " + _t(req, "done"), base="/basic/edit")
    except (ValueError, OSError) as exc:
        return _back(f.get("page", ""), str(exc), ok=False, base="/basic/edit")


@router.post("/basic/edit/import")
async def basic_import(req: Request):
    if not await _guard(req):
        return Response(status_code=403)
    f = await _form(req)
    try:
        new = json.loads(f.get("json") or "")
        _srv["validate_config"](new)
    except ValueError as exc:
        return _back("", f"{_t(req, 'error')}: {str(exc)[:80]}", ok=False, base="/basic/edit")
    old = _srv["load_config"]()
    if old.get("pluginSettings") and not new.get("pluginSettings"):
        new["pluginSettings"] = old["pluginSettings"]   # conservar secretos locales
    _srv["save_config"](new)
    return _back(new["pages"][0]["id"], _t(req, "saved"), base="/basic/edit")


@router.get("/basic/export")
async def basic_export(req: Request):
    if not authed(req):
        return Response(status_code=403)
    cfg = dict(_srv["load_config"]())
    cfg.pop("pluginSettings", None)          # contraseñas/tokens de plugins: nunca
    return Response(json.dumps(cfg, ensure_ascii=False, indent=2),
                    media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="minideck.deck.json"',
                             "Cache-Control": "no-store"})
