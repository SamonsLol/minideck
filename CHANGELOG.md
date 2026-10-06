# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones según [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Añadido
- **Pulsación larga**: segunda acción por botón (`longAction` / `longParams`).
- **Carpetas**: acción `page` (`{"page": "<id>"}` / `{"page": "back"}`).
- **Botones con estado** (`when`): icono, color y texto según el estado en vivo.
- Plugins incluidos de **OBS Studio** (obs-websocket v5) y **Home Assistant**.
- **Deshacer**, **importar** y **exportar** decks desde el editor; copias automáticas de `deck.json` (últimas 30).
- **Esquemas de parámetros** en `@action(schema=...)`: validación antes de ejecutar y plantillas en el editor (`/api/actions/schema`).
- **Timeout por acción** (30 s por defecto) y por fuente de estado (5 s).
- **Log con rotación** en la carpeta de datos y `GET /api/logs`.
- Aviso visible de **sin conexión** mientras se reconecta.
- **Iconos con caché local** (`/iconify/...`): funcionan sin internet tras el primer uso, con servidores de respaldo.
- Interfaz en **español e inglés** (`frontend/i18n.js`).
- Decks por defecto para **Windows, macOS y Linux**; atajos de teclado en Linux (X11).
- **App de bandeja** para Windows/Linux (`app_tray.py`) y `.exe` de Windows (`build/minideck-win.spec`).
- Instalación con **pip/pipx** (`minideck`, `minideck-tray`).
- **Releases automáticas** (`.zip` de Windows, `.dmg` de macOS, wheel) al subir un tag `v*`.
- **Tests de interfaz** con navegador real en CI y test de empaquetado.
- GIF y capturas en el README.

### Corregido
- Una pulsación larga se cancelaba en teclas altas: la animación `:active` encogía la tecla bajo el dedo y disparaba `pointerleave`.
- La interfaz se repintaba entera al recibir una config idéntica (parpadeos y pulsaciones largas perdidas).
- La barra superior cortaba los últimos botones en móviles de ≤ 390 px.
- El editor borraba los campos que no conocía (de plugins o escritos a mano) al guardar un botón.
- Descargas lentas o acciones colgadas podían dejar sin hilos a los botones: ahora hay pools separados para acciones, estado y E/S.
- La macro no validaba los parámetros de sus pasos.
- El widget *Now Playing* se desbordaba sobre la columna vecina en móviles estrechos (título cortado, barra de progreso fuera de la celda).

### Cambiado
- **Licencia: de MIT a AGPL-3.0-or-later.** Cabeceras SPDX en todos los archivos de código.
- Enlace «Acerca de» (licencia + código fuente) en la interfaz, en `/qr` y en `/api/info` (AGPL §13).
- README principal en inglés (`README.md`) y versión en español (`README.es.md`).
- Capturas de pantalla en `docs/screenshots/`.

## [1.0.0] - 2026-10-05

Primera versión pública.

### Seguridad
- Emparejamiento por token: `/api` y `/ws` exigen token; QR y token solo visibles desde `localhost`.
- Protección contra CSRF, *cross-site WebSocket hijacking* y DNS rebinding.
- `pip install` desde el Panel solo desde el propio equipo.
- El empaquetado de macOS ya no incluye `deck.json` ni `discord.json`.

### Añadido
- Sistema de plugins v1: `plugin.json`, carpeta de plugins de usuario, filtro por plataforma, ajustes (`pluginSettings`), `disabledPlugins` y `/api/plugins/info`.
- Plantilla de plugin en `examples/plugins/hello` y guía en `docs/PLUGINS.md`.
- Discord RPC en macOS y Linux.
- `launch` acepta `{"app": ...}` también en Windows/Linux; `command` funciona en Linux.
- Opciones `--host`, `--port` y variables `MINIDECK_*`.
- Tests y CI (Windows, macOS, Linux).

### Cambiado
- Configuración por sistema operativo (`%APPDATA%`, `~/Library/Application Support`, `~/.config`).
- `deck.default.json` como deck inicial; `deck.json` personal fuera de git.
- Un único `requirements.txt` con marcadores de plataforma.
- Las fuentes de estado se consultan en paralelo.
- `run.ps1` sin rutas absolutas; lanzador `MiniDeck.bat` en la raíz.

### Eliminado
- `media.py` duplicado (idéntico a `media_session.py`).
