# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Punto de entrada al instalar con pip/pipx:  `minideck` (o `minideck --port 9000`).

El servidor vive en minideck_app/server con sus módulos de primer nivel
(main, actions…), porque los plugins hacen `from actions import action`.
Para no ensuciar site-packages, esa carpeta se añade a sys.path solo aquí.
"""
import os
import sys
from pathlib import Path


def _server_dir() -> Path:
    return Path(__file__).resolve().parent / "minideck_app" / "server"


def main() -> None:
    # instalado: la config va a la carpeta de datos del usuario, no a site-packages
    os.environ.setdefault("MINIDECK_INSTALLED", "1")
    sys.path.insert(0, str(_server_dir()))
    import main as server  # noqa: PLC0415  (después de ajustar sys.path)
    server.main()


def tray() -> None:
    """`minideck-tray`: icono de bandeja (Windows/Linux; requiere pystray)."""
    os.environ.setdefault("MINIDECK_INSTALLED", "1")
    sys.path.insert(0, str(_server_dir()))
    import app_tray  # noqa: PLC0415
    app_tray.main()


if __name__ == "__main__":
    main()
