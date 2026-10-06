/* SPDX-License-Identifier: AGPL-3.0-or-later
   SPDX-FileCopyrightText: 2026 Samons */
/* Widget del plugin sysmon: panel compacto con CPU, RAM y Disco.
   Muestra icono + porcentaje (sin barra). Se registra como tipo "sysmon". */
(() => {
  const { registerWidget, renderIcon } = window.MiniDeck;

  const TILES = [
    { key: "cpu",  label: "CPU",   icon: "lucide:cpu" },
    { key: "ram",  label: "RAM",   icon: "lucide:memory-stick" },
    { key: "disk", label: "Disco", icon: "lucide:hard-drive" },
  ];

  function build(w) {
    const el = document.createElement("div");
    el.className = "sm-panel";
    el.dataset.id = w.id;
    el.style.setProperty("--led", w.color || "#34d399");
    el.innerHTML = `<div class="sm-grid">` + TILES.map(t => `
      <div class="sm-tile" data-k="${t.key}">
        <span class="sm-ic"></span>
        <div class="sm-pct"><span class="sm-num">–</span><span class="sm-unit">%</span></div>
        <span class="sm-label">${t.label}</span>
      </div>`).join("") + `</div>`;
    TILES.forEach(t =>
      renderIcon(el.querySelector(`.sm-tile[data-k="${t.key}"] .sm-ic`), t.icon, "#8a857a"));
    if (window.MiniDeck.state.sysmon) sync(window.MiniDeck.state.sysmon);
    return el;
  }

  function sync(d) {
    window.MiniDeck.state.sysmon = d;
    const el = document.querySelector(".sm-panel");
    if (!el) return;
    for (const t of TILES) {
      const v = d[t.key];
      if (v == null) continue;
      const tile = el.querySelector(`.sm-tile[data-k="${t.key}"]`);
      if (!tile) continue;
      tile.querySelector(".sm-num").textContent = v;
      tile.classList.toggle("hot", v >= 85);
    }
  }

  registerWidget("sysmon", {
    label: "Panel del sistema",
    build,
    sync,
    stateKey: "sysmon",
    noAction: true,
  });
})();
