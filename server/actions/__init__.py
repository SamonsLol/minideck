# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""
Sistema de acciones y plugins.

Cada módulo de este paquete registra sus acciones con el decorador @action.
Además, MiniDeck carga plugins desde dos carpetas:

    server/plugins/<id>/        ← plugins incluidos con MiniDeck
    <DATA_DIR>/plugins/<id>/    ← plugins del usuario / de la comunidad
                                  (tienen prioridad si el id coincide)

Anatomía de un plugin (todo opcional salvo tener al menos un archivo):

    mi_plugin/
        plugin.json   ← manifiesto: nombre, versión, plataformas, ajustes…
        plugin.py     ← acciones Python (usa: from actions import action)
        widget.js     ← widget de frontend (se inyecta solo)
        widget.css    ← estilos del widget

Contrato de una acción:
    - Recibe: params (dict) con los parámetros del botón.
    - Devuelve: None, o un dict opcional con:
        message: str   → texto para mostrar en el cliente
        state:   dict  → estado a difundir a todos los clientes
    - Si algo falla, lanza una excepción: el servidor la captura y la reporta.

Fuentes de estado: registra con @action("nombre_get", state=True) y el
vigilante del servidor la sondeará cada segundo y difundirá sus cambios.

Guía completa: docs/PLUGINS.md
"""
import importlib
import importlib.util
import json
import logging
import pkgutil
import re
import sys
from pathlib import Path

from paths import BUNDLED_PLUGINS_DIR, CONFIG_PATH, USER_PLUGINS_DIR
from version import PLUGIN_API, __version__

log = logging.getLogger("minideck.actions")

REGISTRY: dict[str, callable] = {}
STATE_SOURCES: list[str] = []
# Dueño de cada acción: "core" o el id del plugin que la registró.
OWNERS: dict[str, str] = {}
# Plugins descubiertos: id → info (manifiesto + estado de carga).
PLUGINS: dict[str, dict] = {}

_current_owner = "core"
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")
FRONTEND_FILES = ("widget.css", "widget.js")


# Metadatos por acción: descripción, ejemplo de params, esquema y timeout.
META: dict[str, dict] = {}
DEFAULT_TIMEOUT = 30.0   # segundos; una acción colgada no bloquea al cliente

_TYPES = {"str": str, "int": int, "float": (int, float), "bool": bool,
          "list": list, "dict": dict}


def _doc_info(fn) -> tuple[str, str]:
    """Primera línea del docstring y el ejemplo "params: {...}" si lo hay."""
    doc = (fn.__doc__ or "").strip()
    summary = doc.splitlines()[0].strip() if doc else ""
    m = re.search(r"params:\s*(\{.*?\}|\{\})(?:\s|$)", doc, re.S)
    return summary, (m.group(1).strip() if m else "")


def action(name: str, state: bool = False, schema: dict | None = None,
           timeout: float | None = None):
    """Decorador para registrar una acción por nombre.

    state=True   → se sondea cada segundo como fuente de estado.
    schema       → validación de params antes de ejecutar, p. ej.
                   {"level": {"type": "int", "min": 0, "max": 100},
                    "keys":  {"type": "str", "required": True},
                    "mode":  {"type": "str", "choices": ["a", "b"]},
                    "$oneOf": [["path", "app"]]}   # al menos uno de ellos
    timeout      → segundos máximos (por defecto DEFAULT_TIMEOUT).
    """
    def deco(fn):
        prev = OWNERS.get(name)
        if prev and prev != _current_owner and _current_owner != "core":
            log.warning("Plugin '%s' reemplaza la acción '%s' (antes de '%s')",
                        _current_owner, name, prev)
        REGISTRY[name] = fn
        OWNERS[name] = _current_owner
        summary, example = _doc_info(fn)
        META[name] = {"doc": summary, "example": example, "schema": schema or {},
                      "timeout": timeout or DEFAULT_TIMEOUT, "state": state}
        if state and name not in STATE_SOURCES:
            STATE_SOURCES.append(name)
        return fn
    return deco


def validate_params(name: str, params: dict) -> None:
    """Comprueba params contra el esquema de la acción. Lanza ValueError con
    un mensaje claro (se muestra tal cual en el móvil)."""
    schema = (META.get(name) or {}).get("schema") or {}
    for group in schema.get("$oneOf", []):
        if not any(params.get(k) not in (None, "") for k in group):
            raise ValueError(f"Falta uno de: {', '.join(group)}")
    for key, rule in schema.items():
        if key.startswith("$"):
            continue
        val = params.get(key)
        if val is None or val == "":
            if rule.get("required"):
                raise ValueError(f"Falta el parámetro '{key}'")
            continue
        typ = rule.get("type")
        if typ in ("int", "float") and isinstance(val, str):
            try:  # "50" desde un formulario → 50
                val = int(val) if typ == "int" else float(val)
                params[key] = val
            except ValueError:
                raise ValueError(f"'{key}' debe ser un número") from None
        if typ and not isinstance(val, _TYPES[typ]) or (typ in ("int", "float")
                                                         and isinstance(val, bool)):
            raise ValueError(f"'{key}' debe ser de tipo {typ}")
        if "min" in rule and val < rule["min"] or "max" in rule and val > rule["max"]:
            raise ValueError(f"'{key}' debe estar entre {rule.get('min')} y {rule.get('max')}")
        if "choices" in rule and val not in rule["choices"]:
            raise ValueError(f"'{key}' debe ser uno de: {', '.join(map(str, rule['choices']))}")


def describe_actions() -> dict:
    """Para el editor: qué hace cada acción y qué parámetros espera."""
    return {n: {"doc": m["doc"], "example": m["example"], "schema": m["schema"],
                "owner": OWNERS.get(n, "core")}
            for n, m in sorted(META.items()) if not m["state"]}


# --------------------------------------------------------------- ajustes ---
_cfg_cache = {"mtime": None, "data": {}}


def _deck() -> dict:
    """deck.json con caché por mtime (los plugins lo consultan a menudo)."""
    try:
        mtime = CONFIG_PATH.stat().st_mtime
    except OSError:
        return {}
    if mtime != _cfg_cache["mtime"]:
        try:
            _cfg_cache["data"] = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            _cfg_cache["mtime"] = mtime
        except (OSError, json.JSONDecodeError):
            pass
    return _cfg_cache["data"]


def plugin_settings(plugin_id: str) -> dict:
    """Ajustes de un plugin: valores por defecto de su plugin.json
    ("settings") sobrescritos por deck.json → "pluginSettings" → <id>."""
    defaults = dict((PLUGINS.get(plugin_id) or {}).get("settings") or {})
    user = (_deck().get("pluginSettings") or {}).get(plugin_id) or {}
    return {**defaults, **user}


def disabled_plugins() -> set[str]:
    return set(_deck().get("disabledPlugins") or [])


# ------------------------------------------------------------- manifiesto --
def _version_tuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", v)[:3])


def _read_manifest(d: Path) -> dict:
    info = {"id": d.name, "name": d.name, "version": "0.0.0", "author": "",
            "description": "", "homepage": "", "platforms": [],
            "requires": [], "settings": {}, "minideck": "", "api": PLUGIN_API}
    mf = d / "plugin.json"
    if mf.exists():
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                info.update({k: v for k, v in data.items() if k in info})
        except (OSError, json.JSONDecodeError) as exc:
            info["error"] = f"plugin.json inválido: {exc}"
    info["id"] = d.name  # el id SIEMPRE es el nombre de la carpeta
    return info


def _incompatibility(info: dict) -> str | None:
    plats = info.get("platforms") or []
    if plats and not any(sys.platform.startswith(p) for p in plats):
        return f"solo para {', '.join(plats)}"
    need = info.get("minideck") or ""
    if need and _version_tuple(need) > _version_tuple(__version__):
        return f"requiere MiniDeck {need} (tienes {__version__})"
    if int(info.get("api") or PLUGIN_API) > PLUGIN_API:
        return f"usa la API de plugins v{info['api']} (soportada: v{PLUGIN_API})"
    return None


# ----------------------------------------------------------------- carga ---
def _discover() -> list[Path]:
    """Carpetas de plugin; las del usuario primero (ganan si el id coincide)."""
    seen, out = set(), []
    for root in (USER_PLUGINS_DIR, BUNDLED_PLUGINS_DIR):
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir() or d.name.startswith((".", "_")) or d.name in seen:
                continue
            if not _ID_RE.match(d.name):
                log.warning("Plugin ignorado: '%s' (usa minúsculas, números, - y _)", d.name)
                continue
            seen.add(d.name)
            out.append(d)
    return out


def _load_plugin(d: Path) -> None:
    global _current_owner
    info = _read_manifest(d)
    info["dir"] = str(d)
    info["user"] = d.parent.resolve() == USER_PLUGINS_DIR.resolve()
    info["frontend"] = [f for f in FRONTEND_FILES if (d / f).exists()]
    info["actions"] = []
    PLUGINS[info["id"]] = info

    if info.get("error"):
        info["status"] = "error"
        return
    if info["id"] in disabled_plugins():
        info["status"] = "disabled"
        return
    reason = _incompatibility(info)
    if reason:
        info["status"], info["error"] = "skipped", reason
        return

    py = d / "plugin.py"
    if py.exists():
        _current_owner = info["id"]
        try:
            name = f"minideck_plugins.{info['id']}"
            spec = importlib.util.spec_from_file_location(name, py)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[name] = mod
            spec.loader.exec_module(mod)
        except ImportError as exc:
            hint = (f" → pip install {' '.join(info['requires'])}"
                    if info["requires"] else "")
            info["status"], info["error"] = "error", f"Falta dependencia: {exc}{hint}"
            log.warning("Plugin '%s': %s", info["id"], info["error"])
            return
        except Exception as exc:  # noqa: BLE001
            info["status"], info["error"] = "error", f"{type(exc).__name__}: {exc}"
            log.warning("Plugin '%s' falló al cargar: %s", info["id"], info["error"])
            return
        finally:
            _current_owner = "core"
    info["actions"] = sorted(a for a, o in OWNERS.items() if o == info["id"])
    info["status"] = "loaded"
    log.info("Plugin cargado: %s %s", info["id"], info["version"])


def load_all_actions() -> None:
    """Importa los módulos del paquete y después los plugins."""
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_"):
            continue
        try:
            importlib.import_module(f"{__name__}.{mod.name}")
        except Exception as exc:  # noqa: BLE001
            # Los módulos de otra plataforma se saltan en silencio; el resto
            # (p. ej. una dependencia sin instalar) sí merece un aviso.
            lvl = logging.DEBUG if "solo aplica" in str(exc) else logging.WARNING
            log.log(lvl, "Módulo de acciones '%s' no disponible: %s", mod.name, exc)

    for d in _discover():
        _load_plugin(d)


def frontend_assets() -> list[dict]:
    """Assets js/css de los plugins activos, para inyectar en el cliente."""
    out = []
    for info in PLUGINS.values():
        if info.get("status") != "loaded":
            continue
        for f in info["frontend"]:
            out.append({"type": f.rsplit(".", 1)[1],
                        "url": f"/plugins/{info['id']}/{f}?v={info['version']}"})
    return out


def plugin_file(plugin_id: str, filename: str) -> Path | None:
    """Ruta segura a un archivo estático de un plugin (sin path traversal)."""
    info = PLUGINS.get(plugin_id)
    if not info:
        return None
    base = Path(info["dir"]).resolve()
    target = (base / filename).resolve()
    if base not in target.parents or not target.is_file():
        return None
    if target.suffix.lower() not in (".js", ".css", ".png", ".svg", ".jpg",
                                     ".jpeg", ".webp", ".json", ".woff2"):
        return None
    return target
