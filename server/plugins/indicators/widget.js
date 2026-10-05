/* Widget "indicators": clima, red, Git y Docker en vivo.
   Muestra solo los que estén disponibles. */
(() => {
  const { registerWidget, renderIcon } = window.MiniDeck;

  function build(w) {
    const el = document.createElement("div");
    el.className = "ind-widget";
    el.dataset.id = w.id;
    el.style.setProperty("--led", w.color || "#22d3ee");
    el.innerHTML = `<div class="ind-grid"></div>`;
    if (window.MiniDeck.state.indicators) sync(window.MiniDeck.state.indicators);
    return el;
  }

  function tile(icon, big, sub) {
    return `<div class="ind-tile">
      <span class="ind-ic" data-ic="${icon}"></span>
      <div class="ind-big">${big}</div>
      <div class="ind-sub">${sub || "&nbsp;"}</div>
    </div>`;
  }

  function sync(d) {
    window.MiniDeck.state.indicators = d;
    const el = document.querySelector(".ind-widget");
    if (!el) return;
    const tiles = [];
    if (d.weather) tiles.push(tile("lucide:cloud-sun", d.weather.temp || "—",
      (d.weather.desc || "") + (d.weather.city ? " · " + d.weather.city : "")));
    if (d.net) tiles.push(tile("lucide:wifi",
      `↓${d.net.down} <span class="ind-u">KB/s</span>`, `↑${d.net.up} KB/s`));
    if (d.git) tiles.push(tile("lucide:git-branch", d.git.branch || "—",
      d.git.changes ? `${d.git.changes} cambios` : "limpio"));
    if (d.docker) tiles.push(tile("lucide:container", d.docker.running,
      d.docker.running === 1 ? "contenedor" : "contenedores"));
    const grid = el.querySelector(".ind-grid");
    grid.innerHTML = tiles.join("") || `<div class="ind-empty">Sin datos</div>`;
    grid.querySelectorAll(".ind-ic").forEach(s =>
      renderIcon(s, s.dataset.ic, "#8a857a"));
  }

  registerWidget("indicators", {
    label: "Indicadores (clima/red/git/docker)",
    build, sync, stateKey: "indicators", noAction: true,
  });
})();
