# Plugin Home Assistant

Controla [Home Assistant](https://www.home-assistant.io/) desde MiniDeck con su
API REST: luces, interruptores, escenas o cualquier servicio. Solo usa la
biblioteca estándar de Python.

## Crear un token

1. En Home Assistant, abre tu **Perfil** (abajo a la izquierda) → pestaña
   **Seguridad**.
2. En **Tokens de acceso de larga duración**, pulsa **Crear token**, ponle un
   nombre (p. ej. «MiniDeck») y copia el token: solo se muestra una vez.

## Configuración en `deck.json`

```json
{
  "pluginSettings": {
    "homeassistant": {
      "url": "http://homeassistant.local:8123",
      "token": "eyJhbGciOi…",
      "entities": ["light.salon", "switch.ventilador", "scene.cine"]
    }
  }
}
```

`entities` es la lista de entidades cuyo estado se envía al móvil en vivo
(opcional). El token da control total de tu casa: no compartas tu `deck.json`.

## Acciones

| Acción | Parámetros | Qué hace |
|---|---|---|
| `ha_toggle` | `{"entity_id": "light.salon"}` | Conmuta la entidad (`homeassistant.toggle`) |
| `ha_scene` | `{"entity_id": "scene.cine"}` | Activa una escena (`scene.turn_on`) |
| `ha_service` | `{"domain": "light", "service": "turn_on", "entity_id": "light.salon", "data": {"brightness_pct": 40}}` | Llama a cualquier servicio |

`domain` y `service` solo admiten `a-z`, `0-9` y `_`. `entity_id` puede ser
una cadena o una lista.

Ejemplos de botones:

```json
{ "id": "ha-salon", "label": "Salón", "icon": "lucide:lamp",
  "action": "ha_toggle", "params": { "entity_id": "light.salon" } }
{ "id": "ha-cine", "label": "Cine", "icon": "lucide:clapperboard",
  "action": "ha_scene", "params": { "entity_id": "scene.cine" } }
{ "id": "ha-tenue", "label": "Tenue", "icon": "lucide:sun-dim",
  "action": "ha_service",
  "params": { "domain": "light", "service": "turn_on", "entity_id": "light.salon",
              "data": { "brightness_pct": 20 } } }
```

## Estado en vivo y widget

La fuente de estado `ha_get` publica `state.ha` (como mucho cada 5 s, y solo
si hay `url`, `token` y `entities`):

```json
{ "connected": true,
  "entities": { "light.salon": { "state": "on", "name": "Luz del salón" } } }
```

El widget **Home Assistant** (tipo `ha`) lista esas entidades con su estado;
tocar una la conmuta.
