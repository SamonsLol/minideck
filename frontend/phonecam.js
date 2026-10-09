/* SPDX-License-Identifier: AGPL-3.0-or-later
   SPDX-FileCopyrightText: 2026 Samons */
/* ============================================================
   Webcam del móvil: usa la cámara del teléfono como webcam del PC.
   Widget "phonecam": al tocarlo abre la cámara, y "Transmitir" envía
   fotogramas JPEG al servidor (/phonecam/ws). En el PC se ven en
   /phonecam/view (fuente de navegador de OBS → cámara virtual).
   El navegador solo da acceso a la cámara en contexto seguro (HTTPS,
   o localhost: p. ej. Android por USB con `adb reverse`).
   ============================================================ */
(() => {
  const T = (k, v) => window.MiniDeckI18n.t(k, v);
  const QUALITY = { "480p": [854, 480], "720p": [1280, 720], "1080p": [1920, 1080] };
  const cam = {
    stream: null, ws: null, running: false, timer: null, wake: null,
    facing: "user", quality: "720p", fps: 24, sent: 0, lastSent: 0, shown: 0,
    rot: 0,          // giro manual extra (0/90/180/270)
    physical: null,  // orientación física según el sensor (0/90/180/270)
  };

  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  /* ---------------------------------------------- tecla del deck */
  function build(w) {
    const k = el("button", "key pc-key");
    k.type = "button";
    k.dataset.id = w.id;
    k.style.setProperty("--led", w.color || "#f87171");
    const ic = el("span", "icon");
    window.MiniDeck.renderIcon(ic, w.icon || "lucide:webcam", "#c9d1dd");
    const lb = el("span", "label", w.label || T("pc.title"));
    const st = el("span", "pc-badge", cam.running ? T("pc.live") : "");
    k.append(ic, lb, st);
    k.onclick = () => openPanel();
    return k;
  }

  function paintKeys() {
    for (const b of document.querySelectorAll(".pc-key .pc-badge")) {
      b.textContent = cam.running ? `● ${T("pc.live")}` : "";
    }
    document.querySelectorAll(".pc-key").forEach((k) => k.classList.toggle("is-on", cam.running));
  }

  /* ---------------------------------------------- panel de la cámara */
  let panel = null;
  function openPanel() {
    if (!panel) panel = makePanel();
    panel.classList.add("open");
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      panel.querySelectorAll(".pc-ctl button, .pc-ctl select").forEach((c) => { c.disabled = true; });
      showMsg(T("pc.insecure"), T("pc.insecureHelp", { url: `https://${location.hostname}:${location.port || 8765}` }));
      return;
    }
    if (!cam.stream) startPreview();
  }

  function makePanel() {
    const p = el("div", "pc-panel");
    p.setAttribute("role", "dialog");
    p.setAttribute("aria-modal", "true");
    p.setAttribute("aria-label", T("pc.title"));
    p.innerHTML = `
      <div class="pc-head">
        <strong></strong><span class="pc-live" hidden></span>
        <button type="button" class="pc-close" aria-label="✕">✕</button>
      </div>
      <div class="pc-stage"><video playsinline muted autoplay></video>
        <div class="pc-msg" hidden><strong></strong><p></p></div></div>
      <div class="pc-ctl">
        <button type="button" class="pc-flip"></button>
        <button type="button" class="pc-rot"></button>
        <select class="pc-q" aria-label="quality"></select>
        <select class="pc-fps" aria-label="fps"></select>
        <button type="button" class="pc-go"></button>
      </div>
      <p class="pc-help"></p>`;
    p.querySelector(".pc-head strong").textContent = T("pc.title");
    p.querySelector(".pc-flip").textContent = "⟲ " + T("pc.flip");
    p.querySelector(".pc-rot").onclick = () => { cam.rot = (cam.rot + 90) % 360; paintPanel(); };
    const q = p.querySelector(".pc-q");
    for (const k of Object.keys(QUALITY)) q.append(new Option(k, k, false, k === cam.quality));
    const f = p.querySelector(".pc-fps");
    for (const v of [15, 24, 30]) f.append(new Option(`${v} fps`, v, false, v === cam.fps));
    p.querySelector(".pc-help").textContent = T("pc.obsHelp");
    p.querySelector(".pc-close").onclick = closePanel;
    p.querySelector(".pc-flip").onclick = () => {
      cam.facing = cam.facing === "user" ? "environment" : "user";
      startPreview();
    };
    q.onchange = () => { cam.quality = q.value; startPreview(); };
    f.onchange = () => { cam.fps = Number(f.value); };
    p.querySelector(".pc-go").onclick = () => (cam.running ? stopSending() : startSending());
    document.body.appendChild(p);
    paintPanel();
    return p;
  }

  function showMsg(title, text) {
    const m = panel.querySelector(".pc-msg");
    m.hidden = !title;
    m.querySelector("strong").textContent = title || "";
    m.querySelector("p").textContent = text || "";
  }

  function paintPanel() {
    if (!panel) return;
    const go = panel.querySelector(".pc-go");
    go.textContent = cam.running ? "■ " + T("pc.stop") : "● " + T("pc.start");
    go.classList.toggle("on", cam.running);
    panel.querySelector(".pc-rot").textContent = "↻ " + T("pc.rotate") + (cam.rot ? ` ${cam.rot}°` : "");
    const live = panel.querySelector(".pc-live");
    live.hidden = !cam.running;
    live.textContent = `● ${T("pc.live")} · ${cam.shown} fps`;
    panel.querySelector("video").classList.toggle("mirror", cam.facing === "user");
    paintKeys();
  }

  async function startPreview() {
    stopTracks();
    showMsg("");
    const [w, h] = QUALITY[cam.quality];
    try {
      cam.stream = await navigator.mediaDevices.getUserMedia({
        audio: false,
        video: { facingMode: cam.facing, width: { ideal: w }, height: { ideal: h } },
      });
      const v = panel.querySelector("video");
      v.srcObject = cam.stream;
      await v.play().catch(() => {});
    } catch (e) {
      showMsg(T("pc.denied"), String(e.message || e.name || e));
    }
    paintPanel();
  }

  function stopTracks() {
    cam.stream?.getTracks().forEach((t) => t.stop());
    cam.stream = null;
  }

  function closePanel() {
    stopSending();
    stopTracks();
    panel?.classList.remove("open");
  }

  /* ---------------------------------------------- envío */
  function startSending() {
    if (!cam.stream) return;
    watchOrientation();
    const ws = new WebSocket(MiniDeckAuth.wsUrl("/phonecam/ws"));
    ws.binaryType = "arraybuffer";
    cam.ws = ws;
    ws.onopen = () => {
      cam.running = true;
      cam.sent = 0;
      tick();
      keepAwake();
      paintPanel();
    };
    ws.onclose = (ev) => {
      if (cam.ws !== ws) return;
      const was = cam.running;
      cam.running = false;
      cam.ws = null;
      clearTimeout(cam.timer);
      releaseWake();
      paintPanel();
      if (ev.code === 4409) window.MiniDeck.toast(T("pc.taken"), true);
      else if (was && ev.code !== 1000) window.MiniDeck.toast(T("pc.lost"), true);
    };
  }

  function stopSending() {
    cam.running = false;
    clearTimeout(cam.timer);
    if (cam.ws) {
      const ws = cam.ws;
      cam.ws = null;
      try { ws.close(1000); } catch { /* */ }
    }
    releaseWake();
    paintPanel();
  }

  /* ---------------------------------------------- orientación
     Los navegadores giran los fotogramas de la cámara según la orientación de
     la PANTALLA. Con la rotación automática bloqueada (o si el navegador no lo
     hace), el celular en horizontal enviaría la imagen de lado: se compara la
     orientación física (sensor) con la de la pantalla y se corrige al dibujar. */
  let watching = false;
  async function watchOrientation() {
    if (watching) return;
    try {   // iOS pide permiso (debe llamarse desde un toque: el botón Transmitir)
      if (typeof DeviceOrientationEvent?.requestPermission === "function" &&
          await DeviceOrientationEvent.requestPermission() !== "granted") return;
    } catch { return; }
    watching = true;
    window.addEventListener("deviceorientation", (e) => {
      if (e.beta == null || e.gamma == null) return;
      const b = e.beta, g = e.gamma;
      if (Math.abs(g) > 60) cam.physical = g < 0 ? 90 : 270;       // de lado
      else if (Math.abs(b) > 45) cam.physical = b > 0 ? 0 : 180;   // de pie / al revés
      // casi plano: se mantiene la última
    });
  }

  function screenAngle() {
    const a = screen.orientation?.angle ?? window.orientation ?? 0;
    return ((a % 360) + 360) % 360;
  }

  /** Grados (sentido horario) a girar el fotograma antes de enviarlo. */
  function frameRotation() {
    let r = 0;
    if (cam.physical != null) {
      const delta = (cam.physical - screenAngle() + 360) % 360;
      // la cámara frontal da la imagen sin espejo: el giro va al revés
      r = cam.facing === "user" ? delta : (360 - delta) % 360;
    }
    return (r + cam.rot) % 360;
  }

  const canvas = document.createElement("canvas");
  let fpsWindow = [];
  function tick() {
    if (!cam.running) return;
    const v = panel.querySelector("video");
    const ws = cam.ws;
    // control de flujo: si la red va lenta, no acumular fotogramas
    if (ws && ws.readyState === 1 && ws.bufferedAmount < 400_000 && v.videoWidth) {
      const vw = v.videoWidth, vh = v.videoHeight;
      const rot = frameRotation();
      const side = rot === 90 || rot === 270;
      canvas.width = side ? vh : vw;
      canvas.height = side ? vw : vh;
      const g = canvas.getContext("2d");
      g.setTransform(1, 0, 0, 1, 0, 0);
      g.translate(canvas.width / 2, canvas.height / 2);
      g.rotate((rot * Math.PI) / 180);
      g.drawImage(v, -vw / 2, -vh / 2);
      canvas.toBlob((b) => {
        if (b && cam.ws === ws && ws.readyState === 1) {
          ws.send(b);
          const now = performance.now();
          fpsWindow = fpsWindow.filter((t) => now - t < 1000).concat(now);
          cam.shown = fpsWindow.length;
          const live = panel.querySelector(".pc-live");
          if (live) live.textContent = `● ${T("pc.live")} · ${cam.shown} fps · ${canvas.width}×${canvas.height}`;
        }
      }, "image/jpeg", cam.quality === "1080p" ? 0.7 : 0.75);
    }
    cam.timer = setTimeout(tick, 1000 / cam.fps);
  }

  /* pantalla siempre encendida mientras transmite */
  async function keepAwake() {
    try { cam.wake = await navigator.wakeLock?.request("screen"); } catch { /* */ }
  }
  function releaseWake() {
    try { cam.wake?.release(); } catch { /* */ }
    cam.wake = null;
  }
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible" && cam.running) keepAwake();
  });

  window.MiniDeck.registerWidget("phonecam", {
    label: "📷 " + (window.MiniDeckI18n ? T("pc.title") : "Webcam"),
    build,
    noAction: true,
  });
})();
