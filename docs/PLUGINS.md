# Crear plugins para MiniDeck

Un plugin añade a MiniDeck **acciones** (cosas que hace el equipo al pulsar un botón), **fuentes de estado** (datos en vivo que se envían al móvil) y/o **widgets** (piezas de interfaz en el deck). Todo es opcional: un plugin puede ser solo Python, solo frontend, o ambos.

## Dónde van los plugins

| Carpeta | Para qué |
|---|---|
| `server/plugins/<id>/` | Plugins incluidos con MiniDeck (los mantiene el proyecto). |
| Carpeta de datos `plugins/<id>/` | Plugins de la comunidad o propios. **No tocas el código de MiniDeck.** |

Carpeta de datos según el sistema:

- Windows: `%APPDATA%\MiniDeck\plugins\`
- macOS: `~/Library/Application Support/MiniDeck/plugins/`
- Linux: `~/.config/minideck/plugins/`

Si un plugin de usuario tiene el mismo `id` que uno incluido, **gana el del usuario** (así puedes personalizar uno existente). El `id` es el nombre de la carpeta: minúsculas, números, `-` y `_`.

Instalar un plugin = copiar su carpeta ahí y reiniciar MiniDeck (o usar el Panel, ver abajo).

## Instalar desde el Panel

Abre el Panel (`/panel.html`) **en el propio equipo** y pulsa **🧩 Plugins**:

- **Instalar plugin**: pega la dirección y pulsa *Instalar*. Vale un repo de GitHub (`https://github.com/usuario/minideck-algo`), una carpeta de un repo (`https://github.com/usuario/repo/tree/main/plugins/algo`) o un enlace directo a un `.zip` (solo `https://`, máx. 10 MB). El plugin se instala en la carpeta de datos y **funciona al momento**, sin reiniciar. Si declara dependencias (`requires`), el Panel ofrece instalarlas con un clic (eso sí requiere reiniciar).
- **Explorar**: catálogo de la comunidad ([`docs/plugins.json`](plugins.json)), con botón *Instalar* en cada uno.
- **Instalados**: estado de cada plugin, activar/desactivar (se aplica al reiniciar), *Desinstalar* (solo plugins de usuario) y **Ajustes**: un formulario generado a partir de `settings` del `plugin.json` (casillas, números, listas una por línea y contraseñas ocultas), sin editar JSON.

Instalar y desinstalar solo funcionan desde el propio equipo (`localhost`): desde el móvil puedes cambiar ajustes pero no instalar código. Los plugins de la tienda no pueden reemplazar a uno incluido con MiniDeck (mismo `id`).

> Un plugin es código que se ejecuta en tu equipo. Instala solo plugins de autores en los que confíes.

## Anatomía

```
hello/
├── plugin.json   ← manifiesto (recomendado)
├── plugin.py     ← acciones y fuentes de estado (Python)
├── widget.js     ← widget de frontend (opcional)
└── widget.css    ← estilos del widget (opcional)
```

Hay una plantilla completa y funcional en [`examples/plugins/hello/`](../examples/plugins/hello/). Cópiala y cámbiale el nombre.

## `plugin.json`

```json
{
  "name": "Hola mundo",
  "version": "1.0.0",
  "author": "Tu nombre",
  "description": "Qué hace, en una frase.",
  "homepage": "https://github.com/tu-usuario/minideck-hello",
  "platforms": ["win32", "darwin", "linux"],
  "requires": ["requests"],
  "minideck": "1.0.0",
  "api": 1,
  "settings": {
    "greeting": "¡Hola!"
  }
}
```

| Campo | Significado |
|---|---|
| `platforms` | Si se indica, el plugin solo carga en esos sistemas (`sys.platform`). Vacío = todos. |
| `requires` | Paquetes de pip que necesita. Si faltan, MiniDeck muestra el comando para instalarlos en vez de fallar. |
| `minideck` | Versión mínima de MiniDeck. |
| `api` | Versión de la API de plugins que usa (hoy: `1`). |
| `settings` | Ajustes con su valor por defecto (ver abajo). |

## Acciones (`plugin.py`)

```python
from actions import action, plugin_settings


@action("hello_say")
def hello_say(params: dict):
    """Muestra un saludo. params: {"name": "Samons"}"""
    greeting = plugin_settings("hello")["greeting"]
    return {"message": f"{greeting} {params.get('name', '')}"}
```

### Validar parámetros y limitar el tiempo

```python
@action("hello_say",
        schema={"name": {"type": "str", "required": True},
                "times": {"type": "int", "min": 1, "max": 10}},
        timeout=10)
def hello_say(params: dict):
    ...
```

- `schema` valida `params` **antes** de ejecutar: si falta un parámetro obligatorio o tiene un tipo o rango incorrecto, el móvil recibe un mensaje claro y tu función no se llama. Tipos: `str`, `int`, `float`, `bool`, `list`, `dict`. Reglas: `required`, `min`, `max`, `choices`. Con `"$oneOf": [["path", "app"]]` se exige al menos uno de varios. Los números escritos como texto (`"5"`) se convierten solos.
- `timeout` (segundos, 30 por defecto): si la acción tarda más, el móvil recibe un error en vez de quedarse esperando.
- El editor del móvil usa el esquema (y el ejemplo `params: {...}` del docstring) para rellenar una plantilla al elegir tu acción, y muestra la primera línea del docstring como ayuda.

Reglas:

- Recibe `params` (lo que el botón tenga en `"params"` en `deck.json`).
- Devuelve `None` o un dict con `message` (texto del aviso en el móvil) y/o `state` (datos que se envían a **todos** los clientes).
- Para indicar un error, **lanza una excepción**: MiniDeck la captura y la muestra.
- Se ejecuta en un hilo aparte: puedes bloquear (llamadas de red, `time.sleep`) sin congelar el servidor. Si guardas estado global, protégelo con un `threading.Lock`.
- Prefija los nombres de acción con el id de tu plugin (`hello_say`, no `say`) para no chocar con otros.

Usarla desde un botón en `deck.json`:

```json
{ "id": "b1", "label": "Saludar", "icon": "lucide:hand", "action": "hello_say",
  "params": { "name": "Samons" } }
```

## Fuentes de estado (datos en vivo)

```python
@action("hello_get", state=True)
def hello_get(params: dict):
    return {"state": {"hello": {"count": 42}}}
```

Con `state=True`, MiniDeck la consulta **cada segundo** y envía los cambios al móvil (máximo 5 s por consulta: si tarda más, se ignora esa vuelta). Debe ser rápida: si algo es costoso (APIs web, subprocesos), cachea el resultado y refréscalo cada N segundos, como hace [`server/plugins/indicators/plugin.py`](../server/plugins/indicators/plugin.py).

### Botones con estado

Cualquier botón del deck puede reaccionar a tu estado sin escribir JavaScript:

```json
{ "id": "b2", "label": "Contador", "icon": "lucide:hash", "action": "hello_say",
  "when": { "key": "hello.count", "equals": 3, "color": "#4ade80", "label": "¡Tres!" } }
```

`key` es la ruta dentro del estado (`hello.count`). Sin `equals`, basta con que el valor sea verdadero (y distinto de `"off"`/`"unavailable"`).

## Ajustes

Los valores por defecto van en `plugin.json` → `settings`. El usuario los cambia desde el Panel (**🧩 Plugins → Ajustes**, el formulario se genera según el tipo de cada valor por defecto: `true/false` → casilla, número, lista de textos o texto; las claves que contienen `token`, `password`, `secret` o `apikey` se tratan como contraseñas y nunca se muestran) o a mano en su `deck.json`:

```json
{
  "pluginSettings": {
    "hello": { "greeting": "¡Buenas!" }
  }
}
```

En Python, `plugin_settings("hello")` devuelve los dos mezclados (los del usuario ganan). Se relee automáticamente cuando cambia `deck.json`.

Para desactivar un plugin sin borrarlo:

```json
{ "disabledPlugins": ["hello"] }
```

## Widgets (`widget.js`)

MiniDeck carga los `widget.js`/`widget.css` de los plugins activos antes de pintar el deck. Registra tu widget con `window.MiniDeck.registerWidget`:

```js
(() => {
  const { registerWidget, run } = window.MiniDeck;

  registerWidget("hello", {
    label: "Hola mundo",          // nombre en el editor
    stateKey: "hello",            // clave del estado que escucha
    build(w) {                    // w = la entrada del deck (id, color, params…)
      const el = document.createElement("div");
      el.className = "hello-widget";
      el.textContent = "…";
      el.onclick = () => run("hello_say", { name: "desde el widget" });
      return el;
    },
    sync(data) {                  // se llama con state.hello cada vez que cambia
      const el = document.querySelector(".hello-widget");
      if (el) el.textContent = `Contador: ${data.count}`;
    },
    noAction: true,               // el editor no pide acción para este widget
  });
})();
```

API disponible en `window.MiniDeck`:

| Función | Qué hace |
|---|---|
| `registerWidget(tipo, def)` | Registra un tipo de widget. |
| `run(accion, params)` | Ejecuta una acción en el equipo. |
| `toast(texto, esError)` | Muestra un aviso. |
| `renderIcon(el, icono, color)` | Pinta un icono (`"lucide:play"`, emoji o `"img:..."`). |
| `state` | Estado actual del cliente (incluye `config`). |

Usa `textContent` (no `innerHTML`) para pintar datos que vengan de fuera, y prefija tus clases CSS con el id del plugin (`.hello-…`) para no pisar estilos ajenos.

## Depurar

- `GET /api/plugins/info` (con tu token) lista cada plugin con su `status` (`loaded`, `error`, `skipped`, `disabled`), el motivo del error y sus acciones.
- `GET /api/state` muestra el estado actual y el error exacto de cada fuente de estado que falle.
- Los errores de carga salen en la consola del servidor.

## Seguridad

Un plugin es código Python que corre **con tus permisos**, igual que cualquier programa que instalas. Instala solo plugins de autores en los que confíes y revisa el código si puedes. Si publicas un plugin:

- No ejecutes comandos construidos con texto del usuario sin escaparlo (usa listas en `subprocess.run([...])`, nunca `shell=True` con concatenaciones).
- No guardes secretos en el repo del plugin: léelos de los ajustes del usuario.
- Declara todas tus dependencias en `requires`.

## Licencia de los plugins

MiniDeck se publica bajo **AGPL-3.0-or-later**. Un plugin con `plugin.py` se ejecuta dentro del mismo proceso que MiniDeck y usa su API interna (`from actions import action`), así que lo más seguro es tratarlo como obra derivada:

- Publica tus plugins bajo **AGPL-3.0-or-later** (o GPL-3.0-or-later, que es compatible).
- Si ofreces a otras personas un MiniDeck **modificado** con tu plugin a través de la red, debes darles acceso al código fuente (AGPL §13).
- Un plugin solo de frontend (`widget.js`/`widget.css`) que únicamente usa `window.MiniDeck` es un caso menos claro. Si tienes dudas, usa también AGPL.

Esto no es asesoramiento legal.

## Publicar tu plugin

1. Crea un repo `minideck-<id>` con la carpeta del plugin, un `LICENSE` (AGPL-3.0-or-later) y un README con capturas.
2. Añade el topic `minideck-plugin` en GitHub para que la comunidad lo encuentre.
3. Abre un PR añadiéndolo a [`docs/PLUGIN_INDEX.md`](PLUGIN_INDEX.md) y a [`docs/plugins.json`](plugins.json) (así aparece en «🧩 Plugins → Explorar» del Panel).
