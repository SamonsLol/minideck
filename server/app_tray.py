# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""MiniDeck — icono de bandeja (Windows y Linux).

Arranca el servidor en un hilo y pone un icono en la bandeja del sistema con:
Mostrar QR, Abrir en este equipo, Carpeta de datos, Ver log, Salir.
Es el punto de entrada del .exe de Windows (ver build/minideck-win.spec).

Desarrollo:  python app_tray.py   (desde server/, requiere pystray y Pillow)
"""
import os
import subprocess
import sys
import threading
import webbrowser

# App sin consola (PyInstaller console=False): stdout/stderr son None y
# uvicorn falla al configurar sus logs. Redirigir a nulo ANTES de importar.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115

import pystray
import uvicorn
from PIL import Image

import main as mdk
from paths import DATA_DIR, FROZEN, RES_DIR, SERVER_DIR

_server: uvicorn.Server | None = None


def _icon_image() -> Image.Image:
    base = RES_DIR if FROZEN else SERVER_DIR.parent
    path = base / "assets" / "minideck.ico"
    try:
        return Image.open(path)
    except OSError:  # sin icono: un cuadrado de color
        return Image.new("RGB", (64, 64), "#60a5fa")


def _serve() -> None:
    global _server
    ssl_kw = ({"ssl_certfile": str(mdk.CERT_FILE), "ssl_keyfile": str(mdk.KEY_FILE)}
              if mdk.USE_TLS else {})
    _server = uvicorn.Server(uvicorn.Config(mdk.app, host=mdk.HOST, port=mdk.PORT,
                                            log_level="warning", **ssl_kw))
    _server.install_signal_handlers = lambda: None   # no estamos en el hilo main
    _server.run()


def _open_path(path) -> None:
    path = str(path)
    if sys.platform.startswith("win"):
        os.startfile(path)  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", path])


def _local(path: str = "") -> str:
    return f"{mdk.SCHEME}://localhost:{mdk.PORT}{path}"


def _log_thread_errors(args) -> None:
    """Sin consola, un error en un hilo desaparecería: mandarlo al log."""
    mdk.log.error("Error en el hilo %s", args.thread.name if args.thread else "?",
                  exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def main() -> None:
    threading.excepthook = _log_thread_errors
    threading.Thread(target=_serve, daemon=True, name="minideck-server").start()

    def quit_(icon, _item):
        if _server:
            _server.should_exit = True
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem("Mostrar QR", lambda: webbrowser.open(_local("/qr")), default=True),
        pystray.MenuItem("Abrir en este equipo", lambda: webbrowser.open(_local("/"))),
        pystray.MenuItem("Panel de widgets", lambda: webbrowser.open(_local("/panel.html"))),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Carpeta de datos", lambda: _open_path(DATA_DIR)),
        pystray.MenuItem("Ver log", lambda: _open_path(mdk.LOG_FILE)),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(f"MiniDeck {mdk.__version__}", None, enabled=False),
        pystray.MenuItem("Salir", quit_),
    )
    pystray.Icon("MiniDeck", _icon_image(), "MiniDeck", menu).run()


if __name__ == "__main__":
    main()
