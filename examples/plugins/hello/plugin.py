# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Plugin de ejemplo «hello»: cópialo como punto de partida.

Instálalo copiando esta carpeta a la carpeta de plugins del usuario
(ver docs/PLUGINS.md) y reinicia MiniDeck.
"""
import threading

from actions import action, plugin_settings

_lock = threading.Lock()   # las acciones corren en hilos: protege el estado
_count = 0


@action("hello_say")
def hello_say(params: dict):
    """Saluda y suma 1 al contador. params: {"name": "Samons"}"""
    global _count
    with _lock:
        _count += 1
    greeting = plugin_settings("hello")["greeting"]
    return {"message": f"{greeting} {params.get('name', '')}".strip(),
            "state": {"hello": {"count": _count}}}


@action("hello_get", state=True)
def hello_get(params: dict):
    """Fuente de estado: MiniDeck la consulta cada segundo. Debe ser rápida."""
    return {"state": {"hello": {"count": _count}}}
