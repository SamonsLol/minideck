/* SPDX-License-Identifier: AGPL-3.0-or-later
   SPDX-FileCopyrightText: 2026 Samons */
/* Widget "clock": hora grande + fecha + batería.
   La hora/fecha se actualizan en el propio móvil; la batería viene del
   estado del servidor (plugin sysmon). Se registra como tipo "clock". */
(() => {
  const { registerWidget } = window.MiniDeck;

  function paint() {
    const el = document.querySelector(".clk-widget");
    if (!el) return;
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    el.querySelector(".clk-time").textContent = `${hh}:${mm}`;
    let f = now.toLocaleDateString("es-ES",
      { weekday: "long", day: "numeric", month: "long" });
    el.querySelector(".clk-date").textContent = f.charAt(0).toUpperCase() + f.slice(1);
  }
  setInterval(paint, 1000);

  function syncBat(d) {
    const el = document.querySelector(".clk-widget");
    if (!el) return;
    const bat = el.querySelector(".clk-bat");
    if (d && d.battery != null) {
      bat.hidden = false;
      bat.textContent = `🔋 ${d.battery}%${d.charging ? " ⚡" : ""}`;
    } else {
      bat.hidden = true;
    }
  }

  function build(w) {
    const el = document.createElement("div");
    el.className = "clk-widget";
    el.dataset.id = w.id;
    el.style.setProperty("--led", w.color || "#60a5fa");
    el.innerHTML = `
      <div class="clk-time">--:--</div>
      <div class="clk-row">
        <span class="clk-date">—</span>
        <span class="clk-bat" hidden></span>
      </div>`;
    setTimeout(paint, 0);
    if (window.MiniDeck.state.sysmon) syncBat(window.MiniDeck.state.sysmon);
    return el;
  }

  registerWidget("clock", {
    label: "Reloj y fecha",
    build,
    sync: syncBat,
    stateKey: "sysmon",
    noAction: true,
  });
})();
