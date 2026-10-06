# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""OCR de pantalla y color del píxel bajo el cursor (Vision + Quartz nativos).

- ocr_capture: seleccionas una zona y el texto detectado va al portapapeles.
- pixel_color: copia el color (HEX) del píxel donde está el cursor.
Requiere permiso de Grabación de pantalla (y Accesibilidad para el cursor).
"""
import os
import subprocess
import sys
import tempfile

from . import action

if sys.platform != "darwin":
    raise ImportError("vision_mac solo aplica a macOS")


def _ocr_image(path: str) -> str:
    import Quartz
    import Vision
    from Foundation import NSURL
    url = NSURL.fileURLWithPath_(path)
    src = Quartz.CGImageSourceCreateWithURL(url, None)
    if not src:
        return ""
    img = Quartz.CGImageSourceCreateImageAtIndex(src, 0, None)
    if not img:
        return ""
    req = Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(1)                    # accurate
    req.setRecognitionLanguages_(["es-ES", "en-US"])
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(img, None)
    handler.performRequests_error_([req], None)
    lines = []
    for obs in (req.results() or []):
        cand = obs.topCandidates_(1)
        if cand and len(cand):
            lines.append(cand[0].string())
    return "\n".join(lines)


@action("ocr_capture")
def ocr_capture(params: dict):
    """Selecciona una zona; el texto reconocido va al portapapeles. params: {}"""
    tmp = tempfile.mktemp(suffix=".png")
    subprocess.run(["screencapture", "-i", tmp], check=False)
    if not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
        return {"message": "Captura cancelada"}
    try:
        text = _ocr_image(tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    if not text.strip():
        return {"message": "No se detectó texto"}
    subprocess.run(["pbcopy"], input=text, text=True, check=False)
    return {"message": f"Texto copiado ({len(text)} caracteres)"}


@action("pixel_color")
def pixel_color(params: dict):
    """Copia el color HEX del píxel bajo el cursor. params: {}"""
    import Quartz
    from AppKit import NSBitmapImageRep, NSEvent, NSScreen
    loc = NSEvent.mouseLocation()
    h = NSScreen.screens()[0].frame().size.height
    x, y = int(loc.x), int(h - loc.y)
    img = Quartz.CGWindowListCreateImage(
        Quartz.CGRectMake(x, y, 1, 1),
        Quartz.kCGWindowListOptionOnScreenOnly,
        Quartz.kCGNullWindowID,
        Quartz.kCGWindowImageDefault)
    if not img:
        raise RuntimeError("No se pudo leer la pantalla")
    rep = NSBitmapImageRep.alloc().initWithCGImage_(img)
    c = rep.colorAtX_y_(0, 0)
    conv = c.colorUsingColorSpaceName_("NSCalibratedRGBColorSpace")
    if conv is not None:
        c = conv
    r = int(round(c.redComponent() * 255))
    g = int(round(c.greenComponent() * 255))
    b = int(round(c.blueComponent() * 255))
    hexv = f"#{r:02X}{g:02X}{b:02X}"
    subprocess.run(["pbcopy"], input=hexv, text=True, check=False)
    return {"message": f"Color copiado: {hexv}"}
