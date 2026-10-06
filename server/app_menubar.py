# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""MiniDeck — app de barra de menú para macOS.

Arranca el servidor (uvicorn) en un hilo y pone un icono en la barra de menú
con: Mostrar QR, Abrir en este Mac, Copiar URL, Arrancar al iniciar sesión, Salir.

Desarrollo:   ../buildenv/bin/python app_menubar.py   (desde la carpeta server/)
Empaquetado:  este módulo es el entry point del .app (ver build/minideck.spec).
"""
import asyncio
import io
import subprocess
import sys
import threading
from pathlib import Path

import rumps
import segno
import uvicorn

import main as mdk  # server/main.py — comparte app, PORT, local_ip

_windows = []        # mantener referencias a las ventanas del QR (evitar GC)


# ----------------------------------------------------------------- servidor --
def _serve():
    ssl_kw = ({"ssl_certfile": str(mdk.CERT_FILE), "ssl_keyfile": str(mdk.KEY_FILE)}
              if mdk.USE_TLS else {})
    config = uvicorn.Config(mdk.app, host="0.0.0.0", port=mdk.PORT,
                            log_level="warning", **ssl_kw)
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None   # no estamos en el hilo main
    asyncio.run(server.serve())


def _url() -> str:
    # incluye el token de emparejamiento: quien escanee el QR queda autorizado
    return mdk.pair_url()


def _qr_png(url: str, scale: int = 8) -> bytes:
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="png", scale=scale, border=3,
                                    dark="#111111", light="#ffffff")
    return buf.getvalue()


# ------------------------------------------------------------- ventana del QR
def show_qr_window():
    from AppKit import (
        NSApp,
        NSBackingStoreBuffered,
        NSColor,
        NSFont,
        NSImage,
        NSImageView,
        NSTextField,
        NSWindow,
        NSWindowStyleMaskClosable,
        NSWindowStyleMaskTitled,
    )
    from Foundation import NSData, NSMakeRect
    url = _url()
    png = _qr_png(url)
    data = NSData.dataWithBytes_length_(png, len(png))
    img = NSImage.alloc().initWithData_(data)

    W, H = 340, 440
    win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, W, H),
        NSWindowStyleMaskTitled | NSWindowStyleMaskClosable,
        NSBackingStoreBuffered, False)
    win.setTitle_("MiniDeck — QR")
    win.center()
    content = win.contentView()

    iv = NSImageView.alloc().initWithFrame_(NSMakeRect(20, 118, 300, 300))
    iv.setImage_(img)
    content.addSubview_(iv)

    def _label(rect, text, size, mono=False, secondary=False):
        f = NSTextField.alloc().initWithFrame_(rect)
        f.setStringValue_(text)
        f.setBezeled_(False)
        f.setEditable_(False)
        f.setSelectable_(True)
        f.setDrawsBackground_(False)
        f.setAlignment_(2)   # centrado
        f.setFont_(NSFont.monospacedSystemFontOfSize_weight_(size, 0) if mono
                   else NSFont.systemFontOfSize_(size))
        if secondary:
            f.setTextColor_(NSColor.secondaryLabelColor())
        content.addSubview_(f)
        return f

    _label(NSMakeRect(0, 78, W, 26), mdk.base_url(), 15, mono=True)
    _label(NSMakeRect(20, 24, W - 40, 44),
           "Escanéalo con la cámara del iPhone\ny abre en Safari", 12, secondary=True)

    win.makeKeyAndOrderFront_(None)
    win.setLevel_(3)   # flotante por encima
    NSApp.activateIgnoringOtherApps_(True)
    _windows.append(win)


# --------------------------------------------------------- arranque al login
def _app_path():
    """Ruta del .app si está empaquetado; None en desarrollo."""
    for p in Path(sys.executable).resolve().parents:
        if p.suffix == ".app":
            return str(p)
    return None


def is_login_item() -> bool:
    if not _app_path():
        return False
    r = subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to get the name of every login item'],
        capture_output=True, text=True)
    return "MiniDeck" in (r.stdout or "")


def set_login_item(enable: bool):
    app = _app_path()
    if not app:
        rumps.alert("Disponible solo en la app empaquetada (.app).")
        return
    if enable:
        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to make login item at end '
             f'with properties {{path:"{app}", hidden:true}}'], check=False)
    else:
        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events" to delete '
             '(every login item whose name is "MiniDeck")'], check=False)


def _asset(name: str) -> str | None:
    """Ruta de un recurso de assets/ (en el .app están en sys._MEIPASS)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    path = base / "assets" / name
    return str(path) if path.exists() else None


# ----------------------------------------------------------------- menú -----
class MiniDeckApp(rumps.App):
    def __init__(self):
        # icono de la lamparita como "plantilla": macOS lo pinta claro u oscuro
        # según la barra de menú (como los iconos del sistema)
        icon = _asset("menubar-template.png")
        super().__init__("MiniDeck", title=None if icon else "MiniDeck", icon=icon,
                         template=True, quit_button=None)
        self._login = rumps.MenuItem("Arrancar al iniciar sesión",
                                     callback=self.on_login)
        self._login.state = is_login_item()
        self.menu = [
            rumps.MenuItem("Mostrar QR", callback=self.on_qr),
            rumps.MenuItem("Abrir en este Mac", callback=self.on_open),
            rumps.MenuItem("Copiar URL", callback=self.on_copy),
            None,
            self._login,
            None,
            rumps.MenuItem("Salir", callback=self.on_quit),
        ]

    def on_qr(self, _):
        show_qr_window()

    def on_open(self, _):
        subprocess.run(["open", f"{mdk.SCHEME}://localhost:{mdk.PORT}"], check=False)

    def on_copy(self, _):
        subprocess.run(["pbcopy"], input=_url(), text=True, check=False)
        rumps.notification("MiniDeck", "URL copiada", _url())

    def on_login(self, item):
        item.state = not item.state
        set_login_item(bool(item.state))

    def on_quit(self, _):
        rumps.quit_application()


def run():
    threading.Thread(target=_serve, daemon=True).start()
    MiniDeckApp().run()


if __name__ == "__main__":
    run()
