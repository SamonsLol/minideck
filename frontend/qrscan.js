/* SPDX-License-Identifier: AGPL-3.0-or-later
   SPDX-FileCopyrightText: 2026 Samons */
/* ============================================================
   MiniDeck — lector de QR para emparejar desde la propia app
   - En vivo (cámara) solo es posible en contexto seguro (HTTPS o
     localhost): es una restricción de los navegadores.
   - Por HTTP en la red local (lo normal) se hace una FOTO del QR con
     <input capture> y se decodifica aquí. Funciona también en la PWA
     instalada en iPhone y Android.
   Decodificador: BarcodeDetector nativo si existe; si no, jsQR
   (frontend/vendor/jsQR.js, Apache-2.0), que se carga solo al usarlo.
   ============================================================ */
(() => {
  let jsqrLoading = null;
  function ensureJsQR() {
    if (window.jsQR) return Promise.resolve();
    jsqrLoading ??= new Promise((res, rej) => {
      const s = document.createElement("script");
      s.src = "/vendor/jsQR.js";
      s.onload = res;
      s.onerror = () => { jsqrLoading = null; rej(new Error("jsQR")); };
      document.head.appendChild(s);
    });
    return jsqrLoading;
  }

  let detector = null;
  try {
    if ("BarcodeDetector" in window) detector = new BarcodeDetector({ formats: ["qr_code"] });
  } catch { detector = null; }

  async function decodeSource(source, w, h, canvas) {
    if (detector) {
      try {
        const found = await detector.detect(source);
        if (found[0]?.rawValue) return found[0].rawValue;
      } catch { /* probar jsQR */ }
    }
    await ensureJsQR();
    canvas.width = w; canvas.height = h;
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(source, 0, 0, w, h);
    const res = window.jsQR(ctx.getImageData(0, 0, w, h).data, w, h,
                            { inversionAttempts: "attemptBoth" });
    return res?.data || null;
  }

  /* ---------------------------------------------- foto (funciona por HTTP) */
  function pickPhoto() {
    return new Promise((resolve) => {
      const input = document.createElement("input");
      input.type = "file";
      input.accept = "image/*";
      input.setAttribute("capture", "environment");   // abre la cámara trasera
      input.style.display = "none";
      input.onchange = () => { resolve(input.files?.[0] || null); input.remove(); };
      input.oncancel = () => { resolve(null); input.remove(); };
      document.body.appendChild(input);
      input.click();
    });
  }

  async function scanPhoto() {
    const file = await pickPhoto();
    if (!file) return null;
    const url = URL.createObjectURL(file);
    try {
      const img = await new Promise((res, rej) => {
        const i = new Image();
        i.onload = () => res(i);
        i.onerror = rej;
        i.src = url;
      });
      const canvas = document.createElement("canvas");
      // las fotos del móvil son enormes: probar a varios tamaños
      for (const max of [1024, 1600, 700]) {
        const k = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
        const text = await decodeSource(img, Math.round(img.naturalWidth * k),
                                        Math.round(img.naturalHeight * k), canvas);
        if (text) return text;
      }
      return "";          // foto sin QR legible
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  /* ---------------------------------------------- en vivo (HTTPS/localhost) */
  const canLive = () => Boolean(window.isSecureContext && navigator.mediaDevices?.getUserMedia);

  /* Pinta el vídeo dentro de `box` y resuelve con el texto del QR, o null si
     se cancela (stop()). */
  function scanLive(box) {
    let stream = null, stopped = false, timer = null, done;
    const promise = new Promise((resolve) => { done = resolve; });
    const video = document.createElement("video");
    video.setAttribute("playsinline", "");
    video.muted = true;
    video.style.cssText = "width:100%;max-height:50vh;border-radius:12px;background:#000;object-fit:cover";
    box.appendChild(video);
    const canvas = document.createElement("canvas");

    const stop = () => {
      stopped = true;
      clearTimeout(timer);
      stream?.getTracks().forEach((t) => t.stop());
      video.remove();
      done(null);
    };
    const tick = async () => {
      if (stopped) return;
      if (video.readyState >= 2 && video.videoWidth) {
        const k = Math.min(1, 720 / Math.max(video.videoWidth, video.videoHeight));
        const text = await decodeSource(video, Math.round(video.videoWidth * k),
                                        Math.round(video.videoHeight * k), canvas)
          .catch(() => null);
        if (text && !stopped) {
          stopped = true;
          stream?.getTracks().forEach((t) => t.stop());
          video.remove();
          done(text);
          return;
        }
      }
      timer = setTimeout(tick, 180);
    };

    navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false })
      .then((s) => {
        stream = s;
        if (stopped) { s.getTracks().forEach((t) => t.stop()); return; }
        video.srcObject = s;
        return video.play();
      })
      .then(() => tick())
      .catch(() => { video.remove(); done(undefined); });   // sin permiso / sin cámara
    return { promise, stop };
  }

  /* Extrae el token de un QR de MiniDeck (URL con ?token=…) o de un código suelto. */
  function tokenFrom(text) {
    const t = (text || "").trim();
    try {
      const tok = new URL(t).searchParams.get("token");
      if (tok) return tok;
    } catch { /* no es URL */ }
    return /^[A-Za-z0-9_-]{8,128}$/.test(t) ? t : null;
  }

  window.MiniDeckQR = { canLive, scanLive, scanPhoto, tokenFrom };
})();
