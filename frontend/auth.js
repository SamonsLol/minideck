/* SPDX-License-Identifier: AGPL-3.0-or-later
   SPDX-FileCopyrightText: 2026 Samons */
/* ============================================================
   MiniDeck — emparejamiento / token de acceso
   El servidor exige un token en /api y /ws. Se obtiene así:
     1) ?token=... en la URL (lo trae el QR de /qr)
     2) desde el propio equipo (localhost) vía /api/pair
     3) escribiéndolo a mano en la pantalla de emparejar
   Se guarda en localStorage y se reutiliza.
   ============================================================ */
(() => {
  const KEY = "minideck-token";
  const LOCAL = ["localhost", "127.0.0.1", "[::1]", "::1"].includes(location.hostname);

  function read() {
    try { return localStorage.getItem(KEY) || ""; } catch { return ""; }
  }
  function write(t) {
    try { t ? localStorage.setItem(KEY, t) : localStorage.removeItem(KEY); } catch {}
  }

  const fromUrl = new URLSearchParams(location.search).get("token");
  if (fromUrl) write(fromUrl);

  // El manifiesto lleva el token en start_url: así la app instalada en la
  // pantalla de inicio (que en iOS no comparte almacenamiento con Safari)
  // arranca ya emparejada.
  function syncManifest() {
    const t = read();
    const link = document.querySelector('link[rel="manifest"]');
    if (link && t) link.href = "manifest.webmanifest?token=" + encodeURIComponent(t);
  }
  syncManifest();

  async function ensure() {
    if (read()) return read();
    // ¿emparejado con cookie? (modo sin JS o QR abierto en el navegador)
    try {
      const r = await fetch("/api/info");
      if (r.ok) return "cookie";
    } catch { /* sin servidor: reintentará al reconectar */ }
    if (LOCAL) {
      try {
        const r = await fetch("/api/pair");
        if (r.ok) { write((await r.json()).token); syncManifest(); }
      } catch { /* servidor caído: reintentará al reconectar */ }
    }
    return read();
  }

  // Traducción si i18n.js está cargado (el panel no lo carga: queda en español).
  const tr = (k, v, fallback) =>
    window.MiniDeckI18n ? window.MiniDeckI18n.t(k, v) : fallback;

  function api(url, opts = {}) {
    const headers = new Headers(opts.headers || {});
    const t = read();
    if (t) headers.set("X-MiniDeck-Token", t);
    return fetch(url, { ...opts, headers }).then((r) => {
      if (r.status === 401) showPairing(tr("pair.invalid", null, "El código guardado ya no es válido."));
      return r;
    });
  }

  function withToken(path) {
    const t = read();
    if (!t) return path;
    return path + (path.includes("?") ? "&" : "?") + "token=" + encodeURIComponent(t);
  }

  function wsUrl(path) {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    return withToken(`${proto}://${location.host}${path}`);
  }

  let qrLoading = null;
  function loadQr() {
    if (window.MiniDeckQR) return Promise.resolve();
    qrLoading ??= new Promise((res, rej) => {
      const sc = document.createElement("script");
      sc.src = "/qrscan.js";
      sc.onload = res;
      sc.onerror = () => { qrLoading = null; rej(new Error("qrscan")); };
      document.head.appendChild(sc);
    });
    return qrLoading;
  }

  // Comprueba el código con el servidor ANTES de guardarlo.
  async function tryToken(code) {
    try {
      const r = await fetch("/api/info", { headers: { "X-MiniDeck-Token": code } });
      return r.ok;
    } catch { return false; }
  }

  const BTN = "padding:13px;border:0;border-radius:10px;font-weight:700;font-size:15px;";

  function showPairing(reason) {
    if (document.getElementById("pairing")) return;
    write("");
    const ov = document.createElement("div");
    ov.id = "pairing";
    ov.setAttribute("role", "dialog");
    ov.setAttribute("aria-modal", "true");
    ov.style.cssText =
      "position:fixed;inset:0;z-index:9999;display:flex;align-items:center;" +
      "justify-content:center;padding:24px;background:#0a0c10;overflow:auto;" +
      "color:#e6e9ef;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif";
    ov.innerHTML = `
      <form style="max-width:360px;width:100%;display:flex;flex-direction:column;gap:12px;text-align:center;margin:auto">
        <img src="/icons/icon-192.png" alt="" width="64" height="64"
             style="align-self:center;border-radius:16px">
        <h2 style="margin:0;font-size:20px"></h2>
        <p class="pair-reason" style="margin:0;opacity:.75;font-size:14px;line-height:1.45"></p>
        <p class="pair-help" style="margin:0;opacity:.75;font-size:14px;line-height:1.45"></p>
        <button type="button" class="pair-scan" style="${BTN}background:#60a5fa;color:#0b0f17"></button>
        <div class="pair-live" style="display:flex;flex-direction:column;gap:8px"></div>
        <p class="pair-status" role="status" aria-live="polite"
           style="margin:0;min-height:1.2em;font-size:13.5px;color:#fbbf24"></p>
        <div class="pair-or" style="opacity:.5;font-size:12px"></div>
        <input name="code" autocomplete="off" autocapitalize="off" spellcheck="false"
               style="padding:12px;border-radius:10px;border:1px solid #334;background:#151922;
                      color:inherit;font:16px ui-monospace,monospace;text-align:center">
        <button type="submit" class="pair-go" style="${BTN}background:#262c36;color:#e6e9ef"></button>
      </form>`;
    const $q = (sel) => ov.querySelector(sel);
    const qrUrl = `http://localhost:${location.port || 80}/qr`;
    $q("h2").textContent = tr("pair.title", null, "Emparejar MiniDeck");
    $q(".pair-reason").textContent =
      reason || tr("pair.reason", null, "Este dispositivo aún no está autorizado.");
    // el texto es nuestro; la URL se limpia al ir dentro de <b>
    const safeUrl = qrUrl.replace(/[<>&"]/g, "");
    $q(".pair-help").innerHTML = tr("pair.help", { url: safeUrl },
      `En el equipo abre <b>${safeUrl}</b> y escanea el QR desde aquí, o escribe el código.`);
    const scanLabel = () => "📷 " + tr("pair.scan", null, "Escanear QR");
    $q(".pair-scan").textContent = scanLabel();
    $q(".pair-or").textContent = tr("pair.or", null, "o escribe el código");
    const input = $q("input");
    input.placeholder = tr("pair.code", null, "Código");
    input.setAttribute("aria-label", input.placeholder);
    $q(".pair-go").textContent = tr("pair.go", null, "Emparejar");
    const status = (msg, ok) => {
      $q(".pair-status").textContent = msg || "";
      $q(".pair-status").style.color = ok ? "#4ade80" : "#fbbf24";
    };

    async function accept(code) {
      if (!code) return;
      status(tr("pair.checking", null, "Comprobando…"), true);
      if (await tryToken(code)) {
        write(code);
        status(tr("pair.ok", null, "¡Emparejado!"), true);
        location.replace(location.pathname);
      } else {
        status(tr("pair.badCode", null, "Ese código no es de este equipo o ya no es válido."));
      }
    }

    let live = null;
    $q(".pair-scan").onclick = async () => {
      status("");
      if (live) { live.stop(); return; }
      try { await loadQr(); } catch {
        status(tr("pair.scanFail", null, "No se pudo cargar el lector de QR."));
        return;
      }
      const QR = window.MiniDeckQR;
      let text;
      if (QR.canLive()) {
        // HTTPS / localhost: cámara en vivo
        $q(".pair-scan").textContent = tr("pair.cancel", null, "Cancelar");
        live = QR.scanLive($q(".pair-live"));
        text = await live.promise;
        live = null;
        $q(".pair-scan").textContent = scanLabel();
        if (text === undefined) text = await QR.scanPhoto();   // sin permiso: foto
      } else {
        // HTTP en la red local: foto del QR (la cámara en vivo exige HTTPS)
        status(tr("pair.photoHint", null, "Haz una foto al QR de la pantalla del equipo."), true);
        text = await QR.scanPhoto();
      }
      if (text === null) { status(""); return; }            // cancelado
      const code = QR.tokenFrom(text);
      if (!code) {
        status(tr("pair.notFound", null,
          "No se leyó ningún QR de MiniDeck. Acércate un poco y vuelve a intentarlo."));
        return;
      }
      input.value = code;
      accept(code);
    };
    $q("form").onsubmit = (e) => {
      e.preventDefault();
      accept(input.value.trim());
    };
    document.body.appendChild(ov);
  }

  window.MiniDeckAuth = { token: read, ensure, api, wsUrl, withToken, showPairing };
})();
