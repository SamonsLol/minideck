/* SPDX-License-Identifier: AGPL-3.0-or-later
   SPDX-FileCopyrightText: 2026 Samons */
/* Widget del plugin «obs»: conexión, escena actual, botones REC / LIVE y
   una fila con las escenas de OBS. Se registra como tipo "obs". */
(() => {
  const { registerWidget, run } = window.MiniDeck;
  let last = null;

  function paintPanel(el, d) {
    const connected = !!(d && d.connected);
    el.classList.toggle("obs-off", !connected);
    el.querySelector(".obs-scene").textContent =
      connected ? (d.scene || "—") : "OBS desconectado";
    el.querySelector(".obs-rec").classList.toggle("obs-on", connected && !!d.recording);
    el.querySelector(".obs-rec").classList.toggle("obs-paused", connected && !!d.paused);
    el.querySelector(".obs-live").classList.toggle("obs-on", connected && !!d.streaming);

    const scenes = connected && Array.isArray(d.scenes) ? d.scenes : [];
    const row = el.querySelector(".obs-scenes");
    const sig = JSON.stringify(scenes);
    if (row.dataset.sig !== sig) {
      row.dataset.sig = sig;
      row.replaceChildren(...scenes.map(name => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "obs-scene-btn";
        b.textContent = name;
        b.dataset.scene = name;
        b.onclick = () => run("obs_scene", { scene: name });
        return b;
      }));
    }
    for (const b of row.children) {
      b.classList.toggle("obs-on", connected && b.dataset.scene === d.scene);
    }
  }

  function paint() {
    for (const el of document.querySelectorAll(".obs-panel")) paintPanel(el, last);
  }

  function build(w) {
    const el = document.createElement("div");
    el.className = "obs-panel obs-off";
    el.dataset.id = w.id;
    el.style.setProperty("--led", w.color || "#ef4444");
    el.innerHTML = `
      <div class="obs-head">
        <span class="obs-dot"></span>
        <span class="obs-scene"></span>
        <button type="button" class="obs-btn obs-rec">REC</button>
        <button type="button" class="obs-btn obs-live">LIVE</button>
      </div>
      <div class="obs-scenes"></div>`;
    el.querySelector(".obs-rec").onclick = () => run("obs_record_toggle", {});
    el.querySelector(".obs-live").onclick = () => run("obs_stream_toggle", {});
    if (last == null && window.MiniDeck.state.obs) last = window.MiniDeck.state.obs;
    paintPanel(el, last);
    return el;
  }

  registerWidget("obs", {
    label: "OBS Studio",
    stateKey: "obs",
    noAction: true,
    build,
    sync(data) {
      last = data;
      paint();
    },
  });
})();
