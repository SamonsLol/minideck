# Plugin OBS Studio

Controla [OBS Studio](https://obsproject.com/) desde MiniDeck mediante
**obs-websocket v5**, que viene incluido en OBS 28 o posterior. No necesita
instalar nada más.

## Activar el servidor WebSocket en OBS

1. En OBS: **Herramientas → Configuración del servidor WebSocket**.
2. Marca **Habilitar servidor WebSocket**. El puerto por defecto es `4455`.
3. Deja activada **Habilitar autenticación** y pulsa **Mostrar información de
   conexión** para copiar la contraseña.

## Configuración en `deck.json`

```json
{
  "pluginSettings": {
    "obs": { "host": "localhost", "port": 4455, "password": "tu-contraseña" }
  }
}
```

Si OBS corre en otro equipo de la red, pon su IP en `host`.

## Acciones

| Acción | Parámetros | Qué hace |
|---|---|---|
| `obs_scene` | `{"scene": "Juego"}` | Cambia la escena de programa |
| `obs_record_toggle` | `{}` | Inicia / detiene la grabación |
| `obs_stream_toggle` | `{}` | Inicia / detiene el directo |
| `obs_record_pause_toggle` | `{}` | Pausa / reanuda la grabación |
| `obs_mute_toggle` | `{"input": "Mic/Aux"}` | Silencia / activa una fuente de audio |
| `obs_replay_save` | `{}` | Guarda el búfer de repetición (debe estar iniciado en OBS) |
| `obs_phonecam_setup` | `{"scene": "", "virtualcam": true}` | Añade la webcam del móvil: crea (o actualiza) la fuente de navegador «MiniDeck Webcam» en la escena actual (o `scene`), ajustada al lienzo, y enciende la cámara virtual |
| `obs_virtualcam_toggle` | `{}` | Inicia / detiene la cámara virtual |

Ejemplos de botones:

```json
{ "id": "obs-rec", "label": "Grabar", "icon": "lucide:circle-dot", "color": "#ef4444",
  "action": "obs_record_toggle", "params": {} }
{ "id": "obs-juego", "label": "Juego", "icon": "lucide:gamepad-2",
  "action": "obs_scene", "params": { "scene": "Juego" } }
{ "id": "obs-mic", "label": "Micro", "icon": "lucide:mic",
  "action": "obs_mute_toggle", "params": { "input": "Mic/Aux" } }
```

## Estado en vivo y widget

La fuente de estado `obs_get` publica `state.obs`:

```json
{ "connected": true, "recording": false, "paused": false, "streaming": false,
  "scene": "Juego", "scenes": ["Juego", "Chat", "Pausa"] }
```

Consulta OBS como mucho cada 2 s; si OBS está cerrado devuelve
`connected: false` y no reintenta conectar hasta pasados 10 s.

El widget **OBS Studio** (tipo `obs`) muestra la conexión, la escena actual,
los botones REC y LIVE (resaltados cuando están activos) y una fila con todas
las escenas para cambiar de una con un toque.
