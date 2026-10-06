# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""
Autenticación por token de emparejamiento.

MiniDeck ejecuta comandos en tu equipo, así que NADIE en la red debe poder
usarlo sin permiso. Al arrancar se genera (una sola vez) un token aleatorio
que se guarda en CONFIG_DIR/auth_token. El móvil lo recibe escaneando el QR
de /qr (solo visible desde el propio equipo) y lo guarda en el navegador.

El token se acepta en:
  - cabecera  X-MiniDeck-Token   (fetch)
  - query     ?token=...         (WebSocket, <img>, enlaces del QR)

Variables de entorno:
  MINIDECK_TOKEN=...      fija el token (útil en Docker / varios equipos)
  MINIDECK_NO_AUTH=1      desactiva la autenticación (NO recomendado)
"""
import hmac
import ipaddress
import os
import secrets
from urllib.parse import urlsplit

from paths import TOKEN_PATH

HEADER = "x-minideck-token"
AUTH_DISABLED = os.environ.get("MINIDECK_NO_AUTH", "").strip() in ("1", "true", "yes")


def _load_or_create() -> str:
    env = os.environ.get("MINIDECK_TOKEN", "").strip()
    if env:
        return env
    try:
        tok = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if tok:
            return tok
    except OSError:
        pass
    tok = secrets.token_urlsafe(16)  # 128 bits, 22 caracteres (se puede teclear)
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(tok, encoding="utf-8")
    try:
        os.chmod(TOKEN_PATH, 0o600)
    except OSError:
        pass
    return tok


TOKEN = _load_or_create()


def check(candidate: str | None) -> bool:
    if AUTH_DISABLED:
        return True
    return bool(candidate) and hmac.compare_digest(candidate, TOKEN)


COOKIE = "minideck_token"


def token_from(headers, query_params, cookies=None) -> str | None:
    """Cabecera (fetch), ?token= (WebSocket, <img>) o cookie (modo sin JS).
    La cookie es HttpOnly + SameSite=Strict, y los POST/WS exigen además el
    mismo origen, así que no abre la puerta a CSRF."""
    return (headers.get(HEADER) or query_params.get("token")
            or (cookies or {}).get(COOKIE))


def is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def local_request(client_host: str | None, headers) -> bool:
    """Petición hecha desde este equipo Y dirigida a localhost. Comprobar
    también Host evita ataques de DNS rebinding (evil.com → 127.0.0.1)."""
    host = (headers.get("host") or "").lower()
    if host.startswith("["):                       # [::1]:8765
        hostname = host[1:host.find("]")] if "]" in host else host
    else:
        hostname = host.rsplit(":", 1)[0]
    return (is_loopback(client_host) and is_loopback(hostname)
            and same_origin(headers))


def same_origin(headers) -> bool:
    """Bloquea peticiones lanzadas por OTRAS webs desde el navegador
    (CSRF / cross-site WebSocket hijacking). Sin cabecera Origin (curl,
    scripts) se permite: el token sigue siendo obligatorio."""
    origin = headers.get("origin")
    if not origin or origin == "null":
        return origin is None
    return urlsplit(origin).netloc.lower() == (headers.get("host") or "").lower()
