# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""
MiniDeck — Servidor principal
FastAPI + WebSocket. Sirve el frontend y ejecuta acciones en el equipo.

Uso:  python main.py [--host 0.0.0.0] [--port 8765]
"""
import argparse
import asyncio
import base64
import html
import io
import json
import logging
import os
import re
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import auth
import basic
import icons
from actions import (
    META,
    OWNERS,
    PLUGINS,
    REGISTRY,
    STATE_SOURCES,
    describe_actions,
    frontend_assets,
    load_all_actions,
    plugin_file,
    validate_params,
)
from paths import (
    BACKUP_DIR,
    CERT_FILE,
    CONFIG_PATH,
    FRONTEND_DIR,
    KEY_FILE,
    LOG_DIR,
    ensure_dirs,
)
from version import LICENSE, PLUGIN_API, SOURCE_URL, __version__

_LOG_FMT = "%(asctime)s  %(levelname)s  %(name)s  %(message)s"
logging.basicConfig(level=logging.INFO, format=_LOG_FMT)
log = logging.getLogger("minideck")
LOG_FILE = LOG_DIR / "minideck.log"
try:
    # Sin consola (MiniDeck.bat, app empaquetada) el log es la única pista
    # cuando algo falla: archivo con rotación, máx. ~3 MB en total.
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    _fh = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    _fh.setFormatter(logging.Formatter(_LOG_FMT))
    logging.getLogger().addHandler(_fh)
except OSError as _exc:  # disco de solo lectura, permisos…: seguir sin archivo
    log.warning("No se pudo abrir el log en %s: %s", LOG_FILE, _exc)

STATE_TIMEOUT = 5.0     # máximo por fuente de estado en cada sondeo

# Pools de hilos separados: una descarga lenta (iconos sin internet) o una
# acción colgada no puede dejar sin hilos a los botones ni al estado en vivo.
ACTION_POOL = ThreadPoolExecutor(16, thread_name_prefix="action")
STATE_POOL = ThreadPoolExecutor(8, thread_name_prefix="state")
IO_POOL = ThreadPoolExecutor(4, thread_name_prefix="io")


def in_pool(pool: ThreadPoolExecutor, fn, *args):
    """Como asyncio.to_thread, pero en el pool indicado."""
    return asyncio.get_running_loop().run_in_executor(pool, fn, *args)
MAX_BACKUPS = 30

PORT = int(os.environ.get("MINIDECK_PORT", "8765"))
HOST = os.environ.get("MINIDECK_HOST", "0.0.0.0")

# TLS: si existen certificados en la carpeta de datos, se sirve por HTTPS
# (necesario para instalar la PWA sin barras en Android). Ver
# build/make_cert.command. Sin certs, sigue por HTTP (iOS funciona igual).
USE_TLS = CERT_FILE.exists() and KEY_FILE.exists()
SCHEME = "https" if USE_TLS else "http"

ensure_dirs()


def base_url() -> str:
    return f"{SCHEME}://{local_ip()}:{PORT}"


def pair_url() -> str:
    """URL que empareja el móvil: incluye el token (la codifica el QR)."""
    return f"{base_url()}/?token={auth.TOKEN}"


# ---------------------------------------------------------------- config ----
def load_config() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def validate_config(cfg) -> None:
    """Rechaza configs que romperían el cliente (evita guardar basura)."""
    if not isinstance(cfg, dict):
        raise ValueError("la config debe ser un objeto JSON")
    pages = cfg.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError("la config necesita al menos una página en 'pages'")
    for p in pages:
        if not isinstance(p, dict) or not p.get("id"):
            raise ValueError("cada página necesita un 'id'")
        if not isinstance(p.get("buttons", []), list):
            raise ValueError(f"'buttons' de la página '{p['id']}' debe ser una lista")


def _backup_current() -> None:
    """Guarda una copia del deck.json actual antes de sobrescribirlo."""
    try:
        current = CONFIG_PATH.read_text(encoding="utf-8")
    except OSError:
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    existing = list_backups()
    if existing and (BACKUP_DIR / existing[0]).read_text(encoding="utf-8") == current:
        return  # nada cambió desde la última copia
    ns = time.time_ns()   # nombre ordenable incluso con varios guardados por segundo
    stamp = time.strftime("deck-%Y%m%d-%H%M%S", time.localtime(ns // 10**9))
    name = f"{stamp}-{ns % 10**9:09d}.json"
    (BACKUP_DIR / name).write_text(current, encoding="utf-8")
    for old in list_backups()[MAX_BACKUPS:]:
        (BACKUP_DIR / old).unlink(missing_ok=True)


def list_backups() -> list[str]:
    """Copias de seguridad, de la más reciente a la más antigua."""
    if not BACKUP_DIR.is_dir():
        return []
    return sorted((p.name for p in BACKUP_DIR.glob("deck-*.json")), reverse=True)


def restore_backup(name: str | None = None) -> dict:
    """Restaura una copia (por defecto la última) y la consume: deshacer
    varias veces va retrocediendo en el historial."""
    names = list_backups()
    if not names:
        raise ValueError("No hay cambios que deshacer")
    name = name or names[0]
    if name not in names:
        raise ValueError("Copia no encontrada")
    cfg = json.loads((BACKUP_DIR / name).read_text(encoding="utf-8"))
    save_config(cfg, backup=False)
    (BACKUP_DIR / name).unlink(missing_ok=True)
    return cfg


def save_config(cfg: dict, backup: bool = True) -> None:
    """Escritura atómica: primero a un temporal, luego reemplazo. Evita
    archivos corruptos a medias y reduce choques con sincronizadores
    de archivos (OneDrive, Dropbox) que bloquean el archivo original.
    Antes guarda una copia del deck anterior (para deshacer)."""
    validate_config(cfg)
    if backup:
        _backup_current()
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    tmp.replace(CONFIG_PATH)


# ------------------------------------------------------- websocket manager --
class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)
        log.info("Cliente conectado (%d activos)", len(self.active))

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.active:
            self.active.remove(ws)
        log.info("Cliente desconectado (%d activos)", len(self.active))

    async def broadcast(self, message: dict) -> None:
        dead = []
        for ws in list(self.active):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


manager = ConnectionManager()


# ------------------------------------------------------ vigilantes de fondo -
_LEGACY_SOURCES = ("volume_get", "now_playing_get", "discord_get", "mixer_get")
_state_errors_logged: set[str] = set()


def _state_sources():
    """Fuentes clásicas + las registradas por plugins con state=True."""
    names = [n for n in _LEGACY_SOURCES if n in REGISTRY]
    names += [n for n in STATE_SOURCES if n not in names]
    return names


async def collect_state(errors: dict | None = None) -> dict:
    """Foto completa del estado del equipo (volumen, canción, discord…).
    Las fuentes se consultan en paralelo: una lenta no frena a las demás."""
    names = [n for n in _state_sources() if n in REGISTRY]
    results = await asyncio.gather(
        *(asyncio.wait_for(in_pool(STATE_POOL, REGISTRY[n], {}), STATE_TIMEOUT)
          for n in names),
        return_exceptions=True)
    snap = {}
    for name, result in zip(names, results, strict=True):
        if isinstance(result, BaseException):
            if errors is not None:
                errors[name] = f"{type(result).__name__}: {result}"
            elif name not in _state_errors_logged:
                _state_errors_logged.add(name)
                log.warning("Fuente de estado '%s' falló: %s: %s",
                            name, type(result).__name__, result)
            continue
        snap.update((result or {}).get("state") or {})
    return snap


async def watch_system_state():
    """Sondea el estado del equipo cada segundo y difunde los cambios,
    aunque se hayan hecho desde el propio equipo."""
    last = None
    while True:
        await asyncio.sleep(1)
        if not manager.active:
            continue
        snap = await collect_state()
        if snap and snap != last:
            last = snap
            await manager.broadcast({"type": "state", "data": snap})


async def watch_config_file():
    """Si editas deck.json y guardas, todos los clientes se actualizan solos."""
    last_mtime = None
    while True:
        await asyncio.sleep(1)
        try:
            mtime = CONFIG_PATH.stat().st_mtime
        except OSError:
            continue
        if last_mtime is None:
            last_mtime = mtime
            continue
        if mtime != last_mtime:
            last_mtime = mtime
            try:
                cfg = load_config()
            except json.JSONDecodeError:
                log.warning("deck.json guardado con JSON inválido; se ignora")
                continue
            log.info("deck.json cambió: actualizando clientes")
            await manager.broadcast({"type": "config", "data": cfg})


@asynccontextmanager
async def lifespan(_app: FastAPI):
    tasks = [asyncio.create_task(watch_system_state()),
             asyncio.create_task(watch_config_file())]
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="MiniDeck", version=__version__, lifespan=lifespan)


# ------------------------------------------------------------ middlewares ---
# Rutas de /api que no requieren token (solo accesibles desde este equipo).
_LOCAL_ONLY = {"/api/pair"}


@app.middleware("http")
async def security(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") or path == "/qr":
        client = request.client.host if request.client else None
        if path in _LOCAL_ONLY or path == "/qr":
            if not auth.local_request(client, request.headers):
                return JSONResponse({"ok": False, "error": "solo desde este equipo"},
                                    status_code=403)
        elif not auth.check(auth.token_from(request.headers, request.query_params,
                                            request.cookies)):
            return JSONResponse({"ok": False, "error": "no autorizado"}, status_code=401)
        elif request.method != "GET" and not auth.same_origin(request.headers):
            return JSONResponse({"ok": False, "error": "origen no permitido"},
                                status_code=403)

    response = await call_next(request)
    # QR escaneado (/?token=…): guardar también la cookie, para que el modo sin
    # JavaScript (/basic) quede emparejado aunque el navegador no ejecute JS.
    tok = request.query_params.get("token")
    if path == "/" and tok and auth.check(tok) and not auth.AUTH_DISABLED:
        basic.set_token_cookie(response, tok)
    # Evita que el navegador/PWA cachee el frontend: sin esto, iOS puede
    # quedarse con versiones viejas de CSS/JS.
    if path == "/" or path.endswith((".html", ".css", ".js", ".webmanifest")):
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    # same-origin: el referrer nunca sale hacia otros sitios (CDN, Iconify), pero
    # los POST propios llevan su Origin real (con no-referrer el navegador manda
    # "Origin: null" y la protección anti-CSRF los rechazaría)
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


# ---------------------------------------------------------- action runner ---
async def run_action(action: str, params: dict) -> dict:
    """Ejecuta una acción del registro. Devuelve {ok, message, state?}."""
    fn = REGISTRY.get(action)
    if fn is None:
        return {"ok": False, "message": f"Acción desconocida: '{action}'"}
    if not isinstance(params, dict):
        return {"ok": False, "message": "params debe ser un objeto"}
    params = dict(params)
    try:
        validate_params(action, params)
    except ValueError as exc:
        return {"ok": False, "message": f"{action}: {exc}"}
    timeout = (META.get(action) or {}).get("timeout", 30.0)
    try:
        # Las acciones son síncronas y potencialmente bloqueantes:
        # se ejecutan en un hilo para no congelar el servidor.
        result = await asyncio.wait_for(in_pool(ACTION_POOL, fn, params), timeout)
        if result is None:
            result = {}
        return {"ok": True, **result}
    except asyncio.TimeoutError:
        # El hilo no se puede matar, pero el móvil deja de esperar.
        log.warning("La acción '%s' superó %.0fs", action, timeout)
        return {"ok": False, "message": f"'{action}' tardó más de {timeout:.0f}s"}
    except Exception as exc:  # noqa: BLE001
        log.exception("Error ejecutando '%s'", action)
        return {"ok": False, "message": f"{type(exc).__name__}: {exc}"}


def find_button(cfg: dict, button_id: str) -> dict | None:
    for page in cfg.get("pages", []):
        for btn in page.get("buttons", []):
            if btn.get("id") == button_id:
                return btn
    return None


# ---------------------------------------------------------------- routes ----
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    if not auth.same_origin(ws.headers) or \
            not auth.check(auth.token_from(ws.headers, ws.query_params, ws.cookies)):
        # 4401: código propio → el cliente muestra la pantalla de emparejar
        await ws.close(code=4401)
        return
    await manager.connect(ws)
    try:
        # Al conectar, el cliente recibe la configuración completa del deck
        # y una foto del estado actual (mixer, discord, canción, volumen).
        await ws.send_json({"type": "config", "data": load_config()})
        snap = await collect_state()
        if snap:
            await ws.send_json({"type": "state", "data": snap})
        while True:
            msg = await ws.receive_json()
            if not isinstance(msg, dict):
                continue
            mtype = msg.get("type")

            if mtype == "press":
                # {"type":"press","buttonId":"btn_mute"}
                cfg = load_config()
                btn = find_button(cfg, msg.get("buttonId", ""))
                if btn is None:
                    await ws.send_json({"type": "result", "ok": False,
                                        "buttonId": msg.get("buttonId"),
                                        "message": "Botón no encontrado"})
                    continue
                # pulsación larga → segunda acción del botón, si la tiene
                if msg.get("long") and btn.get("longAction"):
                    act, prm = btn["longAction"], btn.get("longParams") or {}
                else:
                    act, prm = btn.get("action", ""), btn.get("params") or {}
                result = await run_action(act, prm)
                await ws.send_json({"type": "result",
                                    "buttonId": btn["id"], **result})
                # Si la acción devolvió estado (ej. volumen), se difunde a todos.
                if result.get("state"):
                    await manager.broadcast({"type": "state", "data": result["state"]})

            elif mtype == "run":
                # Ejecución directa sin botón: {"type":"run","action":"...","params":{...}}
                result = await run_action(msg.get("action", ""), msg.get("params") or {})
                await ws.send_json({"type": "result", **result})
                if result.get("state"):
                    await manager.broadcast({"type": "state", "data": result["state"]})

            elif mtype == "get_config":
                await ws.send_json({"type": "config", "data": load_config()})

            elif mtype == "save_config":
                try:
                    save_config(msg.get("data"))
                    log.info("deck.json guardado desde un cliente")
                    await ws.send_json({"type": "result", "ok": True,
                                        "message": "Guardado en el equipo ✓"})
                    await manager.broadcast({"type": "config", "data": load_config()})
                except Exception as exc:  # noqa: BLE001
                    log.warning("NO se pudo guardar deck.json: %s", exc)
                    await ws.send_json({"type": "result", "ok": False,
                                        "message": f"No se pudo guardar: {exc}"})

            elif mtype == "undo":
                try:
                    await in_pool(IO_POOL, restore_backup)
                    await ws.send_json({"type": "result", "ok": True,
                                        "message": "Cambio deshecho ↶"})
                    await manager.broadcast({"type": "config", "data": load_config()})
                except Exception as exc:  # noqa: BLE001
                    await ws.send_json({"type": "result", "ok": False,
                                        "message": str(exc)})

            elif mtype == "ping":
                await ws.send_json({"type": "pong"})

    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        log.exception("Error en WebSocket")
    finally:
        manager.disconnect(ws)


@app.get("/api/pair")
async def api_pair():
    """Entrega el token SOLO a clientes del propio equipo (ver middleware).
    Así, abrir http://localhost:8765 en el PC no pide emparejar."""
    return JSONResponse({"token": auth.TOKEN})


@app.get("/api/info")
async def api_info():
    return JSONResponse({"name": "MiniDeck", "version": __version__,
                         "license": LICENSE, "source": SOURCE_URL,
                         "pluginApi": PLUGIN_API, "platform": sys.platform})


@app.get("/api/config")
async def get_config():
    return JSONResponse(load_config())


@app.get("/api/actions")
async def list_actions():
    """Lista de acciones disponibles (la usa el editor)."""
    return JSONResponse(sorted(REGISTRY.keys()))


@app.get("/api/actions/schema")
async def actions_schema():
    """Qué hace cada acción y qué params espera (el editor rellena plantillas)."""
    return JSONResponse(describe_actions())


@app.get("/api/backups")
async def api_backups():
    return JSONResponse(list_backups())


@app.post("/api/backups/restore")
async def api_backups_restore(req: Request):
    body = await req.json()
    try:
        cfg = await in_pool(IO_POOL, restore_backup, body.get("name"))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
    await manager.broadcast({"type": "config", "data": cfg})
    return JSONResponse({"ok": True})


@app.get("/api/logs")
async def api_logs(lines: int = 200):
    """Últimas líneas del log (diagnóstico desde el móvil o el panel)."""
    lines = max(1, min(lines, 2000))
    try:
        text = LOG_FILE.read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    return Response("\n".join(text.splitlines()[-lines:]), media_type="text/plain")


@app.get("/api/state")
async def api_state():
    """Diagnóstico: estado actual y el error exacto de cada fuente que falle."""
    errors = {n: "acción no registrada (¿módulo de otra plataforma o sin dependencias?)"
              for n in _state_sources() if n not in REGISTRY}
    snap = await collect_state(errors)
    return JSONResponse({"errors": errors, "state": snap})


@app.post("/api/custom_widget")
async def save_custom_widget(req: Request):
    """Crea o actualiza un widget personalizado (desde el Panel de Control).
    Se guarda en deck.json → se difunde a todos los clientes al instante."""
    body = await req.json()
    wid = (body.get("id") or "").strip()
    if not wid or not wid.replace("_", "").replace("-", "").isalnum():
        return JSONResponse({"ok": False, "error": "id inválido (usa letras, números, - y _)"},
                            status_code=400)
    cfg = load_config()
    cfg.setdefault("customWidgets", {})[wid] = {
        "name": (body.get("name") or wid).strip(),
        "html": body.get("html") or "",
        "js": body.get("js") or "",
        "css": body.get("css") or "",
        # definición del modo simple del panel (bloques), si existe
        **({"simple": body["simple"]} if body.get("simple") else {}),
        # librerías externas (URLs https de CDN js/css) del modo código
        **({"libs": [u.strip() for u in body.get("libs", [])
                     if isinstance(u, str) and u.strip().startswith("https://")]}
           if body.get("libs") else {}),
    }
    save_config(cfg)
    await manager.broadcast({"type": "config", "data": cfg})
    return JSONResponse({"ok": True})


@app.delete("/api/custom_widget/{wid}")
async def delete_custom_widget(wid: str):
    cfg = load_config()
    if wid in cfg.get("customWidgets", {}):
        del cfg["customWidgets"][wid]
        save_config(cfg)
        await manager.broadcast({"type": "config", "data": cfg})
    return JSONResponse({"ok": True})


_PKG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-]*(\[[A-Za-z0-9,._\-]+\])?"
                     r"((==|>=|<=|~=|!=|<|>)[A-Za-z0-9.*+!\-]+)?")


@app.post("/api/pip")
async def pip_install(req: Request):
    """Instala un paquete de Python para los plugins (desde el Panel).
    Solo desde el propio equipo: instalar paquetes equivale a ejecutar código.
    Requiere reiniciar el servidor para que un plugin lo vea."""
    if not auth.local_request(req.client.host if req.client else None, req.headers):
        return JSONResponse({"ok": False,
                             "output": "Por seguridad, pip solo se puede usar desde "
                                       "el propio equipo (abre el panel en localhost)."},
                            status_code=403)
    body = await req.json()
    pkg = (body.get("package") or "").strip()
    if not pkg or not _PKG_RE.fullmatch(pkg):
        return JSONResponse({"ok": False, "output": "Nombre de paquete inválido"},
                            status_code=400)
    if getattr(sys, "frozen", False):
        return JSONResponse({"ok": False,
                             "output": "La app empaquetada no puede instalar paquetes."},
                            status_code=400)

    def run():
        base = [sys.executable, "-m", "pip", "install", pkg,
                "--disable-pip-version-check"]
        proc = subprocess.run(base, capture_output=True, text=True, timeout=300)
        # algunos Python (Linux/homebrew) exigen este flag adicional
        if proc.returncode != 0 and "externally-managed" in (proc.stdout + proc.stderr):
            proc = subprocess.run(base + ["--break-system-packages"],
                                  capture_output=True, text=True, timeout=300)
        return proc.returncode, (proc.stdout + proc.stderr)[-4000:]

    try:
        code, out = await in_pool(IO_POOL, run)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "output": str(exc)})
    log.info("pip install %s → %s", pkg, "ok" if code == 0 else "error")
    return JSONResponse({"ok": code == 0, "output": out})


@app.get("/api/plugins")
async def api_plugins():
    """Assets de frontend (js/css) que aportan los plugins activos."""
    return JSONResponse(frontend_assets())


@app.get("/api/plugins/info")
async def api_plugins_info():
    """Plugins instalados con su manifiesto, estado y acciones."""
    keep = ("id", "name", "version", "author", "description", "homepage",
            "platforms", "requires", "settings", "status", "error", "user",
            "frontend", "actions")
    return JSONResponse({
        "plugins": [{k: p.get(k) for k in keep} for p in PLUGINS.values()],
        "core_actions": sorted(a for a, o in OWNERS.items() if o == "core"),
    })


@app.get("/plugins/{plugin_id}/{filename:path}")
async def plugin_static(plugin_id: str, filename: str):
    path = plugin_file(plugin_id, filename)
    if path is None:
        return Response(status_code=404)
    return FileResponse(path)


@app.get("/api/artwork")
async def artwork():
    """Carátula de la canción actual (JPEG). El cliente la pide cuando
    el estado indica un thumbId nuevo."""
    try:
        from actions.media_session import get_thumb_bytes
        data = get_thumb_bytes()
    except Exception:  # noqa: BLE001
        data = None
    if not data:
        return Response(status_code=404)
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "no-store"})


def qr_png(data: str, scale: int = 10) -> bytes | None:
    try:
        import segno
    except ImportError:
        return None
    buf = io.BytesIO()
    segno.make(data, error="m").save(buf, kind="png", scale=scale, border=2,
                                     dark="#111111", light="#ffffff")
    return buf.getvalue()


@app.get("/qr")
async def qr_page():
    """QR para emparejar el móvil. Solo se ve desde este equipo (contiene
    el token de acceso)."""
    url = pair_url()
    png = qr_png(url)
    img_tag = (f'<img src="data:image/png;base64,{base64.b64encode(png).decode()}" alt="QR">'
               if png else '<p style="opacity:.6">(instala "segno" para ver el QR)</p>')
    page = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MiniDeck QR</title><link rel="icon" href="/favicon.svg" type="image/svg+xml"><style>
body{{margin:0;min-height:100vh;display:flex;flex-direction:column;align-items:center;
justify-content:center;gap:18px;background:#1f1f1f;color:#eaeaea;
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:24px;text-align:center}}
h1{{font-size:22px;margin:0}} img{{width:min(72vw,340px);height:auto;background:#fff;
padding:12px;border-radius:16px}} .u{{font-family:ui-monospace,monospace;font-size:16px}}
.t{{opacity:.6;font-size:13px;max-width:380px}} code{{user-select:all}}</style></head>
<body><h1>Escanea para emparejar MiniDeck</h1>{img_tag}
<div class="u">{html.escape(base_url())}</div>
<div class="t">Código de emparejamiento: <code>{html.escape(auth.TOKEN)}</code></div>
<div class="t">Cámara del móvil → abrir en el navegador → Compartir → Añadir a pantalla de inicio.
No compartas este QR: da control total sobre este equipo.</div>
<div class="t">MiniDeck {__version__} · software libre bajo {LICENSE}, sin garantía ·
<a style="color:inherit" href="{html.escape(SOURCE_URL)}">código fuente</a></div>
<div class="t">¿Navegador sin JavaScript? Usa
<a style="color:inherit" href="/basic">el modo básico</a> y escribe el código de arriba.</div>
</body></html>"""
    return Response(content=page, media_type="text/html",
                    headers={"Cache-Control": "no-store"})


@app.get("/iconify/{pack}/{name}.svg")
async def iconify(pack: str, name: str, color: str = ""):
    """Icono con caché local (ver icons.py). Público: no contiene datos."""
    bad_color = color and not icons.COLOR_RE.match(color)
    if not icons.NAME_RE.match(pack) or not icons.NAME_RE.match(name) or bad_color:
        return Response(status_code=400)
    svg = await in_pool(IO_POOL, icons.get_svg, pack, name)
    if svg is None:
        return Response(status_code=404, headers={"Cache-Control": "no-store"})
    return Response(icons.colorize(svg, color), media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=604800"})


@app.get("/manifest.webmanifest")
async def manifest(token: str = ""):
    """Manifiesto PWA. Con un token válido, start_url lo incluye para que la
    app instalada en la pantalla de inicio arranque ya emparejada."""
    data = json.loads((FRONTEND_DIR / "manifest.webmanifest").read_text(encoding="utf-8"))
    if token and auth.check(token):
        data["start_url"] = f"/?token={token}"
    return Response(content=json.dumps(data, ensure_ascii=False),
                    media_type="application/manifest+json")


# Modo sin JavaScript (formularios HTML renderizados en el servidor)
basic.configure(
    load_config=load_config,
    save_config=save_config,
    validate_config=validate_config,
    run_action=lambda action, params: run_action(action, params),
    collect_state=lambda: collect_state(),       # buscada al llamar (tests)
    restore_backup=restore_backup,
    list_actions=lambda: sorted(n for n, m in META.items() if not m["state"]),
    plugin_widget_types=lambda: [pid for pid, p in PLUGINS.items()
                                 if p.get("status") == "loaded" and "widget.js" in p["frontend"]],
)
app.include_router(basic.router)

# Frontend (al final para no tapar /ws, /api ni /plugins)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


# ----------------------------------------------------------------- main -----
def local_ip() -> str:
    """IP de la LAN (no envía tráfico: connect() en UDP solo elige ruta)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:  # noqa: BLE001
        return "127.0.0.1"


load_all_actions()
log.info("MiniDeck %s — acciones: %s", __version__, ", ".join(sorted(REGISTRY.keys())))
if auth.AUTH_DISABLED:
    log.warning("⚠️  Autenticación DESACTIVADA (MINIDECK_NO_AUTH). Cualquiera en tu "
                "red puede controlar este equipo.")


def main() -> None:
    global PORT
    ap = argparse.ArgumentParser(description="MiniDeck — control remoto desde el móvil")
    ap.add_argument("--host", default=HOST, help="interfaz (por defecto 0.0.0.0)")
    ap.add_argument("--port", type=int, default=PORT, help="puerto (por defecto 8765)")
    args = ap.parse_args()
    PORT = args.port

    print()
    print("=" * 60)
    print(f"  MiniDeck {__version__} corriendo" + ("  [HTTPS]" if USE_TLS else ""))
    print(f"  En este equipo:  {SCHEME}://localhost:{PORT}")
    print(f"  QR para el móvil: {SCHEME}://localhost:{PORT}/qr")
    print(f"  Desde el móvil:  {base_url()}  (código: {auth.TOKEN})")
    print("=" * 60)
    print()
    ssl_kw = {"ssl_certfile": str(CERT_FILE), "ssl_keyfile": str(KEY_FILE)} if USE_TLS else {}
    uvicorn.run(app, host=args.host, port=PORT, log_level="warning", **ssl_kw)


if __name__ == "__main__":
    main()
