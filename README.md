# MiniDeck

[![CI](https://github.com/SamonsLol/minideck/actions/workflows/ci.yml/badge.svg)](https://github.com/SamonsLol/minideck/actions/workflows/ci.yml)
[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Plataformas](https://img.shields.io/badge/plataformas-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)

Convierte tu móvil en un **Stream Deck** para tu PC o Mac. Sin app que instalar en el teléfono: es una PWA que abres en el navegador. El servidor es Python (FastAPI + WebSocket) y el frontend es HTML/CSS/JS puro, sin build.

> **English:** MiniDeck turns your phone into a Stream Deck–style controller for your Windows/macOS/Linux computer. Python server + zero-build PWA, plugin system, licensed under AGPL-3.0-or-later. Docs are in Spanish; issues and PRs in English are welcome.

## Qué hace

- **Botones** para atajos de teclado, abrir apps/webs, comandos, macros, webhooks (n8n, Home Assistant…), apagar/bloquear, etc.
- **Widgets en vivo**: volumen, mezclador por app (Windows), *Now Playing* con carátula, Discord (mute/sordina y quién habla), CPU/RAM, clima, Git, Docker…
- **Editor visual** desde el propio móvil: páginas, iconos (Lucide), colores, arrastrar y soltar.
- **Perfiles por app** (macOS): cambia de página según la app activa.
- **Plugins** en Python + JS, y widgets personalizados desde el Panel de Control (`/panel.html`).
- **Emparejamiento seguro** por QR: nadie más en tu red puede controlar tu equipo.

## Inicio rápido

Requisitos: Python 3.10+ y el móvil en la **misma red WiFi** que el equipo.

```bash
git clone https://github.com/SamonsLol/minideck.git
cd minideck
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt
cd server
python main.py
```

En la consola verás:

```
  MiniDeck 1.0.0 corriendo
  En este equipo:  http://localhost:8765
  QR para el móvil: http://localhost:8765/qr
  Desde el móvil:  http://192.168.1.50:8765  (código: …)
```

1. En el equipo abre **http://localhost:8765/qr**.
2. Escanea el QR con la cámara del móvil. Se abre MiniDeck ya **emparejado**.
3. *Compartir → Añadir a pantalla de inicio* para usarlo a pantalla completa.

**Windows:** doble clic en `MiniDeck.bat` lo arranca sin consola y con icono en la bandeja (clic derecho → Mostrar QR / Salir). La primera vez, permite el acceso de Python a **redes privadas** en el Firewall.

**macOS:** ver [README_MAC.md](README_MAC.md) (permisos de Accesibilidad, app de barra de menú `.app`, HTTPS para Android).

## Seguridad

MiniDeck puede ejecutar comandos en tu equipo, así que:

- Todas las peticiones a `/api` y `/ws` exigen un **token de emparejamiento** (se genera solo la primera vez y se guarda en `auth_token`, en la carpeta de config).
- El QR y el token solo se muestran **desde el propio equipo** (`localhost`).
- **No compartas el QR ni el código.** Para revocar todos los dispositivos, borra el archivo `auth_token` y reinicia: se generará uno nuevo.
- No expongas el puerto 8765 a Internet (nada de *port forwarding*). Si necesitas acceso remoto, usa una VPN como Tailscale o WireGuard.

Más detalles y cómo reportar vulnerabilidades: [SECURITY.md](SECURITY.md).

## Configurar el deck

El deck vive en `deck.json`:

| Modo | Ubicación |
|---|---|
| Desde el código (`python main.py`) | `server/config/deck.json` |
| App empaquetada | Windows `%APPDATA%\MiniDeck\` · macOS `~/Library/Application Support/MiniDeck/` · Linux `~/.config/minideck/` |

La primera vez se crea a partir de `server/config/deck.default.json`. Lo más cómodo es editarlo desde el móvil con el botón ✎, pero también puedes editar el JSON a mano: al guardar, todos los clientes se actualizan solos.

```json
{
  "id": "btn_unico",
  "label": "Mi botón",
  "icon": "lucide:gamepad-2",
  "color": "#60a5fa",
  "action": "hotkey",
  "params": { "keys": "ctrl+shift+m" }
}
```

## Acciones incluidas

| Acción | Params | Plataformas |
|---|---|---|
| `hotkey` | `{"keys": "ctrl+shift+m"}` | Win, Mac |
| `type_text` | `{"text": "hola"}` | Win, Mac |
| `launch` | `{"path": "..."}` · Mac: `{"app": "Safari"}` | todas |
| `command` | `{"cmd": "...", "shell": "powershell"}` | todas |
| `website` | `{"url": "https://..."}` | todas |
| `http_request` | `{"url", "method", "body", "headers"}` | todas |
| `now_playing` | `{"cmd": "play_pause" \| "next" \| "previous" \| "seek", "position": 90}` | Win, Mac |
| `volume_set` / `volume_change` / `volume_mute` | `{"level": 50}` / `{"delta": 5}` / `{}` | Win, Mac |
| `mixer_set` / `mixer_mute` | `{"app": "chrome.exe", "level": 40}` | Win |
| `discord_mute` / `discord_deafen` | `{}` | Win, Mac, Linux |
| `lock` | `{}` | todas |
| `power` | `{"mode": "shutdown" \| "restart" \| "sleep" \| "cancel"}` | todas |
| `kill_process` | `{"name": "app.exe"}` | todas |
| `mouse_click` / `mouse_move` | `{"x": 100, "y": 200}` | todas |
| `macro` | `{"steps": [{"action": ..., "params": ...}, {"delay_ms": 500}]}` | todas |
| `screenshot`, `show_desktop`, `shortcut`, `clipboard_copy`, `ocr_capture`, `audio_output`… | ver código | Mac |

La lista exacta de lo disponible en tu equipo: `GET /api/actions`.

Discord requiere crear una app en el portal de desarrolladores: instrucciones al principio de [server/actions/discord_rpc.py](server/actions/discord_rpc.py) y plantilla en `server/config/discord.example.json`.

## Plugins

Añade acciones, datos en vivo y widgets sin tocar el código de MiniDeck:

```
%APPDATA%\MiniDeck\plugins\mi_plugin\     (o ~/Library/Application Support/MiniDeck/plugins/…)
├── plugin.json   ← nombre, versión, plataformas, dependencias, ajustes
├── plugin.py     ← @action("mi_plugin_hacer")
├── widget.js     ← MiniDeck.registerWidget("mi_plugin", {...})
└── widget.css
```

```python
from actions import action

@action("mi_plugin_hacer")
def hacer(params: dict):
    return {"message": "Listo"}
```

Guía completa: **[docs/PLUGINS.md](docs/PLUGINS.md)** · Plantilla: [examples/plugins/hello](examples/plugins/hello) · Índice de la comunidad: [docs/PLUGIN_INDEX.md](docs/PLUGIN_INDEX.md)

## Opciones del servidor

| Opción | Por defecto | Para qué |
|---|---|---|
| `--port` / `MINIDECK_PORT` | `8765` | Puerto |
| `--host` / `MINIDECK_HOST` | `0.0.0.0` | Interfaz (usa `127.0.0.1` para solo local) |
| `MINIDECK_TOKEN` | aleatorio | Fijar el token (p. ej. el mismo en varios equipos) |
| `MINIDECK_CONFIG_DIR` | ver arriba | Carpeta de `deck.json`, token y `discord.json` |
| `MINIDECK_PLUGINS_DIR` | `<datos>/plugins` | Carpeta de plugins de usuario |
| `MINIDECK_NO_AUTH=1` | — | Desactiva el token. **No recomendado.** |

## Estructura

```
minideck/
├── server/
│   ├── main.py            # FastAPI + WebSocket + rutas
│   ├── auth.py            # token de emparejamiento
│   ├── paths.py           # rutas por sistema operativo
│   ├── actions/           # acciones incluidas (una por módulo/plataforma)
│   ├── plugins/           # plugins incluidos (sysmon, clock, indicators)
│   ├── config/            # deck.default.json y plantillas
│   ├── app_menubar.py     # app de barra de menú (macOS)
│   └── run.ps1            # arranque con icono de bandeja (Windows)
├── frontend/              # PWA (HTML/CSS/JS puro, sin build)
├── examples/plugins/      # plantilla de plugin
├── docs/                  # guía de plugins
├── build/                 # empaquetado macOS (PyInstaller, DMG, certificados)
└── tests/
```

## Contribuir

¡Bienvenido! Lee [CONTRIBUTING.md](CONTRIBUTING.md). Para desarrollo:

```bash
pip install -r requirements-dev.txt
pytest
ruff check server tests
```

## Licencia

Copyright © 2026 Samons

MiniDeck es software libre: puedes redistribuirlo y/o modificarlo bajo los términos de la **GNU Affero General Public License** publicada por la Free Software Foundation, ya sea la versión 3 o (a tu elección) cualquier versión posterior (`AGPL-3.0-or-later`). Se distribuye SIN NINGUNA GARANTÍA. Texto completo en [LICENSE](LICENSE).

En resumen: puedes usarlo, modificarlo y compartirlo libremente, pero si distribuyes una versión modificada **o la ofreces a otras personas a través de la red**, debes publicar su código fuente bajo la misma licencia.
