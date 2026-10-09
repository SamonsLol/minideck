# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""
Webcam del móvil: la cámara del teléfono como webcam del PC.

El móvil (widget "Webcam", frontend/phonecam.js) envía fotogramas JPEG por
WebSocket a /phonecam/ws. El servidor guarda el último y lo ofrece:

  /phonecam/view          página a pantalla completa → "Fuente de navegador" de
                          OBS; con "Iniciar cámara virtual", Zoom/Meet/Discord
                          la ven como una webcam más.
  /phonecam/stream.mjpg   flujo MJPEG para programas que lo acepten.
  /phonecam/snapshot.jpg  último fotograma.
  /api/phonecam/status    estado (en vivo, fps, resolución, cámara virtual).

Opcional: si están instalados `pyvirtualcam`, `numpy` y `Pillow` (y el driver
de la cámara virtual de OBS), los fotogramas van también a una cámara virtual
del sistema sin abrir OBS.

Privacidad: solo transmite un dispositivo emparejado (token), y la imagen solo
se ve desde el propio equipo (localhost) o con el token.
"""
import asyncio
import logging
import threading
import time

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse

import auth

log = logging.getLogger("minideck.phonecam")
router = APIRouter()

MAX_FRAME = 3 * 1024 * 1024      # 3 MB por fotograma (1080p JPEG cabe de sobra)
IDLE_AFTER = 3.0                 # s sin fotogramas → "no está en vivo"
BOUNDARY = "minideckframe"


class Hub:
    """Último fotograma + avisos a quien espera el siguiente."""

    def __init__(self) -> None:
        self.frame: bytes | None = None
        self.seq = 0
        self.ts = 0.0
        self.width = self.height = 0
        self.publisher: WebSocket | None = None
        self.viewers = 0
        self._times: list[float] = []

    @property
    def live(self) -> bool:
        return self.frame is not None and time.monotonic() - self.ts < IDLE_AFTER

    @property
    def fps(self) -> float:
        now = time.monotonic()
        recent = [t for t in self._times if now - t < 2.0]
        return round(len(recent) / 2.0, 1)

    async def publish(self, jpeg: bytes) -> None:  # noqa: RUF029 (async por la API)
        self.frame = jpeg
        self.seq += 1
        self.ts = time.monotonic()
        self._times = [t for t in self._times[-60:] if self.ts - t < 2.0] + [self.ts]
        w, h = jpeg_size(jpeg)
        if w:
            self.width, self.height = w, h
        vcam.push(jpeg)

    async def wait_next(self, seq: int, timeout: float) -> int:
        """Espera un fotograma nuevo (sondeo cada 15 ms: no depende del bucle
        de eventos y a 30 fps añade como mucho 15 ms de retraso)."""
        end = time.monotonic() + timeout
        while self.seq == seq and time.monotonic() < end:
            await asyncio.sleep(0.015)
        return self.seq


hub = Hub()


def jpeg_size(data: bytes) -> tuple[int, int]:
    """Ancho y alto de un JPEG leyendo sus cabeceras (sin decodificarlo)."""
    i = 2
    n = len(data)
    while i + 9 < n:
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):          # SOF: aquí están las medidas
            h = int.from_bytes(data[i + 5:i + 7], "big")
            w = int.from_bytes(data[i + 7:i + 9], "big")
            return w, h
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    return 0, 0


# ------------------------------------------------- cámara virtual (opcional)
class VirtualCam:
    """Envía los fotogramas a una cámara virtual del sistema con pyvirtualcam.
    Se activa sola si las dependencias existen; si no, se queda en "no disponible"."""

    def __init__(self) -> None:
        self.status = "no iniciada"
        self._latest: bytes | None = None
        self._event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def available(self) -> bool:
        try:
            import numpy  # noqa: F401
            import pyvirtualcam  # noqa: F401
            from PIL import Image  # noqa: F401
            return True
        except ImportError:
            return False

    def push(self, jpeg: bytes) -> None:
        with self._lock:
            self._latest = jpeg
        self._event.set()
        if self._thread is None and self.available():
            self._thread = threading.Thread(target=self._run, daemon=True, name="phonecam-vcam")
            self._thread.start()

    def _run(self) -> None:
        import io

        import numpy as np
        import pyvirtualcam
        from PIL import Image
        cam = None
        size = None
        while True:
            if not self._event.wait(IDLE_AFTER):
                if cam is not None:                 # sin señal: liberar la cámara
                    cam.close()
                    cam, size = None, None
                    self.status = "en espera"
                continue
            self._event.clear()
            with self._lock:
                jpeg = self._latest
            try:
                img = Image.open(io.BytesIO(jpeg)).convert("RGB")
                if cam is None or img.size != size:
                    if cam is not None:
                        cam.close()
                    size = img.size
                    cam = pyvirtualcam.Camera(width=size[0], height=size[1], fps=30)
                    self.status = f"activa: {cam.device}"
                    log.info("Cámara virtual: %s (%dx%d)", cam.device, *size)
                cam.send(np.asarray(img))
            except Exception as exc:  # noqa: BLE001  (sin driver, etc.)
                msg = f"error: {type(exc).__name__}: {exc}"
                if self.status != msg:
                    log.warning("Cámara virtual no disponible: %s", exc)
                self.status = msg
                time.sleep(5)


vcam = VirtualCam()


# ---------------------------------------------------------------- acceso ---
def _allowed(req_or_ws) -> bool:
    """Ver la imagen: desde este equipo (OBS) o con el token."""
    client = req_or_ws.client.host if req_or_ws.client else None
    if auth.local_request(client, req_or_ws.headers):
        return True
    return auth.check(auth.token_from(req_or_ws.headers, req_or_ws.query_params,
                                      req_or_ws.cookies))


# ----------------------------------------------------------------- rutas ---
@router.websocket("/phonecam/ws")
async def phonecam_ws(ws: WebSocket):
    """El móvil emparejado envía aquí fotogramas JPEG (mensajes binarios)."""
    if not auth.same_origin(ws.headers) or \
            not auth.check(auth.token_from(ws.headers, ws.query_params, ws.cookies)):
        await ws.close(code=4401)
        return
    await ws.accept()
    old, hub.publisher = hub.publisher, ws
    if old is not None:                      # un solo móvil a la vez: el nuevo manda
        try:
            await old.close(code=4409)
        except Exception:  # noqa: BLE001
            pass
    log.info("Webcam del móvil: transmitiendo")
    try:
        while True:
            msg = await ws.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            data = msg.get("bytes")
            if not data:
                continue                     # texto = latido; se ignora
            if len(data) > MAX_FRAME or data[:2] != b"\xff\xd8":
                await ws.close(code=4400)    # solo JPEG razonables
                break
            await hub.publish(data)
    except WebSocketDisconnect:
        pass
    finally:
        if hub.publisher is ws:
            hub.publisher = None
            log.info("Webcam del móvil: detenida")


@router.get("/phonecam/snapshot.jpg")
async def snapshot(req: Request):
    if not _allowed(req):
        return Response(status_code=403)
    if hub.frame is None:
        return Response(status_code=404)
    return Response(hub.frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/phonecam/stream.mjpg")
async def stream(req: Request):
    if not _allowed(req):
        return Response(status_code=403)

    return StreamingResponse(mjpeg_parts(req.is_disconnected),
                             media_type=f"multipart/x-mixed-replace; boundary={BOUNDARY}",
                             headers={"Cache-Control": "no-store"})


async def mjpeg_parts(is_disconnected):
    """Partes multipart del flujo MJPEG: un JPEG por fotograma nuevo."""
    hub.viewers += 1
    try:
        seq = -1
        while not await is_disconnected():
            seq = await hub.wait_next(seq, timeout=2.0)
            if hub.frame is None:
                continue
            yield (f"--{BOUNDARY}\r\nContent-Type: image/jpeg\r\n"
                   f"Content-Length: {len(hub.frame)}\r\n\r\n").encode() + hub.frame + b"\r\n"
    finally:
        hub.viewers -= 1


@router.get("/phonecam/view")
async def view(req: Request):
    """Página para la "Fuente de navegador" de OBS (1280×720 o 1920×1080)."""
    if not _allowed(req):
        return Response(status_code=403)
    q = f"?token={req.query_params['token']}" if req.query_params.get("token") else ""
    return HTMLResponse(f"""<!doctype html><html><head><meta charset="utf-8">
<title>MiniDeck · Webcam</title><style>
html,body{{margin:0;height:100%;background:#000;overflow:hidden}}
img{{width:100%;height:100%;object-fit:contain;display:block}}
</style></head><body><img src="/phonecam/stream.mjpg{q}" alt=""></body></html>""",
                        headers={"Cache-Control": "no-store"})


@router.get("/api/phonecam/status")
async def status():
    return JSONResponse({
        "live": hub.live, "fps": hub.fps, "width": hub.width, "height": hub.height,
        "viewers": hub.viewers, "publisher": hub.publisher is not None,
        "virtualCamera": vcam.status if vcam.available() else "no instalada",
        "obsUrl": "/phonecam/view", "mjpegUrl": "/phonecam/stream.mjpg",
    })
