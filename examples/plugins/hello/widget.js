/* SPDX-License-Identifier: AGPL-3.0-or-later
   SPDX-FileCopyrightText: 2026 Samons */
/* Widget del plugin «hello»: muestra el contador y saluda al tocarlo. */
(() => {
  const { registerWidget, run } = window.MiniDeck;
  let last = null;

  function paint() {
    for (const el of document.querySelectorAll(".hello-widget .hello-count")) {
      el.textContent = last == null ? "–" : String(last.count);
    }
  }

  registerWidget("hello", {
    label: "Hola mundo",
    stateKey: "hello",
    keepParams: true,               // el editor permite editar params (name)
    build(w) {
      const el = document.createElement("button");
      el.className = "hello-widget";
      el.dataset.id = w.id;
      el.style.setProperty("--led", w.color || "#60a5fa");
      el.innerHTML = '<span class="hello-label">Saludos</span><span class="hello-count"></span>';
      el.onclick = () => run("hello_say", w.params || {});
      setTimeout(paint, 0);
      return el;
    },
    sync(data) {
      last = data;
      paint();
    },
  });
})();
