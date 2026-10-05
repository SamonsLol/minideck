"""Acción HTTP genérica: dispara webhooks / APIs (n8n, Home Assistant,
OBS con puente HTTP, IFTTT, etc.). Multiplataforma."""
import json
import urllib.request

from . import action


@action("http_request")
def http_request(params: dict):
    """Hace una petición HTTP.
    params: {"url": "...", "method": "POST", "body": {...} | "texto",
             "headers": {"Authorization": "Bearer ..."}}
    """
    url = params.get("url")
    if not url:
        raise ValueError("Falta el parámetro 'url'")
    method = (params.get("method") or "GET").upper()
    headers = dict(params.get("headers") or {})
    body = params.get("body")
    data = None
    if isinstance(body, (dict, list)):
        data = json.dumps(body).encode()
        headers.setdefault("Content-Type", "application/json")
    elif isinstance(body, str):
        data = body.encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return {"message": f"HTTP {method} → {r.status}"}
    except urllib.error.HTTPError as e:
        return {"message": f"HTTP {method} → {e.code}"}
