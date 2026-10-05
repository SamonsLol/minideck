"""
Rutas de MiniDeck, en un solo sitio.

- RES_DIR:    recursos de solo lectura (frontend, plugins incluidos, config
              por defecto). En la app empaquetada viven en sys._MEIPASS.
- DATA_DIR:   carpeta de datos del usuario, por sistema operativo:
                Windows: %APPDATA%\\MiniDeck
                macOS:   ~/Library/Application Support/MiniDeck
                Linux:   ~/.config/minideck  (o $XDG_CONFIG_HOME/minideck)
- CONFIG_DIR: dónde se guardan deck.json, el token y discord.json.
              En desarrollo es server/config/ (cómodo para editar a mano);
              empaquetado es DATA_DIR. Se puede forzar con MINIDECK_CONFIG_DIR.
"""
import os
import shutil
import sys
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
SERVER_DIR = Path(__file__).resolve().parent


def _data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
        return base / "MiniDeck"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "MiniDeck"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "minideck"


if FROZEN:
    RES_DIR = Path(sys._MEIPASS)  # noqa: SLF001
    FRONTEND_DIR = RES_DIR / "frontend"
    BUNDLED_PLUGINS_DIR = RES_DIR / "plugins"
    DEFAULTS_DIR = RES_DIR / "config"
else:
    RES_DIR = SERVER_DIR
    FRONTEND_DIR = SERVER_DIR.parent / "frontend"
    BUNDLED_PLUGINS_DIR = SERVER_DIR / "plugins"
    DEFAULTS_DIR = SERVER_DIR / "config"

DATA_DIR = _data_dir()
CONFIG_DIR = Path(os.environ.get("MINIDECK_CONFIG_DIR")
                  or (DATA_DIR if FROZEN else SERVER_DIR / "config"))
# Plugins de terceros: se instalan aquí sin tocar el código de MiniDeck.
USER_PLUGINS_DIR = Path(os.environ.get("MINIDECK_PLUGINS_DIR") or DATA_DIR / "plugins")

CONFIG_PATH = CONFIG_DIR / "deck.json"
DEFAULT_CONFIG_PATH = DEFAULTS_DIR / "deck.default.json"
TOKEN_PATH = CONFIG_DIR / "auth_token"
DISCORD_CFG_PATH = CONFIG_DIR / "discord.json"

CERT_DIR = DATA_DIR / "certs"
CERT_FILE = CERT_DIR / "cert.pem"
KEY_FILE = CERT_DIR / "key.pem"


def ensure_dirs() -> None:
    """Crea las carpetas de usuario y siembra deck.json la primera vez."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USER_PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists() and DEFAULT_CONFIG_PATH.exists():
        shutil.copy(DEFAULT_CONFIG_PATH, CONFIG_PATH)
