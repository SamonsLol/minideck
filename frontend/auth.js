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
    if (LOCAL) {
      try {
        const r = await fetch("/api/pair");
        if (r.ok) { write((await r.json()).token); syncManifest(); }
      } catch { /* servidor caído: reintentará al reconectar */ }
    }
    return read();
  }

  function api(url, opts = {}) {
    const headers = new Headers(opts.headers || {});
    const t = read();
    if (t) headers.set("X-MiniDeck-Token", t);
    return fetch(url, { ...opts, headers }).then((r) => {
      if (r.status === 401) showPairing("El código guardado ya no es válido.");
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

  function showPairing(reason) {
    if (document.getElementById("pairing")) return;
    write("");
    const ov = document.createElement("div");
    ov.id = "pairing";
    ov.setAttribute("role", "dialog");
    ov.setAttribute("aria-modal", "true");
    ov.style.cssText =
      "position:fixed;inset:0;z-index:9999;display:flex;align-items:center;" +
      "justify-content:center;padding:24px;background:rgba(10,12,16,.92);" +
      "color:#e6e9ef;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif";
    ov.innerHTML = `
      <form style="max-width:360px;width:100%;display:flex;flex-direction:column;gap:12px;text-align:center">
        <h2 style="margin:0;font-size:20px">Emparejar MiniDeck</h2>
        <p style="margin:0;opacity:.75;font-size:14px;line-height:1.45"></p>
        <p style="margin:0;opacity:.75;font-size:14px;line-height:1.45">
          En el equipo abre <b>http://localhost:${location.port || 80}/qr</b> y escanea
          el QR, o escribe aquí el código de emparejamiento.</p>
        <input name="code" autocomplete="off" autocapitalize="off" spellcheck="false"
               placeholder="Código" aria-label="Código de emparejamiento"
               style="padding:12px;border-radius:10px;border:1px solid #334;background:#151922;
                      color:inherit;font:16px ui-monospace,monospace;text-align:center">
        <button style="padding:12px;border:0;border-radius:10px;background:#60a5fa;
                       color:#0b0f17;font-weight:700;font-size:15px">Emparejar</button>
      </form>`;
    ov.querySelector("p").textContent = reason || "Este dispositivo aún no está autorizado.";
    ov.querySelector("form").onsubmit = (e) => {
      e.preventDefault();
      const code = ov.querySelector("input").value.trim();
      if (!code) return;
      write(code);
      location.replace(location.pathname);
    };
    document.body.appendChild(ov);
    ov.querySelector("input").focus();
  }

  window.MiniDeckAuth = { token: read, ensure, api, wsUrl, withToken, showPairing };
})();
