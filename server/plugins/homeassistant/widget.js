/* SPDX-License-Identifier: AGPL-3.0-or-later
   SPDX-FileCopyrightText: 2026 Samons */
/* Widget del plugin «homeassistant»: lista las entidades configuradas con
   su estado; tocar una la conmuta (ha_toggle). Se registra como tipo "ha". */
(() => {
  const { registerWidget, run } = window.MiniDeck;
  const ON = new Set(["on", "open", "playing", "home", "unlocked", "heat", "cool"]);
  let last = null;

  function paintPanel(el, d) {
    const connected = !!(d && d.connected);
    el.classList.toggle("ha-off", !connected);
    const ents = connected && d.entities ? d.entities : {};
    const ids = Object.keys(ents);
    const list = el.querySelector(".ha-list");
    const sig = JSON.stringify(ids);
    if (list.dataset.sig !== sig) {
      list.dataset.sig = sig;
      list.replaceChildren(...ids.map(id => {
        const b = document.createElement("button");
        b.type = "button";
        b.className = "ha-item";
        b.dataset.entity = id;
        const name = document.createElement("span");
        name.className = "ha-name";
        const st = document.createElement("span");
        st.className = "ha-state";
        b.append(name, st);
        b.onclick = () => run("ha_toggle", { entity_id: id });
        return b;
      }));
    }
    for (const b of list.children) {
      const e = ents[b.dataset.entity] || {};
      b.querySelector(".ha-name").textContent = e.name || b.dataset.entity;
      b.querySelector(".ha-state").textContent = e.state == null ? "—" : String(e.state);
      b.classList.toggle("ha-on", ON.has(String(e.state)));
    }
    el.querySelector(".ha-empty").textContent = connected
      ? (ids.length ? "" : "Sin entidades")
      : "Home Assistant desconectado";
  }

  function paint() {
    for (const el of document.querySelectorAll(".ha-panel")) paintPanel(el, last);
  }

  registerWidget("ha", {
    label: "Home Assistant",
    stateKey: "ha",
    noAction: true,
    build(w) {
      const el = document.createElement("div");
      el.className = "ha-panel ha-off";
      el.dataset.id = w.id;
      el.style.setProperty("--led", w.color || "#fbbf24");
      el.innerHTML = '<div class="ha-empty"></div><div class="ha-list"></div>';
      if (last == null && window.MiniDeck.state.ha) last = window.MiniDeck.state.ha;
      paintPanel(el, last);
      return el;
    },
    sync(data) {
      last = data;
      paint();
    },
  });
})();
