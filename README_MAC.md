# MiniDeck en macOS

Guía de instalación, ejecución y **arreglo de permisos** de MiniDeck en un Mac.

MiniDeck es multiplataforma. En macOS se usa un entorno virtual `.venv/` y `requirements.txt` instala solo las dependencias de Mac (`pyobjc`, `rumps`, `pyautogui`…) gracias a los marcadores de plataforma.

---

## 1. Requisitos

- macOS con **Python 3.11** instalado en `/Library/Frameworks/Python.framework` (python.org).
  - Comprueba: `python3 --version`
- iPhone y Mac en la **misma red WiFi**.

---

## 2. Instalación

Desde la carpeta del proyecto (por ejemplo `~/minideck`):

```bash
cd ~/minideck

# Crear el entorno virtual (SIN sudo — muy importante, ver sección de permisos)
python3 -m venv .venv

# Activarlo
source .venv/bin/activate

# Instalar dependencias (versión macOS)
pip install --upgrade pip
pip install -r requirements.txt
```

> ⚠️ **Nunca instales ni crees el entorno con `sudo`.** Si lo haces, el entorno queda a nombre de `root` y luego todo da "permiso denegado". Esta fue la causa del problema original (ver sección 5).

---

## 3. Ejecución

```bash
cd ~/minideck
source .venv/bin/activate
cd server
python main.py
```

En consola verás algo como:

```
  MiniDeck 1.0.0 corriendo
  En este equipo:  http://localhost:8765
  QR para el móvil: http://localhost:8765/qr
  Desde el móvil:  http://192.168.1.50:8765  (código: …)
```

### Permisos de macOS (accesibilidad)

Para que `pyautogui` pueda simular teclado/ratón, macOS pedirá permiso la primera vez:

**Ajustes del Sistema → Privacidad y seguridad → Accesibilidad** → activa **Terminal** (o la app desde la que ejecutas Python).

---

## 4. En el iPhone

1. En el Mac abre `http://localhost:8765/qr` y escanea el QR con la cámara del iPhone: se abre MiniDeck ya emparejado (el QR lleva el token de acceso; no lo compartas).
2. Toca **Compartir → Añadir a pantalla de inicio**.
3. Ábrela desde el icono: se ve a pantalla completa, como app nativa.

---

## 5. Arreglo de permisos (importante)

Si al trabajar en el proyecto **"cualquier cosa da error de permisos"**, casi siempre son dos causas:

### Causa A — Carpetas sin permiso de escritura

Algunas carpetas quedaron como `dr-xr-xr-x` (solo lectura para el dueño). Sin permiso de escritura no puedes crear, borrar ni renombrar archivos dentro.

**Solución** (ya aplicada, pero por si vuelve a pasar):

```bash
cd ~/minideck
chmod -R u+w frontend server README.md requirements.txt assets
chmod u+w .
```

### Causa B — El entorno virtual `.venv/` es de `root`

Si el entorno se creó/instaló con `sudo`, pertenece a `root` y tu usuario no puede tocarlo (instalar paquetes, borrarlo, etc.).

**Solución — devolver la propiedad a tu usuario** (te pedirá tu contraseña de Mac):

```bash
cd ~/minideck
sudo chown -R "$(whoami)":staff .venv
```

> Alternativa: borrarlo y recrearlo **sin sudo** (`sudo rm -rf .venv` y repetir la sección 2).

### Verificar que todo quedó bien

```bash
cd ~/minideck

# ¿Queda algo propiedad de root? (debería salir vacío tras el chown)
find . -user root

# ¿Alguna carpeta tuya sin permiso de escritura? (debería salir vacío)
find . -type d ! -user root ! -perm -u+w
```

Ambos comandos sin salida = permisos correctos.

---

## 6. Botones de sistema en macOS

La página **Sistema** del deck ya está adaptada. Equivalencias:

| Botón      | Acción         | Qué hace en macOS                                              | Permiso necesario |
|------------|----------------|----------------------------------------------------------------|-------------------|
| Bloquear   | `lock`         | Cmd+Ctrl+Q → bloquea la pantalla                               | Accesibilidad     |
| Suspender  | `power` (sleep)| `pmset sleepnow` → suspende el Mac                             | —                 |
| Captura    | `screenshot`   | Selección de zona al portapapeles (como Win+Shift+S)          | Grabación de pantalla |
| Escritorio | `show_desktop` | F11 → Mostrar escritorio (Mission Control)                    | Accesibilidad     |

**Permisos de macOS** (Ajustes del Sistema → Privacidad y seguridad):

- **Accesibilidad** → activa **Terminal** (o la app desde la que ejecutas Python). Necesario para *Bloquear* y *Escritorio*.
- **Grabación de pantalla** → activa **Terminal**. Necesario para *Captura*.

> Si *Escritorio* no funciona, revisa **Ajustes → Teclado → Combinaciones → Mission Control → "Mostrar escritorio"** y asígnale **F11**.

La acción `power` también soporta `shutdown` (apagar) y `restart` (reiniciar) en macOS vía AppleScript, sin necesidad de contraseña.

---

## 7. "Now Playing" (qué está sonando) en macOS

El widget grande de la página **Principal** ("nada sonando") ya detecta música en Mac.

**Cómo funciona:** en Windows se usa la sesión multimedia global del sistema. En macOS 15.4+ Apple **bloqueó** ese acceso para apps no firmadas, así que MiniDeck lee cada reproductor por separado con AppleScript (módulo `server/actions/media_mac.py`):

| Fuente | Detección | Control (play/pausa, siguiente, anterior, buscar) |
|--------|-----------|---------------------------------------------------|
| **Apple Music** (Music.app) | ✅ título, artista, posición, duración | ✅ completo |
| **Spotify** (app) | ✅ título, artista, posición, duración | ✅ completo |
| **Navegador** (YouTube Music, Amazon Music web, Spotify web, SoundCloud y **YouTube** normal) | ⚠️ **título** de la pestaña, mientras suena | ⏯️ play/pausa, siguiente y anterior (teclas multimedia). ❌ barra (seek) no |

> ### ⭐ Para que el navegador funcione bien: activa JavaScript desde Apple Events
>
> Sin esto, del navegador solo se lee el **título** (el icono play/pausa no cambia, no hay contador ni barra). Activándolo, MiniDeck lee el `<video>` real de la pestaña y funciona **todo**: icono correcto, contador, duración, barra y siguiente/anterior.
>
> **Vivaldi / Chrome / Brave / Edge / Arc:** *Configuración → Privacidad → Apple Events → "Permitir JavaScript desde Apple Events"* (actívalo).
> **Safari:** menú *Desarrollo → Permitir JavaScript desde Apple Events* (si no ves "Desarrollo", actívalo en Ajustes de Safari → Avanzado).
>
> La primera vez, macOS pedirá permiso de **Automatización** para que la app controle el navegador → Acepta.
>
> **Cómo funciona y límites:**
> - **Detección:** busca en las pestañas una cuyo título delate reproducción (ej. `Canción | YouTube Music`, `Vídeo - YouTube`). Los **servicios de música** tienen prioridad sobre un vídeo de YouTube normal.
> - **Con JavaScript activado:** icono play/pausa, contador, duración, **barra (arrastrar)** y siguiente/anterior funcionan por pestaña.
> - **Sin JavaScript activado:** solo play/pausa (teclas multimedia del sistema, requiere **Accesibilidad**); el icono no refleja el estado y no hay barra ni contador.
> - **Aviso:** si tienes varias pestañas de YouTube abiertas, puede confundir cuál suena. Para lo más fiable, **Apple Music o Spotify** (app).

**Permiso necesario — Automatización:** la primera vez que suene algo, macOS preguntará *"Terminal quiere controlar Music / Spotify / el navegador"* → pulsa **Aceptar**. Puedes gestionarlo en **Ajustes del Sistema → Privacidad y seguridad → Automatización**.

Amazon Music: si usas la **app de escritorio** de Amazon Music no expone datos a macOS (no hay detección); si lo escuchas en el **navegador** (music.amazon.es) se detecta el título de la pestaña.

---

## 8. Notas de compatibilidad Windows → macOS

| Elemento (Windows)            | En macOS                                              |
|-------------------------------|------------------------------------------------------|
| `keyboard`, `pycaw`, `comtypes` | No compatibles; se usa `pyautogui` para teclado/ratón |
| Volumen del sistema (`pycaw`) | Funciona vía `osascript` (`volume_mac.py`): botón Silenciar y slider de Volumen. El "mezclador" muestra solo el volumen general (macOS no da volumen por-app) |
| Now Playing (`winsdk`)        | Funciona vía AppleScript (`media_mac.py`, ver sección 7) |
| `Mini Desk.bat`, `run.ps1`    | No se usan; se arranca con `python main.py`           |
| Firewall / "red privada"      | En macOS no hace falta; solo acepta el aviso de red   |
| Ejecutar "como administrador" | En macOS se usa **Accesibilidad** (sección 3)         |

---

## 9. Estructura

```
minideck/
├── server/
│   ├── main.py            # FastAPI + WebSocket
│   ├── actions/           # sistema de acciones plugin
│   └── config/deck.json   # tu deck: páginas y botones
├── frontend/              # PWA (HTML/CSS/JS puro, sin build)
├── .venv/               # entorno virtual de macOS (NO subir a git)
└── requirements.txt
```

---

## 10. Instalar como app (barra de menú) + abrir con QR

MiniDeck se puede empaquetar como una **app de barra de menú** (`MiniDeck.app`) que
arranca el servidor sola, muestra un **QR** para abrirlo desde el iPhone, y puede
**arrancar al iniciar sesión**. No necesita Python en el Mac de destino.

### Construir la app
Desde la raíz del proyecto:

```bash
bash build/build.command
```

Esto crea (o reutiliza) el venv `buildenv/`, instala `requirements-mac.txt`, y con
**PyInstaller** genera **`dist/MiniDeck.app`** (firmada ad-hoc). Arrástrala a `/Applications`.

> Construye en la misma arquitectura del Mac de destino (Apple Silicon vs Intel),
> o usa `target_arch universal2` en `build/minideck.spec`.

### Usarla
Al abrirla aparece el icono de la **lamparita en la barra de menú** (arriba a la derecha):

- **Mostrar QR** → ventana con el código QR + la URL. Escanéalo con la **cámara del
  iPhone** → abre la PWA en Safari → *Compartir → Añadir a pantalla de inicio*.
- **Abrir en este Mac** → abre `http://localhost:8765`.
- **Copiar URL** → copia la dirección LAN.
- **Arrancar al iniciar sesión** → se registra como ítem de inicio.
- **Salir**.

También hay una página web del QR: `http://localhost:8765/qr`.

La config editable (tu deck) se guarda en
`~/Library/Application Support/MiniDeck/deck.json` (los recursos dentro del `.app`
son de solo lectura).

### Llevarla a OTRO Mac
1. Copia `MiniDeck.app` al otro Mac (AirDrop, USB, etc.) → `/Applications`.
2. Como no está firmada con Apple Developer ID, Gatekeeper la bloquea la 1ª vez:
   **clic derecho → Abrir** (o en Terminal: `xattr -dr com.apple.quarantine /Applications/MiniDeck.app`).
3. **Reconcede permisos** en Ajustes → Privacidad y seguridad (son por-app/por-equipo):
   - **Accesibilidad** (atajos, bloquear, escritorio),
   - **Grabación de pantalla** (captura, OCR, color de píxel),
   - **Automatización** (controlar apps/navegador),
   - opcional `brew install switchaudio-osx` para cambiar dispositivos de audio.
4. Abre **Mostrar QR** y escanéalo desde el iPhone (ambos en la **misma red WiFi**).

> Para una distribución "limpia" sin el aviso de Gatekeeper haría falta una cuenta
> **Apple Developer ID** ($99/año) + notarización.

### Estructura de empaquetado
```
build/minideck.spec     # receta de PyInstaller (.app, icono, LSUIElement)
build/build.command     # construye dist/MiniDeck.app
requirements-mac.txt    # dependencias de macOS + build
assets/minideck.icns    # icono de la app
server/app_menubar.py   # entry point: barra de menú + QR + autoarranque
buildenv/               # venv de usuario para construir (NO subir a git)
```

---

## 11. Android sin barras (PWA standalone) — requiere HTTPS

**iPhone**: basta *Compartir → Añadir a pantalla de inicio* (funciona sobre HTTP).

**Android (Chrome/Brave)** solo instala la app **sin barras** si el sitio es
**HTTPS de confianza** (si no, "añadir a inicio" crea un acceso directo con barras).
Solución: un certificado local de confianza con **mkcert**.

### Pasos (una vez)
1. En el Mac:
   ```bash
   bash build/make_cert.command
   ```
   Instala `mkcert`, crea la CA local y genera el certificado para tu IP y
   `TuMac.local` en `~/Library/Application Support/MiniDeck/certs/`.
2. Pasa el archivo **`rootCA.pem`** (misma carpeta) al teléfono (correo, Drive, USB).
3. En Android: **Ajustes → Seguridad → Cifrado y credenciales → Instalar un
   certificado → Certificado de CA** → elige `rootCA.pem`.
4. **Reinicia MiniDeck** (ahora arranca en **HTTPS**; el banner lo indica) y abre
   `https://TU_IP:8765` en Chrome/Brave.
5. Aparecerá el botón **Instalar** (o menú → *Instalar app*). Ábrela desde el
   icono → **pantalla completa, sin barras**.

> Si cambias de red WiFi tu IP cambia: vuelve a correr `build/make_cert.command`
> (o usa `https://TuMac.local:8765`, más estable) y regenera el QR.
>
> Con certificados presentes, el servidor sirve HTTPS para **todos** (iPhone
> incluido). Sin certificados, sigue en HTTP (iPhone funciona igual).
