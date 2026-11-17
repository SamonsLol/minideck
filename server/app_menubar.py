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

import desktop_language
import main as mdk  # server/main.py — comparte app, PORT, local_ip

_windows = []        # mantener referencias a las ventanas del QR (evitar GC)


_TEXT = {
    "en": {
        "show_qr": "Show QR code", "open": "Open on this Mac", "copy": "Copy URL",
        "login": "Launch at login", "language": "Language", "quit": "Quit",
        "copied": "URL copied", "login_app_only": "Available only in the packaged app (.app).",
        "scan_help": "Scan it with your iPhone camera\nand open it in Safari",
    },
    "es": {
        "show_qr": "Mostrar QR", "open": "Abrir en este Mac", "copy": "Copiar URL",
        "login": "Arrancar al iniciar sesión", "language": "Idioma", "quit": "Salir",
        "copied": "URL copiada", "login_app_only": "Disponible solo en la app empaquetada (.app).",
        "scan_help": "Escanéalo con la cámara del iPhone\ny abre en Safari",
    },
}


def _text(language: str, key: str) -> str:
    return _TEXT[language][key]


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
def show_qr_window(language: str):
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
    _label(NSMakeRect(20, 24, W - 40, 44), _text(language, "scan_help"), 12, secondary=True)

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


def set_login_item(enable: bool, language: str):
    app = _app_path()
    if not app:
        rumps.alert(_text(language, "login_app_only"))
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
        self._language = desktop_language.get_language()
        self._qr = rumps.MenuItem("", callback=self.on_qr)
        self._open = rumps.MenuItem("", callback=self.on_open)
        self._copy = rumps.MenuItem("", callback=self.on_copy)
        self._login = rumps.MenuItem("", callback=self.on_login)
        self._login.state = is_login_item()
        self._language_menu = rumps.MenuItem("")
        self._english = rumps.MenuItem("English", callback=self.on_english)
        self._spanish = rumps.MenuItem("Español", callback=self.on_spanish)
        self._language_menu.add(self._english)
        self._language_menu.add(self._spanish)
        self._quit = rumps.MenuItem("", callback=self.on_quit)
        self._refresh_menu()
        self.menu = [
            self._qr,
            self._open,
            self._copy,
            None,
            self._language_menu,
            self._login,
            None,
            self._quit,
        ]

    def _refresh_menu(self):
        self._qr.title = _text(self._language, "show_qr")
        self._open.title = _text(self._language, "open")
        self._copy.title = _text(self._language, "copy")
        self._login.title = _text(self._language, "login")
        self._language_menu.title = _text(self._language, "language")
        self._quit.title = _text(self._language, "quit")
        self._english.state = self._language == "en"
        self._spanish.state = self._language == "es"

    def _set_language(self, language: str):
        self._language = desktop_language.set_language(language)
        self._refresh_menu()

    def on_qr(self, _):
        show_qr_window(self._language)

    def on_open(self, _):
        subprocess.run(["open", f"{mdk.SCHEME}://localhost:{mdk.PORT}?lang={self._language}"],
                       check=False)

    def on_copy(self, _):
        subprocess.run(["pbcopy"], input=_url(), text=True, check=False)
        rumps.notification("MiniDeck", _text(self._language, "copied"), _url())

    def on_login(self, item):
        item.state = not item.state
        set_login_item(bool(item.state), self._language)

    def on_english(self, _):
        self._set_language("en")

    def on_spanish(self, _):
        self._set_language("es")

    def on_quit(self, _):
        rumps.quit_application()


def run():
    threading.Thread(target=_serve, daemon=True).start()
    MiniDeckApp().run()


if __name__ == "__main__":
    run()
