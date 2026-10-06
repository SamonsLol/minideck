# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/); versiones según [SemVer](https://semver.org/lang/es/).

## [Sin publicar]

### Cambiado
- **Licencia: de MIT a AGPL-3.0-or-later.** Cabeceras SPDX en todos los archivos de código.
- Enlace «Acerca de» (licencia + código fuente) en la interfaz, en `/qr` y en `/api/info` (AGPL §13).
- README principal en inglés (`README.md`) y versión en español (`README.es.md`).
- Capturas de pantalla en `docs/screenshots/`.

### Corregido
- El widget *Now Playing* se desbordaba sobre la columna vecina en móviles estrechos (título cortado, barra de progreso fuera de la celda).

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
