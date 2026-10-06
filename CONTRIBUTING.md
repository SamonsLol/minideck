# Contribuir a MiniDeck

¡Gracias por querer ayudar! Se aceptan issues y PRs en español o en inglés.

## Formas de contribuir

- **Reportar bugs** con la plantilla de issue (incluye SO, versión de Python y el log del servidor).
- **Proponer ideas** antes de programar algo grande: abre un issue para hablarlo.
- **Crear plugins**: la mejor forma de añadir funciones sin tocar el núcleo. Ver [docs/PLUGINS.md](docs/PLUGINS.md).
- **Mejorar la documentación**, traducciones o el deck por defecto.

## Entorno de desarrollo

```bash
git clone https://github.com/SamonsLol/minideck.git
cd minideck
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cd server && python main.py
```

Antes de abrir un PR:

```bash
python -m playwright install chromium   # una vez, para los tests de interfaz
pytest
ruff check server tests examples packaging
```

El CI ejecuta los tests en Windows, macOS y Linux, más los tests de interfaz en un navegador real (desbordamientos a 340/360/390/768 px, carpetas, pulsación larga, botones con estado, idioma y editor). Si cambias el frontend, añade o ajusta un test en `tests/test_ui.py`.

## Pautas

- **¿Núcleo o plugin?** Si la función solo interesa a parte de los usuarios o depende de una app concreta (OBS, Spotify, Home Assistant…), va mejor como plugin.
- **Acciones de plataforma**: un módulo por plataforma (`algo.py` para Windows, `algo_mac.py` para macOS) con la guarda `raise ImportError("... solo aplica a ...")` al principio, como los existentes.
- **Frontend sin build**: HTML/CSS/JS puro, sin dependencias de npm. Usa `textContent` para datos externos.
- **Textos de la interfaz**: van en `frontend/i18n.js` (español e inglés) y se usan con `T("clave")`. Cualquier texto nuevo necesita sus dos traducciones.
- **Acciones nuevas**: con `schema=` para validar sus parámetros y un docstring con `params: {...}` de ejemplo.
- **Seguridad**: nada de `shell=True` con texto del usuario; cualquier ruta nueva de `/api` pasa por el middleware de autenticación. Si añades algo sensible, añade un test.
- **Commits** pequeños y descriptivos. Un PR = un cambio.
- Al contribuir aceptas que tu código se publique bajo la licencia [AGPL-3.0-or-later](LICENSE).
- Los archivos nuevos de código deben empezar con la cabecera `SPDX-License-Identifier: AGPL-3.0-or-later`.

## Código de conducta

Este proyecto sigue el [Código de Conducta](CODE_OF_CONDUCT.md). Sé amable.
