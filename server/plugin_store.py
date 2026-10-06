# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""
Tienda de plugins: instalar, desinstalar y configurar plugins desde el Panel,
sin tocar JSON a mano.

Rutas (todas bajo /api, así que el middleware exige el token):

    GET    /api/plugins/store            plugins instalados + ajustes (secretos ocultos)
    POST   /api/plugins/install          {"url": "..."}   ← SOLO desde este equipo
    DELETE /api/plugins/{id}             desinstala un plugin de usuario ← SOLO local
    PUT    /api/plugins/{id}/settings    {"settings": {...}}
    POST   /api/plugins/{id}/enabled     {"enabled": bool} (al reiniciar)

Instalar un plugin es ejecutar código de otra persona en este equipo, por eso
instalar y desinstalar solo se permite desde el propio equipo (como /api/pip).
Las funciones de config de main se inyectan con configure() para no importar
main (evita ciclos), igual que en basic.py.
"""
import asyncio
import io
import json
import logging
import os
import re
import shutil
import stat
import sys
import threading
import urllib.error
import urllib.request
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

import actions
import auth
from paths import BUNDLED_PLUGINS_DIR, CONFIG_PATH, USER_PLUGINS_DIR
from version import __version__

log = logging.getLogger("minideck.store")
router = APIRouter()

MAX_DOWNLOAD = 10 * 1024 * 1024        # 10 MB comprimido
MAX_UNCOMPRESSED = 50 * 1024 * 1024    # contra "zip bombs"
MAX_FILES = 2000
MASK = "••••••"
_SECRET_RE = re.compile(r"token|password|passwd|secret|apikey|api_key|api-key", re.I)
_SEG_RE = re.compile(r"^[A-Za-z0-9._\-]+$")

# Descargas y extracción fuera del bucle de eventos (no se puede importar
# main.IO_POOL: main nos importa a nosotros).
_POOL = ThreadPoolExecutor(2, thread_name_prefix="store")
# Una instalación/desinstalación a la vez (tocan REGISTRY y la carpeta).
_LOCK = threading.Lock()

_srv: dict = {}


def configure(**funcs) -> None:
    """load_config, save_config (inyectadas por main)."""
    _srv.update(funcs)


class StoreError(Exception):
    """Error con un mensaje claro para el usuario (en español)."""

    def __init__(self, msg: str, status: int = 400):
        super().__init__(msg)
        self.status = status


class NotFound(StoreError):
    def __init__(self, msg: str = "No encontrado (404)"):
        super().__init__(msg, 404)


def _err(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": msg}, status_code=status)


def _is_local(req: Request) -> bool:
    return auth.local_request(req.client.host if req.client else None, req.headers)


_LOCAL_MSG = ("Por seguridad, los plugins solo se pueden instalar o desinstalar "
              "desde el propio equipo (abre el Panel en localhost).")


async def _run(fn, *args):
    return await asyncio.get_running_loop().run_in_executor(_POOL, fn, *args)


# --------------------------------------------------------------- config ---
def _load_cfg() -> dict:
    if "load_config" in _srv:
        return _srv["load_config"]()
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _save_cfg(cfg: dict) -> None:
    if "save_config" in _srv:
        _srv["save_config"](cfg)
    else:  # escritura atómica, como main.save_config
        tmp = CONFIG_PATH.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        tmp.replace(CONFIG_PATH)
    actions._cfg_cache["mtime"] = None   # noqa: SLF001  releer ajustes ya


# ------------------------------------------------------------- ajustes ----
def is_secret(key: str) -> bool:
    return bool(_SECRET_RE.search(key))


def _kind(default, current=None) -> str:
    if isinstance(default, bool):
        return "bool"
    if isinstance(default, int):
        return "int"
    if isinstance(default, float):
        return "float"
    if isinstance(default, str):
        return "str"
    if isinstance(default, list):
        items = list(default) + (current if isinstance(current, list) else [])
        if all(isinstance(i, (str, int, float)) and not isinstance(i, bool) for i in items):
            return "list"
    return "other"   # dict u otros: no editables desde el Panel


def _mask(key: str, value):
    if not is_secret(key):
        return value
    return MASK if value not in (None, "", [], {}) else ""


def _settings_view(pid: str) -> tuple[list, dict]:
    defaults = (actions.PLUGINS.get(pid) or {}).get("settings") or {}
    if not isinstance(defaults, dict):
        return [], {}
    current = actions.plugin_settings(pid)
    schema, values = [], {}
    for key, default in defaults.items():
        kind = _kind(default, current.get(key))
        secret = is_secret(key)
        schema.append({"key": key, "type": kind, "secret": secret,
                       "default": _mask(key, default)})
        val = current.get(key, default)
        if kind == "list" and isinstance(val, list):
            val = [str(v) for v in val]
        values[key] = _mask(key, val)
    return schema, values


def _coerce(key: str, kind: str, value):
    """Convierte el valor del formulario al tipo del valor por defecto."""
    try:
        if kind == "bool":
            if isinstance(value, bool):
                return value
            s = str(value).strip().lower()
            if s in ("1", "true", "on", "yes", "si", "sí"):
                return True
            if s in ("0", "false", "off", "no", ""):
                return False
            raise ValueError
        if kind == "int":
            if isinstance(value, bool):
                raise ValueError
            if isinstance(value, float) and value.is_integer():
                return int(value)
            return int(str(value).strip())
        if kind == "float":
            if isinstance(value, bool):
                raise ValueError
            return float(str(value).strip().replace(",", "."))
        if kind == "str":
            if isinstance(value, (dict, list)):
                raise ValueError
            return "" if value is None else str(value)
        if kind == "list":
            if isinstance(value, str):
                value = value.splitlines()
            if not isinstance(value, list):
                raise ValueError
            return [str(v).strip() for v in value if str(v).strip()]
    except (TypeError, ValueError):
        pass
    names = {"bool": "sí/no", "int": "un número entero", "float": "un número",
             "str": "texto", "list": "una lista"}
    raise StoreError(f"'{key}' debe ser {names.get(kind, kind)}")


# --------------------------------------------------------------- info -----
def plugin_info(pid: str) -> dict:
    p = actions.PLUGINS[pid]
    schema, values = _settings_view(pid)
    disabled = actions.disabled_plugins()
    return {
        "id": pid, "name": p.get("name") or pid, "version": p.get("version") or "",
        "author": p.get("author") or "", "description": p.get("description") or "",
        "homepage": p.get("homepage") or "", "status": p.get("status") or "",
        "error": p.get("error") or "", "user": bool(p.get("user")),
        "requires": list(p.get("requires") or []), "platforms": p.get("platforms") or [],
        "actions": list(p.get("actions") or []),
        "enabled": pid not in disabled,
        "schema": schema, "settings": values,
    }


@router.get("/api/plugins/store")
async def store_list(req: Request):
    plugins = [plugin_info(pid) for pid in sorted(actions.PLUGINS)]
    return JSONResponse({"plugins": plugins, "canInstall": _is_local(req),
                         "canPip": not getattr(sys, "frozen", False),
                         "version": __version__})


# ------------------------------------------------------------ descarga ----
def download(url: str) -> bytes:
    """Descarga por https con límite de tamaño. Los tests la sustituyen."""
    if urlsplit(url).scheme != "https":
        raise StoreError("Solo se permiten direcciones https://")
    req = urllib.request.Request(url, headers={"User-Agent": f"MiniDeck/{__version__}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (https comprobado)
            if urlsplit(r.geturl()).scheme != "https":
                raise StoreError("La descarga redirigió a una dirección no segura")
            size = int(r.headers.get("Content-Length") or 0)
            if size > MAX_DOWNLOAD:
                raise StoreError("El plugin pesa más de 10 MB")
            data = r.read(MAX_DOWNLOAD + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise NotFound() from None
        raise StoreError(f"Error al descargar ({exc.code})") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise StoreError(f"No se pudo descargar: {reason}. ¿Hay conexión a internet?") from None
    if len(data) > MAX_DOWNLOAD:
        raise StoreError("El plugin pesa más de 10 MB")
    return data


def parse_url(url: str) -> dict:
    """Devuelve {"downloads": [urls a probar], "subpath", "repo", "github"}."""
    url = (url or "").strip()
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc:
        raise StoreError("La dirección debe empezar por https://")
    host = parts.netloc.lower()
    segs = [unquote(s) for s in parts.path.split("/") if s]
    if host in ("github.com", "www.github.com"):
        if len(segs) < 2:
            raise StoreError("Dirección de GitHub incompleta: usa https://github.com/usuario/repo")
        user, repo = segs[0], segs[1]
        if repo.endswith(".git"):
            repo = repo[:-4]
        if not (_SEG_RE.match(user) and _SEG_RE.match(repo)):
            raise StoreError("Dirección de GitHub no válida")
        branches, sub = ["main", "master"], ""
        if len(segs) >= 4 and segs[2] in ("tree", "blob"):
            branches, sub = [segs[3]], "/".join(segs[4:])
        elif len(segs) > 2:
            raise StoreError("Usa la dirección del repositorio o de una carpeta "
                             "(…/tree/<rama>/<carpeta>)")
        if not all(_SEG_RE.match(b) for b in branches):
            raise StoreError("Nombre de rama no válido")
        return {"github": True, "repo": repo, "subpath": sub.strip("/"),
                "downloads": [f"https://codeload.github.com/{user}/{repo}/zip/refs/heads/{b}"
                              for b in branches]}
    if not parts.path.lower().endswith(".zip"):
        raise StoreError("Usa un repositorio de GitHub o un enlace directo a un .zip")
    stem = PurePosixPath(segs[-1]).stem if segs else "plugin"
    return {"github": False, "repo": stem, "subpath": "", "downloads": [url]}


def _fetch(src: dict) -> bytes:
    last = None
    for u in src["downloads"]:
        try:
            return download(u)
        except NotFound as exc:
            last = exc
    if src["github"] and len(src["downloads"]) > 1:
        raise StoreError("No se encontró el repositorio (ni rama main ni master). "
                         "¿Es público y la dirección es correcta?", 404)
    raise StoreError("No se encontró nada en esa dirección (404)", 404) from last


# ----------------------------------------------------------- extracción ---
def _safe_names(zf: zipfile.ZipFile) -> list[tuple[zipfile.ZipInfo, str]]:
    """Valida TODAS las entradas antes de escribir nada (zip-slip)."""
    infos = zf.infolist()
    if len(infos) > MAX_FILES:
        raise StoreError("El zip tiene demasiados archivos")
    total, out = 0, []
    for info in infos:
        raw = info.filename
        name = raw.replace("\\", "/")
        if (name.startswith("/") or ":" in name     # C:\…, flujos NTFS (a:b)
                or any(p == ".." for p in name.split("/"))):
            raise StoreError(f"Zip peligroso: ruta no permitida «{raw}»")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == stat.S_IFLNK:
            raise StoreError(f"Zip peligroso: enlace simbólico «{raw}»")
        total += info.file_size
        if total > MAX_UNCOMPRESSED:
            raise StoreError("El zip descomprimido es demasiado grande")
        out.append((info, name.rstrip("/") if info.is_dir() else name))
    return out


def _find_folder(entries: list[tuple[zipfile.ZipInfo, str]], subpath: str) -> str:
    """Carpeta del plugin dentro del zip ("" = raíz del zip)."""
    files = [n for i, n in entries if not i.is_dir() and n]
    if not files:
        raise StoreError("El zip está vacío")
    tops = {n.split("/", 1)[0] for n in files}
    root = tops.pop() if len(tops) == 1 and all("/" in n for n in files) else ""
    if subpath:
        target = f"{root}/{subpath}" if root else subpath
        if not any(n.startswith(target + "/") for n in files):
            raise StoreError(f"La carpeta «{subpath}» no existe en el repositorio")
        return target
    for marker in ("plugin.json", "plugin.py", "widget.js"):
        dirs = sorted({n.rsplit("/", 1)[0] if "/" in n else "" for n in files
                       if n.rsplit("/", 1)[-1] == marker},
                      key=lambda d: (d.count("/") if d else -1, d))
        if dirs:
            return dirs[0]
    raise StoreError("No parece un plugin de MiniDeck: no hay plugin.json, "
                     "plugin.py ni widget.js")


def _plugin_id(folder: str, root_name: str) -> str:
    base = folder.rsplit("/", 1)[-1] if folder else ""
    if not folder or "/" not in folder:
        # carpeta raíz del repo: nombre del repo sin el prefijo "minideck-"
        base = root_name
        for pre in ("minideck-", "minideck_"):
            if base.lower().startswith(pre):
                base = base[len(pre):]
    pid = base.lower()
    if not actions._ID_RE.match(pid):  # noqa: SLF001
        raise StoreError(f"Nombre de plugin no válido: «{pid}» (usa minúsculas, "
                         "números, - y _)")
    return pid


def _rmtree(path: Path) -> None:
    def onerr(func, p, _exc):   # archivos de solo lectura (Windows)
        try:
            os.chmod(p, stat.S_IWRITE)
            func(p)
        except OSError:
            pass
    if not path.exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=onerr)
    else:
        shutil.rmtree(path, onerror=onerr)


def _unregister(pid: str) -> None:
    """Quita las acciones de un plugin del registro (para recargar/borrar)."""
    for name in [a for a, o in actions.OWNERS.items() if o == pid]:
        actions.REGISTRY.pop(name, None)
        actions.OWNERS.pop(name, None)
        actions.META.pop(name, None)
        if name in actions.STATE_SOURCES:
            actions.STATE_SOURCES.remove(name)
    sys.modules.pop(f"minideck_plugins.{pid}", None)
    actions.PLUGINS.pop(pid, None)


def install(url: str) -> dict:
    src = parse_url(url)
    data = _fetch(src)
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise StoreError("Lo descargado no es un archivo .zip válido") from None
    with zf:
        entries = _safe_names(zf)
        folder = _find_folder(entries, src["subpath"])
        root_name = src["repo"]
        if not src["github"] and folder and "/" not in folder:
            root_name = re.sub(r"-(main|master)$", "", folder)
        pid = _plugin_id(folder, root_name)
        if (BUNDLED_PLUGINS_DIR / pid).exists():
            raise StoreError(f"«{pid}» es un plugin incluido con MiniDeck: no se puede "
                             "reemplazar desde la tienda.", 409)

        with _LOCK:
            USER_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
            tmp = USER_PLUGINS_DIR / f".tmp-{pid}-{uuid.uuid4().hex[:8]}"
            tmp.mkdir()
            try:
                prefix = folder + "/" if folder else ""
                base = tmp.resolve()
                for info, name in entries:
                    if info.is_dir() or not name.startswith(prefix):
                        continue
                    rel = name[len(prefix):]
                    target = (tmp / rel).resolve()
                    if base not in target.parents:          # doble comprobación
                        raise StoreError(f"Zip peligroso: ruta no permitida «{name}»")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(info) as fsrc, open(target, "wb") as fdst:
                        shutil.copyfileobj(fsrc, fdst)
                dest = USER_PLUGINS_DIR / pid
                old = None
                if dest.exists():
                    old = USER_PLUGINS_DIR / f".old-{pid}-{uuid.uuid4().hex[:8]}"
                    dest.replace(old)
                tmp.replace(dest)
            except BaseException:
                _rmtree(tmp)
                raise
            if old is not None:
                _rmtree(old)
            if pid in actions.PLUGINS:
                _unregister(pid)
            actions._load_plugin(dest)  # noqa: SLF001  funciona sin reiniciar
    info = plugin_info(pid)
    log.info("Plugin instalado: %s desde %s (%s)", pid, url, info["status"])
    if info["status"] == "loaded":
        msg = f"«{info['name']}» instalado y activo."
    elif info["status"] == "disabled":
        msg = f"«{info['name']}» instalado, pero está desactivado."
    else:
        msg = f"«{info['name']}» instalado, pero no se pudo activar: {info['error']}"
    if info["requires"]:
        msg += " Necesita: " + ", ".join(info["requires"]) + " (instálalos y reinicia)."
    return {"ok": True, "plugin": info, "requires": info["requires"], "message": msg}


def uninstall(pid: str) -> dict:
    with _LOCK:
        info = actions.PLUGINS.get(pid)
        if not info:
            raise StoreError("Ese plugin no está instalado", 404)
        if not info.get("user"):
            raise StoreError("Los plugins incluidos con MiniDeck no se pueden desinstalar "
                             "(puedes desactivarlos).")
        folder = Path(info["dir"])
        if folder.resolve().parent != USER_PLUGINS_DIR.resolve():
            raise StoreError("Carpeta de plugin inesperada")
        _unregister(pid)
        _rmtree(folder)
        # si tapaba a uno incluido con el mismo id, vuelve el incluido
        if (BUNDLED_PLUGINS_DIR / pid).is_dir():
            actions._load_plugin(BUNDLED_PLUGINS_DIR / pid)  # noqa: SLF001
    log.info("Plugin desinstalado: %s", pid)
    return {"ok": True, "message": f"«{info.get('name') or pid}» desinstalado."}


# --------------------------------------------------------------- rutas ----
async def _json(req: Request) -> dict:
    try:
        body = await req.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise StoreError("Petición no válida") from None
    if not isinstance(body, dict):
        raise StoreError("Petición no válida")
    return body


@router.post("/api/plugins/install")
async def store_install(req: Request):
    if not _is_local(req):
        return _err(_LOCAL_MSG, 403)
    try:
        body = await _json(req)
        url = body.get("url")
        if not isinstance(url, str) or not url.strip():
            raise StoreError("Falta la dirección del plugin")
        return JSONResponse(await _run(install, url))
    except StoreError as exc:
        return _err(str(exc), exc.status)


@router.delete("/api/plugins/{pid}")
async def store_uninstall(pid: str, req: Request):
    if not _is_local(req):
        return _err(_LOCAL_MSG, 403)
    try:
        return JSONResponse(await _run(uninstall, pid))
    except StoreError as exc:
        return _err(str(exc), exc.status)


@router.put("/api/plugins/{pid}/settings")
async def store_settings(pid: str, req: Request):
    try:
        if pid not in actions.PLUGINS:
            raise StoreError("Ese plugin no está instalado", 404)
        body = await _json(req)
        new = body.get("settings")
        if not isinstance(new, dict):
            raise StoreError("Faltan los ajustes")
        defaults = actions.PLUGINS[pid].get("settings") or {}
        if not isinstance(defaults, dict):
            defaults = {}
        cfg = _load_cfg()
        all_settings = cfg.get("pluginSettings")
        if not isinstance(all_settings, dict):
            all_settings = {}
        old = dict(all_settings.get(pid) or {})
        merged = dict(old)
        for key, value in new.items():
            if key not in defaults:
                raise StoreError(f"Ajuste desconocido: «{key}»")
            if is_secret(key) and value == MASK:
                continue          # el usuario no lo cambió: conservar el antiguo
            kind = _kind(defaults[key], value)
            if kind == "other":
                raise StoreError(f"«{key}» no se puede cambiar desde el Panel")
            merged[key] = _coerce(key, kind, value)
        all_settings[pid] = merged
        cfg["pluginSettings"] = all_settings
        await _run(_save_cfg, cfg)
        _, values = _settings_view(pid)
        return JSONResponse({"ok": True, "settings": values,
                             "message": "Ajustes guardados."})
    except StoreError as exc:
        return _err(str(exc), exc.status)
    except ValueError as exc:     # validate_config de main
        return _err(str(exc))


@router.post("/api/plugins/{pid}/enabled")
async def store_enabled(pid: str, req: Request):
    try:
        if pid not in actions.PLUGINS:
            raise StoreError("Ese plugin no está instalado", 404)
        body = await _json(req)
        enabled = body.get("enabled")
        if not isinstance(enabled, bool):
            raise StoreError("'enabled' debe ser true o false")
        cfg = _load_cfg()
        disabled = [d for d in (cfg.get("disabledPlugins") or []) if isinstance(d, str)]
        disabled = [d for d in disabled if d != pid]
        if not enabled:
            disabled.append(pid)
        cfg["disabledPlugins"] = sorted(set(disabled))
        await _run(_save_cfg, cfg)
        word = "activará" if enabled else "desactivará"
        return JSONResponse({"ok": True, "enabled": enabled, "restart": True,
                             "message": f"El plugin se {word} al reiniciar MiniDeck."})
    except StoreError as exc:
        return _err(str(exc), exc.status)
