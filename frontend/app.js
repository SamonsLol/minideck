/* SPDX-License-Identifier: AGPL-3.0-or-later
   SPDX-FileCopyrightText: 2026 Samons */
/* ============================================================
   MiniDeck — cliente
   Conecta por WebSocket, renderiza el deck desde la config
   y envía pulsaciones. Reconexión automática incluida.
   ============================================================ */

const $ = (id) => document.getElementById(id);
// Traducción (i18n.js). Se llama T y no t para no chocar con variables locales.
const T = (key, vars) => window.MiniDeckI18n.t(key, vars);

const state = {
  ws: null,
  config: null,
  currentPage: null,
  reconnectDelay: 500,   // crece hasta 8s
  pingTimer: null,
  live: {},              // último estado recibido (para botones con "when")
  pageHistory: [],       // para "page": "back" (carpetas)
};

/* ============================================================
   SISTEMA DE WIDGETS / PLUGINS
   Un plugin registra su widget desde su widget.js con:
     window.MiniDeck.registerWidget("mi_tipo", {
       label: "Mi widget",            // nombre en el editor
       build(w) { return elemento },  // construye el DOM del widget
       stateKey: "mi_estado",         // opcional: clave del estado
       sync(data) { ... },            // opcional: pinta el estado
       noAction: true,                // sin acción/params en el editor
       keepParams: true,              // params sí, acción no (ej. discord)
       slider: true,                  // muestra campos de slider
     });
   Y en el servidor: @action("mi_estado_get", state=True)
   ============================================================ */
const WIDGETS = {};

function registerWidget(type, def) {
  WIDGETS[type] = def;
}

function runAction(action, params) {
  if (state.ws?.readyState !== WebSocket.OPEN) { toast("Sin conexión", true); return; }
  state.ws.send(JSON.stringify({ type: "run", action, params: params ?? {} }));
}

async function loadPlugins() {
  try {
    const assets = await (await MiniDeckAuth.api("/api/plugins")).json();
    await Promise.all(assets.map(a => new Promise((res) => {
      if (a.type === "css") {
        const l = document.createElement("link");
        l.rel = "stylesheet"; l.href = a.url;
        l.onload = l.onerror = res;
        document.head.appendChild(l);
      } else {
        const s = document.createElement("script");
        s.src = a.url;
        s.onload = s.onerror = res;
        document.body.appendChild(s);
      }
    })));
  } catch { /* sin plugins */ }
}

// API pública para los widget.js de los plugins
window.MiniDeck = { registerWidget, run: runAction, toast, renderIcon,
                    get state() { return state; } };

/* ---------- widgets personalizados (creados en el Panel de Control) ----
   Viven en deck.json bajo "customWidgets": { id: {name, html, js, css} }.
   El HTML es el diseño, el CSS se inyecta, y el JS recibe un `ctx` con:
     ctx.el                       → el elemento raíz del widget
     ctx.w                        → su config del deck (id, color, params…)
     ctx.run(accion, params)      → ejecuta cualquier acción del servidor
     ctx.onState(clave, fn)       → reacciona al estado en vivo
     ctx.toast(texto, esError)    → notificación
     ctx.renderIcon(el, icono, color) */
const customSubs = [];
const loadedLibs = new Set();
let pendingLibs = [];

/* carga las librerías externas (CDN) declaradas por widgets personalizados,
   en orden y una sola vez, ANTES de que corra su JS */
function ensureCustomLibs() {
  const urls = pendingLibs.filter(u => !loadedLibs.has(u));
  pendingLibs = [];
  return Promise.all(urls.map(u => new Promise((res) => {
    loadedLibs.add(u);
    if (u.split("?")[0].endsWith(".css")) {
      const l = document.createElement("link");
      l.rel = "stylesheet"; l.href = u;
      l.onload = l.onerror = res;
      document.head.appendChild(l);
    } else {
      const s = document.createElement("script");
      s.src = u;
      s.async = false;   // respetar el orden declarado (dependencias entre libs)
      s.onload = s.onerror = res;
      document.body.appendChild(s);
    }
  })));
}

function registerCustomWidgets(cfg) {
  for (const k of Object.keys(WIDGETS)) {
    if (k.startsWith("custom:")) delete WIDGETS[k];
  }
  let cssAll = "";
  for (const [id, d] of Object.entries(cfg.customWidgets ?? {})) {
    cssAll += (d.css || "") + "\n";
    for (const u of (d.libs ?? [])) pendingLibs.push(u);
    WIDGETS["custom:" + id] = {
      label: "✦ " + (d.name || id),
      keepParams: true,
      build: (w) => buildCustom(w, d),
    };
  }
  let tag = $("customCss");
  if (!tag) {
    tag = document.createElement("style");
    tag.id = "customCss";
    document.head.appendChild(tag);
  }
  tag.textContent = cssAll;
}

function buildCustom(w, d) {
  const el = document.createElement("div");
  el.className = "custom-widget";
  el.dataset.id = w.id;
  el.style.setProperty("--led", w.color || "#8a93a3");
  el.innerHTML = d.html || "";
  const ctx = {
    el, w,
    run: runAction,
    toast,
    renderIcon,
    get state() { return state; },
    onState(key, fn) { customSubs.push({ key, fn }); },
  };
  try {
    new Function("ctx", d.js || "")(ctx);
  } catch (e) {
    console.error(`widget ${w.type}:`, e);
    el.innerHTML = `<div class="custom-err">⚠︎ ${e.message}</div>`;
  }
  return el;
}

/* dispatcher de estado: reparte cada clave a su widget */
function dispatchState(data) {
  Object.assign(state.live, data);
  syncStatefulButtons();
  renderSystemState(data);
  syncSliders(data);
  if (typeof data.muted === "boolean") syncMuteButtons(data.muted);
  if (typeof data.activeApp === "string") handleActiveApp(data.activeApp);
  for (const def of Object.values(WIDGETS)) {
    if (def.stateKey && def.sync && data[def.stateKey] !== undefined) {
      try { def.sync(data[def.stateKey]); } catch (e) { console.error(e); }
    }
  }
  for (const s of customSubs) {
    if (data[s.key] !== undefined) {
      try { s.fn(data[s.key]); } catch (e) { console.error(e); }
    }
  }
}

/* ------------------------------------------------ botones con estado
   Un botón puede cambiar de icono/color/texto según el estado en vivo:
     "when": { "key": "obs.recording",          ← ruta en el estado
               "equals": true,                   ← opcional (por defecto: truthy)
               "icon": "lucide:circle-stop", "color": "#f87171", "label": "Grabando" }
   La ruta admite claves con puntos (ej. "ha.entities.light.salon.state"):
   en cada nivel se prueba primero la clave más larga que exista. */
function statePath(obj, path) {
  const parts = String(path).split(".");
  let cur = obj;
  let i = 0;
  while (i < parts.length) {
    if (cur == null || typeof cur !== "object") return undefined;
    let j = parts.length;
    for (; j > i; j--) {
      const k = parts.slice(i, j).join(".");
      if (Object.prototype.hasOwnProperty.call(cur, k)) { cur = cur[k]; break; }
    }
    if (j === i) return undefined;
    i = j;
  }
  return cur;
}

function whenActive(when) {
  const v = statePath(state.live, when.key);
  if ("equals" in when) return String(v) === String(when.equals);
  return Boolean(v) && v !== "off" && v !== "unavailable";
}

function paintKey(el, btn, on) {
  const w = on ? btn.when : {};
  const color = w.color || btn.color || "#8a93a3";
  const icon = w.icon || btn.icon;
  const label = w.label ?? btn.label ?? "";
  const sig = `${icon}|${color}|${label}`;
  if (el.dataset.sig === sig) return;
  el.dataset.sig = sig;
  el.classList.toggle("is-on", Boolean(on));
  el.style.setProperty("--led", color);
  const iconEl = el.querySelector(".icon");
  iconEl.innerHTML = "";
  const iconColor = btn.iconColor === "led" || on ? color : (btn.iconColor || "#c9d1dd");
  renderIcon(iconEl, icon, iconColor);
  el.querySelector(".label").textContent = label;
}

function syncStatefulButtons() {
  if (!state.config || state.editMode) return;
  const page = state.config.pages.find(p => p.id === state.currentPage);
  for (const btn of page?.buttons || []) {
    if (!btn.when?.key) continue;
    const el = document.querySelector(`.key[data-id="${CSS.escape(btn.id)}"]`);
    if (el) paintKey(el, btn, whenActive(btn.when));
  }
}

// Los botones con acción "volume_mute" cambian su icono según el estado de
// silencio del sistema (volume-x en rojo si está silenciado, volume-2 si no).
function syncMuteButtons(muted) {
  if (!state.config) return;
  for (const page of state.config.pages || []) {
    for (const b of page.buttons || []) {
      if (b.action !== "volume_mute") continue;
      const icon = document.querySelector(`.key[data-id="${b.id}"] .icon`);
      if (!icon || icon.dataset.muted === String(muted)) continue;
      icon.dataset.muted = String(muted);
      icon.innerHTML = "";
      renderIcon(icon, muted ? "lucide:volume-x" : "lucide:volume-2",
                 muted ? "#f87171" : "#c9d1dd");
    }
  }
}

/* ------------------------------------------------ conexión */
function connect() {
  if (state.unauthorized) return;
  const ws = new WebSocket(MiniDeckAuth.wsUrl("/ws"));
  state.ws = ws;

  ws.onopen = () => {
    $("statusDot").classList.add("connected");
    $("offlineBanner").hidden = true;
    state.reconnectDelay = 500;
    // si quedó un guardado pendiente de cuando no había conexión, enviarlo
    if (state.pendingSave) saveConfig();
    // sincronizar sliders/estado al conectar
    ws.send(JSON.stringify({ type: "run", action: "volume_get", params: {} }));
    // keep-alive para que iOS no mate la conexión en segundo plano
    clearInterval(state.pingTimer);
    state.pingTimer = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ping" }));
    }, 25000);
  };

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    if (msg.type === "config") {
      // el servidor reenvía la config al guardar y también cuando detecta el
      // cambio en disco: si es idéntica, no repintar (cortaría una pulsación
      // larga en curso y provoca parpadeos)
      const json = JSON.stringify(msg.data);
      if (json === state.configJson && !state.editMode) return;
      state.configJson = json;
      state.config = msg.data;
      registerCustomWidgets(msg.data);
      ensureCustomLibs().then(() => {
        if (!state.currentPage ||
            !state.config.pages.some(p => p.id === state.currentPage)) {
          state.currentPage = state.config.pages[0]?.id ?? null;
        }
        render();
      });
    } else if (msg.type === "result") {
      handleResult(msg);
      if (msg.state) dispatchState(msg.state);
      if (msg.lyrics || msg.syncedLyrics)
        showLyrics(msg.lyricsTitle, msg.lyrics, msg.syncedLyrics);
    } else if (msg.type === "state") {
      dispatchState(msg.data);
    }
  };

  ws.onclose = (ev) => {
    $("statusDot").classList.remove("connected");
    clearInterval(state.pingTimer);
    if (ev.code === 4401) {            // token ausente o inválido
      state.unauthorized = true;
      MiniDeckAuth.showPairing();
      return;
    }
    // aviso visible (no solo el punto de estado) mientras se reconecta
    $("offlineBanner").hidden = false;
    setTimeout(connect, state.reconnectDelay);
    state.reconnectDelay = Math.min(state.reconnectDelay * 2, 8000);
  };

  ws.onerror = () => ws.close();
}

// Reconectar de inmediato cuando el iPhone vuelve del reposo
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" &&
      state.ws?.readyState !== WebSocket.OPEN) {
    connect();
  }
});

/* ------------------------------------------------ render */
function render() {
  const cfg = state.config;
  $("deckName").textContent = cfg.name || "MiniDeck";
  document.documentElement.style.setProperty("--cols", cfg.grid?.columns ?? 4);
  document.documentElement.style.setProperty("--gap", `${cfg.grid?.gap ?? 16}px`);
  renderTabs();
  renderGrid();
}

function renderTabs() {
  const nav = $("pageTabs");
  nav.innerHTML = "";
  for (const page of state.config.pages) {
    const tab = document.createElement("button");
    tab.className = "page-tab" + (page.id === state.currentPage ? " active" : "");
    tab.textContent = page.name;
    tab.onclick = () => {
      const pages = state.config.pages;
      const cur = pages.findIndex(p => p.id === state.currentPage);
      const tgt = pages.findIndex(p => p.id === page.id);
      if (tgt === cur) return;
      goToPage(page.id, tgt > cur ? 1 : -1);
    };
    nav.appendChild(tab);
  }
  if (state.editMode) {
    const mk = (txt, fn, title) => {
      const b = document.createElement("button");
      b.className = "page-tab tool";
      b.textContent = txt;
      b.title = title;
      b.onclick = fn;
      nav.appendChild(b);
    };
    mk("＋", addPage, T("tool.addPage"));
    mk("✎", renamePage, T("tool.renamePage"));
    mk("🗑", deletePage, T("tool.deletePage"));
    mk("↶", undoLast, T("tool.undo"));
    mk("⇩", exportDeck, T("tool.export"));
    mk("⇧", importDeck, T("tool.import"));
  }
}

function renderGrid() {
  const grid = $("grid");
  grid.innerHTML = "";
  customSubs.length = 0;
  const page = state.config.pages.find(p => p.id === state.currentPage);
  if (!page) return;

  page.buttons.forEach((btn, i) => {
    const def = WIDGETS[btn.type];
    const el = def ? def.build(btn) : buildKey(btn);
    applySpan(el, btn);
    if (state.editMode) {
      el.classList.add("edit");
      el.dataset.idx = i;
      el.oncontextmenu = (e) => e.preventDefault();
      el.onclick = (e) => {
        if (drag.justDragged) return;   // el toque fue un arrastre, no un tap
        e.preventDefault();
        openEditor(i);
      };
      attachDrag(el);
    }
    grid.appendChild(el);
  });

  if (state.editMode) {
    const add = document.createElement("button");
    add.className = "key add-tile";
    add.innerHTML = `<span class="icon">＋</span><span class="label"></span>`;
    add.querySelector(".label").textContent = T("grid.add");
    add.onclick = () => {
      const w = newWidget();
      currentPage().buttons.push(w);
      saveConfig();
      openEditor(currentPage().buttons.length - 1);
    };
    grid.appendChild(add);
  }
}

/* Bento box: cada widget puede ocupar varias celdas.
   "w": columnas que abarca (o "full")   "h": filas que abarca
   Ej: { "w": 2, "h": 2 } → cuadrado grande.  Sin w/h → celda 1x1. */
function applySpan(el, btn) {
  const cols = state.config?.grid?.columns ?? 4;
  if (btn.w === "full") {
    el.style.gridColumn = "1 / -1";
  } else if (btn.w) {
    el.style.gridColumn = `span ${Math.min(Number(btn.w), cols)}`;
  }
  if (btn.h) el.style.gridRow = `span ${Number(btn.h)}`;
}

function buildKey(btn) {
  const el = document.createElement("button");
  el.className = "key";
  el.dataset.id = btn.id;
  el.style.setProperty("--led", btn.color || "#8a93a3");

  const icon = document.createElement("span");
  icon.className = "icon";
  const iconColor = btn.iconColor === "led"
    ? (btn.color || "#e8ecf2")
    : (btn.iconColor || "#c9d1dd");
  renderIcon(icon, btn.icon, iconColor);

  const label = document.createElement("span");
  label.className = "label";
  label.textContent = btn.label ?? "";

  el.append(icon, label);
  if (btn.when?.key) {
    el.dataset.sig = "";
    paintKey(el, btn, !state.editMode && whenActive(btn.when));
  }
  attachPress(el, btn);
  return el;
}

/* Toque normal → "action". Mantener pulsado (LONG_MS) → "longAction" si el
   botón la tiene; el aviso háptico confirma que se disparó. */
const LONG_MS = 550;
function attachPress(el, btn) {
  if (!btn.longAction) {
    el.onclick = () => press(btn, el);
    return;
  }
  el.classList.add("has-long");
  let timer = null, fired = false, sx = 0, sy = 0;
  const cancel = () => { clearTimeout(timer); timer = null; };
  el.addEventListener("pointerdown", (e) => {
    if (state.editMode) return;
    fired = false; sx = e.clientX; sy = e.clientY;
    // capturar el puntero: la tecla se encoge al pulsarla (:active) y, si es
    // alta, su borde pasa bajo el dedo y el navegador emitiría pointerleave
    try { el.setPointerCapture(e.pointerId); } catch { /* sin soporte */ }
    timer = setTimeout(() => {
      fired = true;
      navigator.vibrate?.(30);
      press(btn, el, true);
    }, LONG_MS);
  });
  el.addEventListener("pointermove", (e) => {
    if (timer && Math.hypot(e.clientX - sx, e.clientY - sy) > 12) cancel();
  });
  // solo se cancela si el dedo se desplaza (scroll/swipe), no por pointerleave
  el.addEventListener("pointerup", cancel);
  el.addEventListener("pointercancel", cancel);
  el.oncontextmenu = (e) => e.preventDefault();   // sin menú de "copiar" en iOS
  el.onclick = () => {
    if (fired) { fired = false; return; }       // ya se ejecutó la larga
    press(btn, el);
  };
}

/* Slider: ocupa una fila completa. Config:
   { "type": "slider", "id": "...", "label": "Volumen", "icon": "lucide:volume-2",
     "color": "#60a5fa", "min": 0, "max": 100, "step": 1,
     "action": "volume_set", "valueParam": "level", "bind": "volume" }
   - action/valueParam: qué acción ejecutar y en qué parámetro va el valor.
   - bind: clave del estado del servidor que mantiene el slider sincronizado. */
function buildSlider(w) {
  const el = document.createElement("div");
  el.className = "slider-widget";
  el.dataset.id = w.id;
  if (w.bind) el.dataset.bind = w.bind;
  el.style.setProperty("--led", w.color || "#8a93a3");

  const icon = document.createElement("span");
  icon.className = "icon";
  renderIcon(icon, w.icon, w.iconColor || "#c9d1dd");

  const label = document.createElement("span");
  label.className = "slider-label";
  label.textContent = w.label ?? "";

  const value = document.createElement("span");
  value.className = "slider-value";

  const input = document.createElement("input");
  input.type = "range";
  input.min = w.min ?? 0;
  input.max = w.max ?? 100;
  input.step = w.step ?? 1;
  input.value = w.min ?? 0;

  const paint = () => {
    const pct = ((input.value - input.min) / (input.max - input.min)) * 100;
    input.style.setProperty("--fill", `${pct}%`);
    value.textContent = input.value + (w.unit ?? "%");
  };
  paint();

  // Mientras arrastras: envía como máximo cada 120 ms. Al soltar: valor final.
  let last = 0;
  const send = (val) => {
    if (state.ws?.readyState !== WebSocket.OPEN) return;
    state.ws.send(JSON.stringify({
      type: "run",
      action: w.action,
      params: { ...(w.params ?? {}), [w.valueParam ?? "level"]: Number(val) },
    }));
  };
  input.addEventListener("input", () => {
    paint();
    const now = Date.now();
    if (now - last > 120) { last = now; send(input.value); }
  });
  input.addEventListener("change", () => send(input.value));

  const head = document.createElement("div");
  head.className = "slider-head";
  head.append(icon, label, value);
  el.append(head, input);
  return el;
}

/* Now Playing: muestra y controla lo que suena en el PC (YT Music, etc.)
   Config: { "type": "nowplaying", "id": "np", "color": "#f472b6", "w": "full", "h": 2 }
   Se alimenta solo del estado que difunde el servidor cada segundo. */
function buildNowPlaying(w) {
  const el = document.createElement("div");
  el.className = "np-widget";
  el.dataset.id = w.id;
  el.style.setProperty("--led", w.color || "#f472b6");

  el.innerHTML = `
    <div class="np-main">
      <div class="np-art"></div>
      <div class="np-info">
        <div class="np-title">${T("np.nothing")}</div>
        <div class="np-artist">—</div>
      </div>
      <button class="np-btn np-lyrics" title="${T("np.lyrics")}"></button>
    </div>
    <div class="np-seek-row">
      <span class="np-time np-pos">0:00</span>
      <input type="range" class="np-seek" min="0" max="100" step="1" value="0">
      <span class="np-time np-dur">0:00</span>
    </div>
    <div class="np-controls">
      <button class="np-btn np-prev"></button>
      <button class="np-btn np-play np-big"></button>
      <button class="np-btn np-next"></button>
    </div>`;

  renderIcon(el.querySelector(".np-prev"),   "lucide:skip-back",    "#e8ecf2");
  renderIcon(el.querySelector(".np-play"),   "lucide:play",         "#0f1216");
  renderIcon(el.querySelector(".np-next"),   "lucide:skip-forward", "#e8ecf2");
  renderIcon(el.querySelector(".np-lyrics"), "lucide:mic-vocal",    "#c9d1dd");

  const send = (cmd, extra = {}) => {
    if (state.ws?.readyState !== WebSocket.OPEN) return;
    state.ws.send(JSON.stringify({ type: "run", action: "now_playing",
                                   params: { cmd, ...extra } }));
  };
  el.querySelector(".np-prev").onclick = () => send("previous");
  el.querySelector(".np-play").onclick = () => send("play_pause");
  el.querySelector(".np-next").onclick = () => send("next");
  el.querySelector(".np-lyrics").onclick = () => {
    if (state.ws?.readyState !== WebSocket.OPEN) return;
    state.ws.send(JSON.stringify({ type: "run", action: "lyrics_get", params: {} }));
    toast("Buscando letra…", false);
  };

  const seek = el.querySelector(".np-seek");
  const seekPos = el.querySelector(".np-pos");
  // marcar que se está arrastrando (en iOS el slider no recibe focus)
  const startSeek = () => { _npSeeking = true; };
  seek.addEventListener("pointerdown", startSeek);
  seek.addEventListener("touchstart", startSeek, { passive: true });
  seek.addEventListener("mousedown", startSeek);
  // feedback inmediato mientras arrastra (relleno + tiempo), sin esperar al server
  seek.addEventListener("input", () => {
    _npSeeking = true;
    const v = Number(seek.value);
    const max = Number(seek.max) || 0;
    seek.style.setProperty("--fill", max ? `${(v / max) * 100}%` : "0%");
    if (seekPos) seekPos.textContent = fmtTime(v);
  });
  // al soltar: enviar la posición y bloquear la sobreescritura ~1.5s
  seek.addEventListener("change", () => {
    send("seek", { position: Number(seek.value) });
    _npSeeking = false;
    _npSeekUntil = Date.now() + 1500;
  });

  return el;
}

let _npStatus = null;
let _npTitle = null;
let _npThumbId = null;
// Mientras el usuario arrastra la barra (y un instante después, hasta que el
// servidor refleje la nueva posición) no dejamos que el estado la sobreescriba.
let _npSeeking = false;
let _npSeekUntil = 0;
function syncNowPlaying(np) {
  // reloj local para interpolar la posición entre updates (letra karaoke)
  state.np = { position: np.position || 0, status: np.status, at: Date.now() };

  // si cambia la canción con el panel de letra abierto, buscar la nueva
  if (np.active && np.title !== _npTitle) {
    _npTitle = np.title;
    const panel = $("lyricsPanel");
    if (panel?.classList.contains("open") &&
        state.ws?.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify({ type: "run", action: "lyrics_get", params: {} }));
    }
  }

  const el = document.querySelector(".np-widget");
  if (!el) return;

  const title = el.querySelector(".np-title");
  const artist = el.querySelector(".np-artist");
  const seek = el.querySelector(".np-seek");
  const pos = el.querySelector(".np-pos");
  const dur = el.querySelector(".np-dur");

  if (!np.active) {
    title.textContent = T("np.nothing");
    artist.textContent = "—";
    return;
  }
  title.textContent = np.title || "Sin título";
  artist.textContent = np.artist || "";

  // carátula: URL directa (np.artwork, de YouTube/Spotify) o /api/artwork (Windows).
  // Además se usa como FONDO del bloque, atenuada para que el texto sea legible.
  const art = el.querySelector(".np-art");
  const src = np.artwork ? `url("${np.artwork}")`
            : (np.thumbId ? `url(${MiniDeckAuth.withToken("/api/artwork?v=" + encodeURIComponent(np.thumbId))})` : "");
  const key = np.artwork || np.thumbId || "";
  if (key !== _npThumbId) {
    _npThumbId = key;
    art.style.backgroundImage = src;
    if (src) {
      el.style.backgroundImage =
        `linear-gradient(rgba(18,18,18,0.55), rgba(18,18,18,0.72)), ${src}`;
      el.style.backgroundSize = "cover";
      el.style.backgroundPosition = "center";
      el.classList.add("has-art");
    } else {
      el.style.backgroundImage = "";
      el.classList.remove("has-art");
    }
  }

  const hasDur = (np.duration || 0) > 0;
  seek.disabled = !hasDur;
  // no sobreescribir la barra mientras el usuario la arrastra (ni el instante
  // posterior, hasta que el servidor refleje la posición nueva)
  const busy = document.activeElement === seek || _npSeeking ||
               Date.now() < _npSeekUntil;
  if (!busy) {
    seek.max = hasDur ? np.duration : 100;
    // si está sonando, solo corregir cuando el desfase real supera 1.5s;
    // los micro-ajustes los hace el reloj local sin saltos visibles
    const target = hasDur ? Math.min(np.position || 0, np.duration) : 0;
    const shown = Number(seek.value) || 0;
    if (np.status !== "playing" || Math.abs(target - shown) > 1.5) {
      seek.value = target;
      const pct = hasDur ? (target / np.duration) * 100 : 0;
      seek.style.setProperty("--fill", `${pct}%`);
      pos.textContent = fmtTime(target);
    }
  }
  dur.textContent = hasDur ? fmtTime(np.duration) : "–:––";

  // Icono play/pausa: guardamos el estado en el propio elemento (no en una
  // variable global) para que sea correcto también tras recrear el widget.
  const play = el.querySelector(".np-play");
  const want = np.status === "playing" ? "pause" : "play";
  if (play && play.dataset.state !== want) {
    play.dataset.state = want;
    play.innerHTML = "";
    renderIcon(play, "lucide:" + want, "#0f1216");
  }
  _npStatus = np.status;
}

function fmtTime(s) {
  s = Math.max(0, Math.floor(s || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/* Panel de letra — karaoke si hay letra sincronizada (LRC), plana si no.
   Un reloj local interpola la posición entre los updates del servidor
   (que llegan cada 1s) para que el resaltado avance con fluidez. */
const lyr = { lines: null, timer: null, activeIdx: -1 };

function parseLRC(text) {
  const lines = [];
  for (const raw of text.split("\n")) {
    const m = raw.match(/^\[(\d+):(\d+(?:\.\d+)?)\](.*)$/);
    if (!m) continue;
    const t = parseInt(m[1]) * 60 + parseFloat(m[2]);
    const s = m[3].trim();
    if (s) lines.push({ t, s });
  }
  return lines.length ? lines : null;
}

function currentSongTime() {
  const np = state.np;
  if (!np) return 0;
  // Calibración opcional en deck.json: "nowplaying": { "offset": -0.5 }
  // (positivo adelanta la barra/letra; negativo la atrasa)
  const offset = Number(state.config?.nowplaying?.offset ?? 0);
  if (np.status !== "playing") return np.position + offset;
  return np.position + (Date.now() - np.at) / 1000 + offset;
}

function showLyrics(title, plain, synced) {
  let panel = $("lyricsPanel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "lyricsPanel";
    panel.className = "lyrics-panel";
    panel.innerHTML = `
      <div class="lyrics-head">
        <span class="lyrics-title"></span>
        <button class="lyrics-close">✕</button>
      </div>
      <div class="lyrics-body"></div>`;
    panel.querySelector(".lyrics-close").onclick = closeLyrics;
    document.body.appendChild(panel);
  }
  panel.querySelector(".lyrics-title").textContent = title || "Letra";
  const body = panel.querySelector(".lyrics-body");
  body.innerHTML = "";
  clearInterval(lyr.timer);
  lyr.lines = synced ? parseLRC(synced) : null;
  lyr.activeIdx = -1;

  if (lyr.lines) {
    body.classList.add("karaoke");
    for (const line of lyr.lines) {
      const div = document.createElement("div");
      div.className = "lyr-line";
      div.textContent = line.s;
      body.appendChild(div);
    }
    lyr.timer = setInterval(tickKaraoke, 250);
    tickKaraoke();
  } else {
    body.classList.remove("karaoke");
    const pre = document.createElement("div");
    pre.className = "lyr-plain";
    pre.textContent = plain || "";
    body.appendChild(pre);
  }
  panel.classList.add("open");
}

function tickKaraoke() {
  if (!lyr.lines) return;
  const t = currentSongTime();
  let idx = -1;
  for (let i = 0; i < lyr.lines.length; i++) {
    if (lyr.lines[i].t <= t) idx = i; else break;
  }
  if (idx === lyr.activeIdx) return;
  lyr.activeIdx = idx;
  const els = document.querySelectorAll("#lyricsPanel .lyr-line");
  els.forEach((el, i) => el.classList.toggle("active", i === idx));
  if (idx >= 0 && els[idx]) {
    els[idx].scrollIntoView({ behavior: "smooth", block: "center" });
  }
}

function closeLyrics() {
  const panel = $("lyricsPanel");
  if (panel) panel.classList.remove("open");
  clearInterval(lyr.timer);
  lyr.timer = null;
}

/* Widget Discord: mute con estado real + quién está en tu canal de voz
   (los que hablan se iluminan). Requiere server/config/discord.json
   configurado (ver instrucciones en server/actions/discord_rpc.py).
   Config del widget:
   { "id": "dc", "type": "discord", "color": "#5865f2", "w": "full", "h": 2,
     "params": {
       "webhook": "https://discord.com/api/webhooks/…",   ← opcional
       "quick": ["Ya voy 🎮", "gg"],                        ← opcional
       "muteKeys": "ctrl+shift+m"   ← fallback si el RPC no conecta
     } } */
function buildDiscord(w) {
  const p = w.params ?? {};
  const el = document.createElement("div");
  el.className = "dc-widget";
  el.dataset.id = w.id;
  el.style.setProperty("--led", w.color || "#5865f2");

  el.innerHTML = `
    <div class="dc-head">
      <span class="icon"></span>
      <div class="dc-chan">
        <div class="dc-title">${w.label || "Discord"}</div>
        <div class="dc-sub">Conectando…</div>
      </div>
      <button class="dc-btn dc-mute" title="Silenciar micro"></button>
    </div>
    <div class="dc-members"></div>
    <div class="dc-quick"></div>
    <div class="dc-compose">
      <input class="dc-input" type="text" placeholder="Mensaje al canal…"
             autocomplete="off" autocapitalize="sentences">
      <button class="dc-btn dc-send" title="Enviar"></button>
    </div>`;

  renderIcon(el.querySelector(".dc-head .icon"), "simple-icons:discord",
             w.color || "#5865f2");
  renderIcon(el.querySelector(".dc-mute"), "lucide:mic-off", "#e8ecf2");
  renderIcon(el.querySelector(".dc-send"), "lucide:send", "#e8ecf2");

  const run = (action, params) => {
    if (state.ws?.readyState !== WebSocket.OPEN) { toast("Sin conexión", true); return; }
    state.ws.send(JSON.stringify({ type: "run", action, params }));
  };

  el.querySelector(".dc-mute").onclick = () => {
    if (state.discord?.connected) run("discord_mute", {});
    else if (p.muteKeys) run("hotkey", { keys: p.muteKeys });
    else toast("Discord RPC no conectado (revisa server/config/discord.json)", true);
  };

  const sendMsg = (content) => {
    if (!p.webhook) { toast("Configura el webhook del canal", true); return; }
    if (!content.trim()) return;
    run("discord_webhook", { url: p.webhook, content,
                             username: p.username || "MiniDeck" });
  };

  const quick = el.querySelector(".dc-quick");
  for (const q of (p.quick ?? [])) {
    const chip = document.createElement("button");
    chip.className = "dc-chip";
    chip.textContent = q;
    chip.onclick = () => sendMsg(q);
    quick.appendChild(chip);
  }
  if (!(p.quick ?? []).length) quick.style.display = "none";
  if (!p.webhook) el.querySelector(".dc-compose").style.display = "none";

  const input = el.querySelector(".dc-input");
  const doSend = () => { sendMsg(input.value); input.value = ""; input.blur(); };
  el.querySelector(".dc-send").onclick = doSend;
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") doSend(); });

  if (state.discord) syncDiscord(state.discord);
  return el;
}

/* Pinta el estado de Discord en el widget: mute, canal y voces */
function syncDiscord(d) {
  state.discord = d;
  const el = document.querySelector(".dc-widget");
  if (!el) return;

  el.querySelector(".dc-mute").classList.toggle("on", !!d.mute);

  const sub = el.querySelector(".dc-sub");
  sub.textContent = !d.connected ? "RPC desconectado"
                  : d.channel ? d.channel
                  : "Sin canal de voz";

  const box = el.querySelector(".dc-members");
  box.innerHTML = "";
  for (const m of (d.members ?? [])) {
    const pill = document.createElement("span");
    pill.className = "dc-member" + (m.speaking ? " speaking" : "");
    pill.textContent = m.name;
    box.appendChild(pill);
  }
  box.style.display = (d.members ?? []).length ? "" : "none";
}

/* Widget Mixer: mezclador de volumen por aplicación, como el de Windows.
   Config: { "id": "mx", "type": "mixer", "color": "#fbbf24", "w": "full", "h": 3 }
   Las filas aparecen/desaparecen solas según qué apps tengan audio activo. */
function buildMixer(w) {
  const el = document.createElement("div");
  el.className = "mx-widget";
  el.dataset.id = w.id;
  el.style.setProperty("--led", w.color || "#fbbf24");
  el.innerHTML = `
    <div class="mx-rows">
      <div class="mx-empty">Sin audio activo</div>
    </div>`;
  if (state.mixer) syncMixer(state.mixer);
  return el;
}

function mixerRun(action, params) {
  if (state.ws?.readyState !== WebSocket.OPEN) return;
  state.ws.send(JSON.stringify({ type: "run", action, params }));
}

function buildMixerRow(app) {
  const row = document.createElement("div");
  row.className = "mx-row";
  row.dataset.app = app.app;
  row.innerHTML = `
    <button class="mx-mute" title="Silenciar"></button>
    <div class="mx-info">
      <div class="mx-top">
        <span class="mx-name"></span>
        <span class="mx-val"></span>
      </div>
      <input type="range" class="mx-slider" min="0" max="100" step="1">
    </div>`;
  row.querySelector(".mx-name").textContent = app.name;

  row.querySelector(".mx-mute").onclick = () =>
    mixerRun("mixer_mute", { app: app.app });

  const input = row.querySelector(".mx-slider");
  const val = row.querySelector(".mx-val");
  const paint = () => {
    input.style.setProperty("--fill", `${input.value}%`);
    val.textContent = input.value + "%";
  };
  let last = 0;
  input.addEventListener("input", () => {
    paint();
    const now = Date.now();
    if (now - last > 120) {
      last = now;
      mixerRun("mixer_set", { app: app.app, level: Number(input.value) });
    }
  });
  input.addEventListener("change", () =>
    mixerRun("mixer_set", { app: app.app, level: Number(input.value) }));
  row._paint = paint;
  return row;
}

function updateMixerRow(row, app) {
  const input = row.querySelector(".mx-slider");
  if (document.activeElement !== input) {
    input.value = app.volume;
    row._paint();
  }
  if (row.dataset.muted !== String(app.muted)) {
    row.dataset.muted = String(app.muted);
    const btn = row.querySelector(".mx-mute");
    btn.innerHTML = "";
    renderIcon(btn, app.muted ? "lucide:volume-x" : "lucide:volume-2",
               app.muted ? "#f87171" : "#c9d1dd");
    row.classList.toggle("muted", app.muted);
  }
}

function syncMixer(list) {
  state.mixer = list;
  const el = document.querySelector(".mx-widget");
  if (!el) return;
  const box = el.querySelector(".mx-rows");
  const seen = new Set();
  for (const app of list) {
    seen.add(app.app);
    let row = box.querySelector(`.mx-row[data-app="${CSS.escape(app.app)}"]`);
    if (!row) { row = buildMixerRow(app); box.appendChild(row); }
    updateMixerRow(row, app);
  }
  for (const row of [...box.querySelectorAll(".mx-row")]) {
    if (!seen.has(row.dataset.app)) row.remove();
  }
  el.querySelector(".mx-empty").style.display = list.length ? "none" : "";
  el.classList.toggle("scrollable", box.scrollHeight > box.clientHeight + 4);
}

/* Actualiza sliders enlazados cuando llega estado del servidor */
function syncSliders(data) {
  for (const el of document.querySelectorAll(".slider-widget[data-bind]")) {
    const key = el.dataset.bind;
    if (!(key in data)) continue;
    const input = el.querySelector("input");
    if (document.activeElement === input) continue; // no pelear con el dedo del usuario
    input.value = data[key];
    input.dispatchEvent(new Event("__paint"));
    const pct = ((input.value - input.min) / (input.max - input.min)) * 100;
    input.style.setProperty("--fill", `${pct}%`);
    const val = el.querySelector(".slider-value");
    if (val) val.textContent = input.value + "%";
  }
}

/* Tipos de icono soportados en deck.json:
   - Emoji:           "icon": "🎮"
   - Imagen propia:   "icon": "img:custom/obs.png"   (en frontend/icons/)
   - Imagen por URL:  "icon": "img:https://ejemplo.com/logo.png"
   - Paquetes Iconify (200k+ iconos, se colorean con el color del botón):
       "icon": "mdi:microphone-off"    "icon": "lucide:volume-2"
       Buscador de nombres: https://icon-sets.iconify.design            */
function renderIcon(container, icon, color) {
  if (!icon) { container.textContent = "●"; return; }

  if (icon.startsWith("img:")) {
    const src = icon.slice(4);
    const img = document.createElement("img");
    img.src = /^https?:\/\//.test(src) ? src : `icons/${src}`;
    img.alt = "";
    img.onerror = () => { container.textContent = "🖼️"; };
    container.appendChild(img);
    return;
  }

  // patrón "paquete:nombre" de Iconify (mdi:, lucide:, tabler:, ph:, ...)
  if (/^[a-z0-9-]+:[a-z0-9-]+$/.test(icon)) {
    const [pack, name] = icon.split(":");
    const c = encodeURIComponent(color || "#e8ecf2");
    const img = document.createElement("img");
    // vía el servidor: cachea el icono en disco y funciona sin internet
    img.src = `/iconify/${pack}/${name}.svg?color=${c}`;
    img.alt = "";
    img.onerror = () => { container.textContent = "●"; };
    container.appendChild(img);
    return;
  }

  container.textContent = icon; // emoji o texto
}

/* ------------------------------------------------ acciones */
function press(btn, el, long = false) {
  el.classList.add("pressed");
  setTimeout(() => el.classList.remove("pressed"), 120);
  // "page" se resuelve en el cliente: carpetas / navegación entre páginas
  const act = long ? btn.longAction : btn.action;
  if (act === "page") {
    openPageAction((long ? btn.longParams : btn.params)?.page);
    return;
  }
  if (state.ws?.readyState !== WebSocket.OPEN) {
    toast(T("toast.noConn"), true);
    return;
  }
  state.ws.send(JSON.stringify({ type: "press", buttonId: btn.id, long }));
}

/* Carpetas: un botón con "action": "page" abre otra página; "back" vuelve. */
function openPageAction(target) {
  const pages = state.config.pages;
  if (target === "back") {
    const prev = state.pageHistory.pop();
    if (prev && pages.some(p => p.id === prev)) goToPage(prev, -1, true);
    return;
  }
  if (!pages.some(p => p.id === target)) {
    toast(T("toast.pageMissing", { page: target }), true);
    return;
  }
  state.pageHistory.push(state.currentPage);
  if (state.pageHistory.length > 20) state.pageHistory.shift();
  goToPage(target, 1, true);
}

function handleResult(msg) {
  const el = document.querySelector(`.key[data-id="${msg.buttonId}"]`);
  if (el) {
    const cls = msg.ok ? "flash-ok" : "flash-err";
    el.classList.add(cls);
    setTimeout(() => el.classList.remove(cls), 500);
  }
  if (!msg.ok) toast(msg.message || T("toast.actionError"), true);
  // toasts en verde: pulsaciones de botón, o avisos informativos como
  // "Letra no encontrada" (mensajes sin estado adjunto). Los resultados
  // con estado (sliders, now playing) no hacen toast para no inundar.
  else if (msg.message && (msg.buttonId || !msg.state)) toast(msg.message, false);
}

function renderSystemState(data) {
  const parts = [];
  if (typeof data.volume === "number") {
    parts.push(data.muted ? "🔇 mute" : `🔊 ${data.volume}%`);
  }
  $("systemState").textContent = parts.join("  ·  ");
}

/* ============================================================
   EDITOR VISUAL — modo edición, hoja de propiedades y páginas.
   Todo se guarda vía save_config: el servidor escribe deck.json
   y difunde la config nueva a todos los clientes.
   ============================================================ */
let actionsList = [];
let actionsSchema = {};
function loadActionsList() {
  MiniDeckAuth.api("/api/actions/schema").then(r => r.json())
    .then(d => { if (d && typeof d === "object") actionsSchema = d; }).catch(() => {});
  return MiniDeckAuth.api("/api/actions").then(r => r.json())
    .then(a => { if (Array.isArray(a)) actionsList = a; }).catch(() => {});
}

// Plantilla de params para una acción: del esquema, o del ejemplo del docstring.
function paramsTemplate(action) {
  if (action === "page") return { page: "" };
  const info = actionsSchema[action];
  if (!info) return {};
  const out = {};
  for (const [k, rule] of Object.entries(info.schema || {})) {
    if (k.startsWith("$")) continue;
    if (!rule.required && !(info.schema.$oneOf || []).flat().includes(k)) continue;
    out[k] = rule.choices ? rule.choices[0]
      : { int: 0, float: 0, bool: false, list: [], dict: {} }[rule.type] ?? "";
  }
  if (!Object.keys(out).length && info.example) {
    try { return JSON.parse(info.example); } catch { /* ejemplo no-JSON */ }
  }
  return out;
}

function actionHint(action) {
  if (action === "page") return T("ed.pageAction");
  const info = actionsSchema[action];
  if (!info) return "";
  return [info.doc, info.example && `params: ${info.example}`].filter(Boolean).join("\n");
}

/* ---------------------------------------------- deshacer / importar / exportar */
function undoLast() {
  if (state.ws?.readyState !== WebSocket.OPEN) { toast(T("toast.noConn"), true); return; }
  state.ws.send(JSON.stringify({ type: "undo" }));
}

function exportDeck() {
  // "pluginSettings" guarda contraseñas y tokens (OBS, Home Assistant…):
  // nunca deben salir en un deck pensado para compartir.
  const { pluginSettings, ...shareable } = state.config;
  const data = JSON.stringify(shareable, null, 2);
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([data], { type: "application/json" }));
  const name = (state.config.name || "minideck").replace(/[^\w.-]+/g, "_");
  a.download = `${name}.deck.json`;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  toast(T("toast.exported"), false);
}

function importDeck() {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".json,application/json";
  input.onchange = async () => {
    const file = input.files?.[0];
    if (!file) return;
    let cfg;
    try {
      cfg = JSON.parse(await file.text());
      if (!cfg || !Array.isArray(cfg.pages) || !cfg.pages.length) throw new Error("pages");
    } catch (e) {
      toast(T("toast.importBad", { err: e.message.slice(0, 60) }), true);
      return;
    }
    if (!confirm(T("confirm.import", { name: cfg.name || file.name, n: cfg.pages.length }))) return;
    // conservar los ajustes (y secretos) de plugins que ya hay en este equipo
    if (state.config.pluginSettings && !cfg.pluginSettings) {
      cfg.pluginSettings = state.config.pluginSettings;
    }
    state.config = cfg;            // el servidor valida y guarda copia (deshacer)
    state.currentPage = cfg.pages[0].id;
    saveConfig();
  };
  input.click();
}

const PALETTE = ["#4ade80", "#60a5fa", "#f87171", "#fbbf24",
                 "#a78bfa", "#f472b6", "#34d399", "#8a93a3"];

function toggleEdit() {
  state.editMode = !state.editMode;
  $("editBtn").classList.toggle("active", state.editMode);
  closeSheet();
  render();
}

function currentPage() {
  return state.config.pages.find(p => p.id === state.currentPage);
}

function saveConfig() {
  if (state.ws?.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({ type: "save_config", data: state.config }));
    state.pendingSave = false;
  } else {
    // sin conexión (ej. el iPhone acaba de despertar): guardar al reconectar
    state.pendingSave = true;
    toast(T("toast.saveLater"), true);
  }
  render();
}

function newWidget() {
  return { id: "w_" + Math.random().toString(36).slice(2, 8),
           label: T("w.new"), icon: "lucide:square", color: "#60a5fa",
           action: "hotkey", params: { keys: "" } };
}

/* ------------------------------------------------ páginas */
function addPage() {
  const name = prompt(T("prompt.newPage"));
  if (!name) return;
  const id = "p_" + Math.random().toString(36).slice(2, 8);
  state.config.pages.push({ id, name, buttons: [] });
  state.currentPage = id;
  saveConfig();
}

function renamePage() {
  const page = currentPage();
  const name = prompt(T("prompt.renamePage"), page.name);
  if (!name) return;
  page.name = name;
  saveConfig();
}

function deletePage() {
  if (state.config.pages.length <= 1) {
    toast(T("page.onlyOne"), true);
    return;
  }
  const page = currentPage();
  if (!confirm(T("confirm.deletePage", { name: page.name, n: page.buttons.length }))) return;
  state.config.pages = state.config.pages.filter(p => p.id !== page.id);
  state.currentPage = state.config.pages[0].id;
  saveConfig();
}

/* ------------------------------------------------ hoja de edición */
function ensureSheet() {
  let sheet = $("editSheet");
  if (sheet) return sheet;

  sheet = document.createElement("div");
  sheet.id = "editSheet";
  sheet.className = "sheet";
  sheet.innerHTML = `
    <div class="sheet-head">
      <span data-i18n="ed.title"></span>
      <button class="sheet-close">✕</button>
    </div>
    <div class="sheet-body">
      <label class="f-row"><span data-i18n="ed.name"></span>
        <input class="f-label" type="text" autocomplete="off"></label>
      <label class="f-row"><span data-i18n="ed.icon"></span>
        <div class="f-icon-row">
          <span class="f-icon-prev"></span>
          <input class="f-icon" type="text" autocomplete="off"
                 placeholder="lucide:play · 🎮 · img:custom/x.png">
          <button type="button" class="f-icon-pick" data-i18n-title="ed.searchIcon">🔍</button>
        </div></label>
      <div class="f-row"><span data-i18n="ed.color"></span>
        <div class="swatches"></div>
        <input class="f-color" type="text" autocomplete="off" placeholder="#60a5fa">
      </div>
      <div class="f-grid3">
        <label class="f-row"><span data-i18n="ed.type"></span>
          <select class="f-type"></select></label>
        <label class="f-row"><span data-i18n="ed.width"></span>
          <select class="f-w">
            <option value="1">1</option><option value="2">2</option>
            <option value="3">3</option><option value="full" data-i18n="ed.row"></option>
          </select></label>
        <label class="f-row"><span data-i18n="ed.height"></span>
          <select class="f-h">
            <option value="1">1</option><option value="2">2</option>
            <option value="3">3</option><option value="4">4</option>
            <option value="5">5</option>
          </select></label>
      </div>
      <div class="only-action">
        <label class="f-row row-action"><span data-i18n="ed.action"></span>
          <select class="f-action"></select></label>
        <div class="f-hint"></div>
        <label class="f-row"><span data-i18n="ed.params"></span>
          <textarea class="f-params" rows="4" spellcheck="false"
                    autocorrect="off" autocapitalize="off"></textarea></label>
      </div>
      <div class="only-key">
        <label class="f-row"><span data-i18n="ed.long"></span>
          <select class="f-long"></select></label>
        <label class="f-row row-long-params"><span data-i18n="ed.longParams"></span>
          <textarea class="f-long-params" rows="3" spellcheck="false"
                    autocorrect="off" autocapitalize="off"></textarea></label>
        <label class="f-row"><span data-i18n="ed.when"></span>
          <textarea class="f-when" rows="3" spellcheck="false" autocorrect="off"
                    autocapitalize="off"></textarea></label>
      </div>
      <div class="only-slider f-grid3">
        <label class="f-row"><span data-i18n="ed.min"></span> <input class="f-min" type="number"></label>
        <label class="f-row"><span data-i18n="ed.max"></span> <input class="f-max" type="number"></label>
        <label class="f-row"><span data-i18n="ed.vparam"></span> <input class="f-vparam" type="text"></label>
        <label class="f-row"><span data-i18n="ed.bind"></span> <input class="f-bind" type="text"
               placeholder="volume"></label>
      </div>
      <div class="sheet-tools">
        <button class="t-test" data-i18n="ed.test"></button>
        <button class="t-dup" data-i18n="ed.dup"></button>
        <button class="t-del" data-i18n="ed.del"></button>
      </div>
      <button class="sheet-save" data-i18n="ed.save"></button>
    </div>`;
  window.MiniDeckI18n.apply(sheet);
  sheet.querySelector(".f-when").placeholder = T("ed.whenHint");
  document.body.appendChild(sheet);

  // paleta de colores
  const sw = sheet.querySelector(".swatches");
  for (const c of PALETTE) {
    const b = document.createElement("button");
    b.className = "swatch";
    b.style.background = c;
    b.onclick = () => { sheet.querySelector(".f-color").value = c; paintSwatches(sheet, c); refreshIconPreview(sheet); };
    sw.appendChild(b);
  }

  sheet.querySelector(".sheet-close").onclick = closeSheet;
  sheet.querySelector(".f-icon-pick").onclick = () => openIconPicker(sheet);
  sheet.querySelector(".f-icon").addEventListener("input", () => refreshIconPreview(sheet));
  sheet.querySelector(".f-color").addEventListener("input", () => refreshIconPreview(sheet));
  sheet.querySelector(".f-type").onchange = () => syncTypeFields(sheet);
  // al cambiar de acción: ayuda + plantilla de params (si no había nada escrito)
  sheet.querySelector(".f-action").onchange = () => {
    const act = sheet.querySelector(".f-action").value;
    sheet.querySelector(".f-hint").textContent = actionHint(act);
    const ta = sheet.querySelector(".f-params");
    let cur = {};
    try { cur = JSON.parse(ta.value || "{}"); } catch { /* se respeta lo escrito */ }
    if (!Object.keys(cur).length || ta.dataset.template === ta.value) {
      ta.value = JSON.stringify(paramsTemplate(act), null, 2);
      ta.dataset.template = ta.value;
    }
  };
  sheet.querySelector(".f-long").onchange = () => {
    const act = sheet.querySelector(".f-long").value;
    sheet.querySelector(".row-long-params").style.display = act ? "" : "none";
    const ta = sheet.querySelector(".f-long-params");
    if (act && (!ta.value.trim() || ta.value.trim() === "{}")) {
      ta.value = JSON.stringify(paramsTemplate(act), null, 2);
    }
  };
  sheet.querySelector(".sheet-save").onclick = () => applyEditor(sheet);
  sheet.querySelector(".t-del").onclick = () => {
    const i = Number(sheet.dataset.index);
    if (!confirm(T("confirm.deleteWidget"))) return;
    currentPage().buttons.splice(i, 1);
    closeSheet();
    saveConfig();
  };
  sheet.querySelector(".t-dup").onclick = () => {
    const i = Number(sheet.dataset.index);
    const copy = JSON.parse(JSON.stringify(currentPage().buttons[i]));
    copy.id = "w_" + Math.random().toString(36).slice(2, 8);
    currentPage().buttons.splice(i + 1, 0, copy);
    saveConfig();
    openEditor(i + 1);
  };
  sheet.querySelector(".t-test").onclick = () => {
    const w = readEditor(sheet);
    if (!w || !w.action) return;
    if (state.ws?.readyState === WebSocket.OPEN) {
      state.ws.send(JSON.stringify({ type: "run", action: w.action,
                                     params: w.params ?? {} }));
    }
  };
  return sheet;
}

function paintSwatches(sheet, color) {
  sheet.querySelectorAll(".swatch").forEach(s =>
    s.classList.toggle("sel",
      s.style.background && rgbEq(s.style.background, color)));
}
function rgbEq(a, b) {
  const c = document.createElement("i");
  c.style.color = a; const ca = c.style.color;
  c.style.color = b || ""; return ca === c.style.color;
}

function syncTypeFields(sheet) {
  const t = sheet.querySelector(".f-type").value;
  const def = WIDGETS[t];
  sheet.querySelector(".only-action").style.display =
    def?.noAction ? "none" : "";
  sheet.querySelector(".row-action").style.display =
    (def?.noAction || def?.keepParams) ? "none" : "";
  sheet.querySelector(".only-slider").style.display =
    (t === "slider" || def?.slider) ? "" : "none";
  // pulsación larga y estado: solo para botones normales
  sheet.querySelector(".only-key").style.display = t === "button" ? "" : "none";
}

function refreshIconPreview(sheet) {
  const prev = sheet.querySelector(".f-icon-prev");
  if (!prev) return;
  prev.innerHTML = "";
  const icon = sheet.querySelector(".f-icon").value.trim();
  const color = sheet.querySelector(".f-color").value.trim() || "#c9d1dd";
  if (icon) renderIcon(prev, icon, color);
}

/* ------------------------------------------------ buscador de iconos lucide */
let _lucideNames = null;
async function lucideNames() {
  if (_lucideNames) return _lucideNames;
  // Iconify y, si no responde, la lista de lucide-static en jsDelivr
  const sources = [
    async () => {
      const d = await (await fetch("https://api.iconify.design/collection?prefix=lucide")).json();
      const set = new Set(d.uncategorized || []);
      for (const arr of Object.values(d.categories || {})) arr.forEach(n => set.add(n));
      return [...set];
    },
    async () => Object.keys(await (await fetch(
      "https://cdn.jsdelivr.net/npm/lucide-static@latest/tags.json")).json()),
  ];
  for (const src of sources) {
    try {
      const names = await src();
      if (names.length) { _lucideNames = names.sort(); return _lucideNames; }
    } catch { /* siguiente fuente */ }
  }
  return [];
}

function openIconPicker(sheet) {
  let ov = document.querySelector(".icon-picker");
  if (!ov) {
    ov = document.createElement("div");
    ov.className = "icon-picker";
    ov.innerHTML = `
      <div class="ip-head">
        <input class="ip-search" type="text" autocomplete="off"
               placeholder="">
        <button class="ip-close" type="button">✕</button>
      </div>
      <div class="ip-grid"></div>`;
    document.body.appendChild(ov);
    ov.querySelector(".ip-close").onclick = () => ov.classList.remove("open");
    ov.querySelector(".ip-search").addEventListener("input", () => renderIconGrid(ov));
  }
  ov._sheet = sheet;
  ov.querySelector(".ip-search").placeholder = T("ip.search");
  ov.classList.add("open");
  ov.querySelector(".ip-search").value = "";
  renderIconGrid(ov);
  setTimeout(() => ov.querySelector(".ip-search").focus(), 50);
}

async function renderIconGrid(ov) {
  const grid = ov.querySelector(".ip-grid");
  const q = ov.querySelector(".ip-search").value.trim().toLowerCase();
  grid.innerHTML = `<div class="ip-empty">${T("ip.loading")}</div>`;
  const names = await lucideNames();
  if (!names.length) {
    grid.innerHTML = `<div class="ip-empty">${T("ip.offline")}</div>`;
    return;
  }
  const list = (q ? names.filter(n => n.includes(q)) : names).slice(0, 180);
  grid.innerHTML = "";
  for (const n of list) {
    const b = document.createElement("button");
    b.className = "ip-item";
    b.type = "button";
    b.title = n;
    b.innerHTML =
      `<img src="/iconify/lucide/${n}.svg?color=%23888" alt="" loading="lazy">` +
      `<span>${n}</span>`;
    b.onclick = () => {
      ov._sheet.querySelector(".f-icon").value = "lucide:" + n;
      refreshIconPreview(ov._sheet);
      ov.classList.remove("open");
    };
    grid.appendChild(b);
  }
  if (!list.length) grid.innerHTML = `<div class="ip-empty">${T("ip.none")}</div>`;
}

function openEditor(index) {
  const w = currentPage().buttons[index];
  if (!w) return;
  const sheet = ensureSheet();
  sheet.dataset.index = index;

  // tipos disponibles: botón + todos los widgets registrados (incl. plugins)
  const tsel = sheet.querySelector(".f-type");
  tsel.innerHTML = "";
  for (const [val, label] of [["button", T("ed.button")],
       ...Object.entries(WIDGETS).map(([t, d]) => [t, d.label || t])]) {
    const o = document.createElement("option");
    o.value = val; o.textContent = label;
    tsel.appendChild(o);
  }

  sheet.querySelector(".f-label").value = w.label ?? "";
  sheet.querySelector(".f-icon").value = w.icon ?? "";
  sheet.querySelector(".f-color").value = w.color ?? "#60a5fa";
  paintSwatches(sheet, w.color ?? "#60a5fa");
  sheet.querySelector(".f-type").value = w.type ?? "button";
  sheet.querySelector(".f-w").value = String(w.w ?? 1);
  sheet.querySelector(".f-h").value = String(w.h ?? 1);

  // acciones del servidor + "page" (carpetas, se resuelve en el cliente)
  const allActions = ["page", ...actionsList];
  const fillActions = (sel, current, withNone) => {
    sel.innerHTML = "";
    if (withNone) {
      const o = document.createElement("option");
      o.value = ""; o.textContent = T("ed.longNone");
      sel.appendChild(o);
    }
    for (const a of allActions) {
      const o = document.createElement("option");
      o.value = o.textContent = a;
      sel.appendChild(o);
    }
    if (current && !allActions.includes(current)) {
      const o = document.createElement("option");
      o.value = o.textContent = current;
      sel.appendChild(o);
    }
    sel.value = current ?? "";
  };
  fillActions(sheet.querySelector(".f-action"), w.action, false);
  fillActions(sheet.querySelector(".f-long"), w.longAction, true);
  sheet.querySelector(".f-hint").textContent = actionHint(w.action);
  const pta = sheet.querySelector(".f-params");
  pta.value = JSON.stringify(w.params ?? {}, null, 2);
  pta.dataset.template = "";
  sheet.querySelector(".f-long-params").value =
    w.longAction ? JSON.stringify(w.longParams ?? {}, null, 2) : "";
  sheet.querySelector(".row-long-params").style.display = w.longAction ? "" : "none";
  sheet.querySelector(".f-when").value = w.when ? JSON.stringify(w.when, null, 2) : "";
  sheet.querySelector(".f-min").value = w.min ?? 0;
  sheet.querySelector(".f-max").value = w.max ?? 100;
  sheet.querySelector(".f-vparam").value = w.valueParam ?? "level";
  sheet.querySelector(".f-bind").value = w.bind ?? "";

  syncTypeFields(sheet);
  refreshIconPreview(sheet);
  sheet.classList.add("open");
}

/* Lee un <textarea> JSON. iOS convierte comillas rectas en tipográficas
   ("" '' y guiones largos): se normalizan para que el JSON sea válido.
   Vacío → `empty`. Error → undefined (y marca el campo). */
function readJsonField(ta, field, empty) {
  ta.classList.remove("err");
  const raw = (ta.value || "").trim()
    .replace(/[\u201C\u201D\u201E\u2033]/g, '"')
    .replace(/[\u2018\u2019\u2032]/g, "'")
    .replace(/\u2014/g, "-");
  if (!raw) return empty;
  try {
    const v = JSON.parse(raw);
    ta.value = JSON.stringify(v, null, 2);   // dejar la versión limpia
    return v;
  } catch (e) {
    ta.classList.add("err");
    toast(T("ed.badJson", { field, err: e.message.slice(0, 60) }), true);
    return undefined;
  }
}

// Campos que gestiona el formulario; el resto (de plugins, o escritos a
// mano en deck.json) se conserva al guardar.
const EDITOR_FIELDS = ["label", "icon", "color", "type", "w", "h", "action", "params",
                       "min", "max", "valueParam", "bind", "longAction", "longParams", "when"];

function readEditor(sheet) {
  const params = readJsonField(sheet.querySelector(".f-params"), T("ed.params"), {});
  if (params === undefined) return null;
  const longAct = sheet.querySelector(".f-long").value;
  const longParams = longAct
    ? readJsonField(sheet.querySelector(".f-long-params"), T("ed.longParams"), {})
    : null;
  if (longParams === undefined) return null;
  const when = readJsonField(sheet.querySelector(".f-when"), T("ed.when"), null);
  if (when === undefined) return null;

  const type = sheet.querySelector(".f-type").value;
  const wsel = sheet.querySelector(".f-w").value;
  const prev = currentPage().buttons[Number(sheet.dataset.index)] || {};
  const w = Object.fromEntries(Object.entries(prev).filter(([k]) => !EDITOR_FIELDS.includes(k)));
  Object.assign(w, {
    id: prev.id ?? "w_" + Math.random().toString(36).slice(2, 8),
    label: sheet.querySelector(".f-label").value.trim(),
    icon: sheet.querySelector(".f-icon").value.trim(),
    color: sheet.querySelector(".f-color").value.trim() || "#8a93a3",
  });
  if (type === "button") {
    if (longAct) { w.longAction = longAct; w.longParams = longParams; }
    if (when && when.key) w.when = when;
  }
  if (type !== "button") w.type = type;
  if (wsel !== "1") w.w = wsel === "full" ? "full" : Number(wsel);
  const h = Number(sheet.querySelector(".f-h").value);
  if (h > 1) w.h = h;
  const def = WIDGETS[type];
  if (!def?.noAction && !def?.keepParams) {
    w.action = sheet.querySelector(".f-action").value;
    w.params = params;
  } else if (def?.keepParams) {
    w.params = params;
  }
  if (type === "slider" || def?.slider) {
    w.min = Number(sheet.querySelector(".f-min").value) || 0;
    w.max = Number(sheet.querySelector(".f-max").value) || 100;
    w.valueParam = sheet.querySelector(".f-vparam").value.trim() || "level";
    const bind = sheet.querySelector(".f-bind").value.trim();
    if (bind) w.bind = bind;
  }
  return w;
}

function applyEditor(sheet) {
  const w = readEditor(sheet);
  if (!w) return;
  currentPage().buttons[Number(sheet.dataset.index)] = w;
  closeSheet();
  saveConfig();  // el toast "Guardado en el PC ✓" llega como confirmación real
}

function closeSheet() {
  $("editSheet")?.classList.remove("open");
}

/* ------------------------------------------------ drag & drop (edición)
   Mantener presionado ~260ms inicia el arrastre; mover el dedo antes de
   eso se interpreta como scroll y se cancela. Un "fantasma" sigue al dedo
   y el widget real se reubica en vivo; al soltar se guarda el orden. */
const drag = { el: null, ghost: null, timer: null, active: false,
               pointerId: null, startX: 0, startY: 0,
               offX: 0, offY: 0, justDragged: false,
               lastTarget: null, lastIX: -999, lastIY: -999 };

// bloquear el scroll SOLO mientras hay un arrastre activo
document.addEventListener("touchmove", (e) => {
  if (drag.active) e.preventDefault();
}, { passive: false });

function attachDrag(el) {
  el.addEventListener("pointerdown", (e) => {
    if (!state.editMode || drag.active) return;
    drag.el = el;
    drag.pointerId = e.pointerId;
    drag.startX = e.clientX;
    drag.startY = e.clientY;
    clearTimeout(drag.timer);
    drag.timer = setTimeout(beginDrag, 260);
  });
  el.addEventListener("pointermove", onDragMove);
  el.addEventListener("pointerup", endDrag);
  el.addEventListener("pointercancel", endDrag);
}

function beginDrag() {
  const el = drag.el;
  if (!el) return;
  drag.active = true;
  drag.lastTarget = null;
  drag.lastIX = -999;
  drag.lastIY = -999;
  $("grid").classList.add("dragging");
  try { el.setPointerCapture(drag.pointerId); } catch {}

  const r = el.getBoundingClientRect();
  drag.offX = drag.startX - r.left;
  drag.offY = drag.startY - r.top;

  const g = el.cloneNode(true);
  g.className = el.className + " drag-ghost";
  g.style.width = r.width + "px";
  g.style.height = r.height + "px";
  g.style.left = r.left + "px";
  g.style.top = r.top + "px";
  document.body.appendChild(g);
  drag.ghost = g;
  el.classList.add("drag-src");
}

function onDragMove(e) {
  if (!drag.el) return;

  if (!drag.active) {
    // si el dedo se mueve antes del long-press, era un scroll: cancelar
    const dist = Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY);
    if (dist > 12) { clearTimeout(drag.timer); drag.el = null; }
    return;
  }

  drag.ghost.style.left = (e.clientX - drag.offX) + "px";
  drag.ghost.style.top = (e.clientY - drag.offY) + "px";

  // enfriamiento: tras un reacomodo, exigir movimiento antes del siguiente
  if (Math.hypot(e.clientX - drag.lastIX, e.clientY - drag.lastIY) < 16) return;

  // objetivo = la celda cuyo CENTRO queda más cerca del dedo (excluyendo la
  // arrastrada). Esto funciona aunque el dedo esté sobre el propio widget,
  // que era lo que rompía a los 1x1 con la detección por elementFromPoint.
  const grid = $("grid");
  const tiles = [...grid.querySelectorAll("[data-idx]")].filter(t => t !== drag.el);
  let target = null;
  let best = Infinity;
  for (const t of tiles) {
    const r = t.getBoundingClientRect();
    const d = Math.hypot(e.clientX - (r.left + r.width / 2),
                         e.clientY - (r.top + r.height / 2));
    if (d < best) { best = d; target = t; }
  }
  if (!target || best > 160) return;

  // anti-parpadeo: no reacomodar dos veces seguidas contra la misma celda
  if (target === drag.lastTarget) return;

  if ([...grid.querySelectorAll("[data-idx]")].indexOf(drag.el) <
      [...grid.querySelectorAll("[data-idx]")].indexOf(target)) {
    grid.insertBefore(drag.el, target.nextSibling);
  } else {
    grid.insertBefore(drag.el, target);
  }
  drag.lastTarget = target;
  drag.lastIX = e.clientX;
  drag.lastIY = e.clientY;
}

function endDrag() {
  clearTimeout(drag.timer);
  if (!drag.active) { drag.el = null; return; }

  drag.active = false;
  drag.lastTarget = null;
  $("grid").classList.remove("dragging");
  drag.ghost?.remove();
  drag.ghost = null;
  drag.el?.classList.remove("drag-src");

  // el orden nuevo es el orden actual del DOM
  const page = currentPage();
  const order = [...$("grid").querySelectorAll("[data-idx]")]
    .map(n => page.buttons[Number(n.dataset.idx)])
    .filter(Boolean);
  drag.el = null;
  drag.justDragged = true;
  setTimeout(() => { drag.justDragged = false; }, 350);

  page.buttons = order;
  saveConfig();
}

/* ------------------------------------------------ toast */
let toastTimer = null;
function toast(text, isError) {
  const t = $("toast");
  t.textContent = text;
  t.classList.toggle("error", !!isError);
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 1800);
}

/* ------------------------------------------------ widgets de serie */
registerWidget("slider",     { label: "Slider", build: buildSlider, slider: true });
registerWidget("nowplaying", { label: "Now Playing", build: buildNowPlaying,
                               stateKey: "nowplaying", sync: syncNowPlaying,
                               noAction: true });
registerWidget("discord",    { label: "Discord", build: buildDiscord,
                               stateKey: "discord", sync: syncDiscord,
                               keepParams: true });
registerWidget("mixer",      { label: "Mixer", build: buildMixer,
                               stateKey: "mixer", sync: syncMixer,
                               noAction: true });

/* ------------------------------------------------ tema */
const THEMES = ["", "lcd"];   // "" = oscuro por defecto; "lcd" = pantalla e-ink
const currentTheme = () => document.documentElement.getAttribute("data-theme") || "";
function applyTheme(t) {
  if (t) document.documentElement.setAttribute("data-theme", t);
  else document.documentElement.removeAttribute("data-theme");
  try { localStorage.setItem("minideck-theme", t); } catch (e) {}
  $("themeBtn").classList.toggle("active", t === "lcd");
  toast(T("toast.theme", { name: t === "lcd" ? "LCD" : (MiniDeckI18n.lang === "es" ? "Oscuro" : "Dark") }), false);
}
function toggleTheme() {
  const i = THEMES.indexOf(currentTheme());
  applyTheme(THEMES[(i + 1) % THEMES.length]);
}

/* ------------------------------------------------ pantalla completa / inmersivo */
const isImmersive = () => document.body.classList.contains("immersive");
function setImmersive(on) {
  document.body.classList.toggle("immersive", on);
  $("fsBtn").classList.toggle("active", on);
  const el = document.documentElement;
  const nativeFs = el.requestFullscreen || el.webkitRequestFullscreen;
  try {
    if (on && nativeFs && !document.fullscreenElement) nativeFs.call(el);
    else if (!on && document.fullscreenElement)
      (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
  } catch (e) {}
  if (on) toast(T(matchMedia("(pointer: fine)").matches ? "fs.hintDesktop" : "fs.hint"), false);
}
function toggleFullscreen() { setImmersive(!isImmersive()); }

// Si el navegador sale de pantalla completa por su cuenta (Esc, F11, gesto),
// salir también del modo inmersivo: si no, la barra superior quedaría oculta
// y no habría forma de volver a editar.
for (const ev of ["fullscreenchange", "webkitfullscreenchange"]) {
  document.addEventListener(ev, () => {
    const fs = document.fullscreenElement || document.webkitFullscreenElement;
    if (!fs && isImmersive()) setImmersive(false);
  });
}

// Esc: cierra lo que esté abierto, de arriba abajo.
document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  const picker = document.querySelector(".icon-picker.open");
  if (picker) { picker.classList.remove("open"); return; }
  if ($("editSheet")?.classList.contains("open")) { closeSheet(); return; }
  if (isImmersive()) { setImmersive(false); return; }
  if (state.editMode) toggleEdit();
});

/* ------------------------------------------------ cambiar de página */
function animateGrid(dir) {
  const grid = $("grid");
  grid.classList.remove("slide-next", "slide-prev");
  void grid.offsetWidth;                       // reinicia la animación
  grid.classList.add(dir > 0 ? "slide-next" : "slide-prev");
}
function goToPage(id, dir) {
  state.currentPage = id;
  render();
  animateGrid(dir);
}
function gotoPageDelta(d) {
  const pages = state.config?.pages || [];
  if (pages.length < 2) return;
  let i = pages.findIndex(p => p.id === state.currentPage);
  if (i < 0) i = 0;
  i = (i + d + pages.length) % pages.length;
  goToPage(pages[i].id, d);
  flashPageName(pages[i].name);
}
function flashPageName(name) {
  let el = document.querySelector(".page-flash");
  if (!el) { el = document.createElement("div"); el.className = "page-flash";
             document.body.appendChild(el); }
  el.textContent = name;
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 650);
}

/* Gestos táctiles:
   - Un dedo en horizontal  → página siguiente/anterior.
   - Un dedo hacia abajo (en pantalla completa) → salir.
   No interfiere con toques de botón (umbral) ni con el scroll vertical
   (solo actúa si el movimiento es claramente horizontal). */
let _sw = null;            // gesto en curso
let _swiped = false;       // hubo swipe: anular el "click" que le sigue
const _avg = (t, k) => t.length === 2 ? (t[0][k] + t[1][k]) / 2 : t[0][k];

document.addEventListener("touchstart", (e) => {
  if (state.editMode) { _sw = null; return; }   // no molestar al reordenar
  _sw = { x0: _avg(e.touches, "clientX"), y0: _avg(e.touches, "clientY"),
          dx: 0, dy: 0, n: e.touches.length };
}, { passive: true });

document.addEventListener("touchmove", (e) => {
  if (!_sw) return;
  _sw.dx = _avg(e.touches, "clientX") - _sw.x0;
  _sw.dy = _avg(e.touches, "clientY") - _sw.y0;
}, { passive: true });

document.addEventListener("touchend", () => {
  if (!_sw) return;
  const { dx, dy } = _sw;
  _sw = null;
  // horizontal → cambiar de página
  if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.3) {
    _swiped = true;
    setTimeout(() => { _swiped = false; }, 350);
    gotoPageDelta(dx < 0 ? 1 : -1);   // arrastrar a la izquierda = siguiente
    return;
  }
  // hacia abajo en pantalla completa → salir
  if (isImmersive() && dy > 90 && dy > Math.abs(dx) * 1.3) {
    _swiped = true;
    setTimeout(() => { _swiped = false; }, 350);
    setImmersive(false);
  }
}, { passive: true });

// si el toque fue un swipe, cancelar el click que dispararía el botón
document.addEventListener("click", (e) => {
  if (_swiped) { e.stopPropagation(); e.preventDefault(); _swiped = false; }
}, true);

/* ------------------------------------------------ perfil por app
   Cambia de página automáticamente según la app activa del Mac.
   El mapa app→página está en deck.json ("profiles"). */
let _lastApp = null;
function handleActiveApp(app) {
  if (!app || app === _lastApp) return;
  _lastApp = app;                       // solo actúa cuando CAMBIA la app
  if (!state.autoProfile) return;
  const pageId = state.config?.profiles?.[app];
  if (!pageId) return;
  const pages = state.config?.pages || [];
  const cur = pages.findIndex(p => p.id === state.currentPage);
  const tgt = pages.findIndex(p => p.id === pageId);
  if (tgt < 0 || tgt === cur) return;
  goToPage(pageId, tgt > cur ? 1 : -1);
}
function toggleAutoProfile() {
  state.autoProfile = !state.autoProfile;
  try { localStorage.setItem("minideck-autoprofile", state.autoProfile ? "1" : "0"); } catch (e) {}
  $("profileBtn").classList.toggle("active", state.autoProfile);
  toast(state.autoProfile ? "Perfil por app: activado" : "Perfil por app: desactivado", false);
  _lastApp = null;                      // fuerza reevaluar al reactivar
}

/* ------------------------------------------------ init */
try { state.autoProfile = localStorage.getItem("minideck-autoprofile") !== "0"; }
catch (e) { state.autoProfile = true; }
$("profileBtn").onclick = toggleAutoProfile;
$("profileBtn").classList.toggle("active", state.autoProfile);
$("editBtn").onclick = toggleEdit;
$("themeBtn").onclick = toggleTheme;
// idioma: alterna entre los disponibles y repinta la interfaz
function paintLangBtn() { $("langBtn").textContent = MiniDeckI18n.lang.toUpperCase(); }
paintLangBtn();
$("langBtn").onclick = () => {
  const langs = MiniDeckI18n.languages;
  MiniDeckI18n.setLang(langs[(langs.indexOf(MiniDeckI18n.lang) + 1) % langs.length]);
  paintLangBtn();
  $("editSheet")?.remove();           // se reconstruye en el idioma nuevo
  if (state.config) render();
  toast(T("toast.lang"), false);
};
$("fsBtn").onclick = toggleFullscreen;
$("fsExit").onclick = toggleFullscreen;
$("themeBtn").classList.toggle("active", currentTheme() === "lcd");
MiniDeckAuth.ensure().then((token) => {
  if (!token) { state.unauthorized = true; MiniDeckAuth.showPairing(); return; }
  loadActionsList();
  loadPlugins().then(connect);
});

// Aviso "Añadir a pantalla de inicio": solo en iPhone/iPad abierto en Safari
// (no cuando ya corre como app standalone). Se puede cerrar y no vuelve.
(function () {
  const isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
  const standalone = window.navigator.standalone === true ||
    window.matchMedia("(display-mode: standalone)").matches;
  let dismissed = false;
  try { dismissed = localStorage.getItem("minideck-a2hs") === "1"; } catch (e) {}
  const b = $("a2hs");
  const closeBtn = () => {
    if (!b) return;
    $("a2hsClose").onclick = () => {
      b.classList.remove("show");
      try { localStorage.setItem("minideck-a2hs", "1"); } catch (e) {}
    };
  };
  // iOS (Safari): guía "Añadir a pantalla de inicio"
  if (isIOS && !standalone && !dismissed && b) {
    setTimeout(() => b.classList.add("show"), 3500);
    closeBtn();
  }
  // Android (Chrome/Brave, HTTPS de confianza): botón "Instalar" nativo
  window.addEventListener("beforeinstallprompt", (e) => {
    e.preventDefault();
    if (standalone || !b) return;
    const btn = $("a2hsInstall");
    $("a2hsText").textContent = MiniDeckI18n.lang === "es"
      ? "Instala MiniDeck como app (pantalla completa)."
      : "Install MiniDeck as an app (full screen).";
    btn.style.display = "";
    btn.onclick = async () => {
      btn.disabled = true;
      e.prompt();
      try { await e.userChoice; } catch (_) {}
      b.classList.remove("show");
    };
    b.classList.add("show");
    closeBtn();
  });
})();

// Splash de inicio: se muestra 3 s (logo + MiniDeck + by Samons) y se va.
setTimeout(() => {
  const s = $("splash");
  if (!s) return;
  s.classList.add("hide");
  setTimeout(() => s.remove(), 600);
}, 3000);

// La barra de progreso avanza localmente cada 500ms usando el reloj
// interpolado, sin esperar al siguiente update del servidor.
setInterval(() => {
  const np = state.np;
  const el = document.querySelector(".np-widget");
  if (!el || !np || np.status !== "playing") return;
  const seek = el.querySelector(".np-seek");
  if (seek.disabled || document.activeElement === seek) return;
  const max = Number(seek.max);
  if (!max) return;
  const t = Math.min(currentSongTime(), max);
  seek.value = t;
  seek.style.setProperty("--fill", `${(t / max) * 100}%`);
  el.querySelector(".np-pos").textContent = fmtTime(t);
}, 500);

// Service worker: solo funciona bajo HTTPS o localhost.
// En red local por HTTP simplemente se omite sin romper nada.
if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost" || location.hostname === "127.0.0.1")) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}