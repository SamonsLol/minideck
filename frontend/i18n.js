/* SPDX-License-Identifier: AGPL-3.0-or-later
   SPDX-FileCopyrightText: 2026 Samons */
/* ============================================================
   MiniDeck — traducciones (es / en)
   Idioma: localStorage "minideck-lang" o el del navegador.
   Uso:  t("key")  ·  t("key", { n: 3 })  →  "{n}" se sustituye.
   HTML: <el data-i18n="key">  ·  data-i18n-title="key" (atributo title)
   Para añadir un idioma, añade un objeto más a STRINGS.
   ============================================================ */
(() => {
  const STRINGS = {
    es: {
      "status.title": "Estado de conexión",
      "top.profile": "Cambiar de página según la app activa",
      "top.theme": "Cambiar tema",
      "top.fullscreen": "Pantalla completa",
      "top.edit": "Editar deck",
      "top.about": "MiniDeck © Samons — software libre bajo AGPL-3.0-or-later, sin garantía. Código fuente y licencia",
      "top.lang": "Idioma / Language",
      "fs.exit": "Salir de pantalla completa",
      "a2hs.text": "Para verla a pantalla completa: <b>Compartir</b> ⬆️ → <b>Añadir a pantalla de inicio</b>, y ábrela desde ese icono.",
      "a2hs.install": "Instalar",
      "a2hs.close": "Cerrar",
      "offline": "Sin conexión con el equipo · reconectando…",
      "toast.noConn": "Sin conexión con el equipo",
      "toast.actionError": "Error al ejecutar",
      "toast.saveLater": "Sin conexión: se guardará al reconectar",
      "toast.theme": "Tema: {name}",
      "toast.lang": "Idioma: Español",
      "toast.longHint": "Mantén pulsado para: {action}",
      "toast.exported": "Deck exportado",
      "toast.importBad": "Archivo no válido: {err}",
      "toast.pageMissing": "La página '{page}' no existe",
      "confirm.import": "¿Reemplazar tu deck por «{name}» ({n} páginas)? Podrás deshacerlo.",
      "confirm.deletePage": "¿Eliminar la página \"{name}\" y sus {n} widgets?",
      "confirm.deleteWidget": "¿Eliminar este widget?",
      "prompt.newPage": "Nombre de la página nueva:",
      "prompt.renamePage": "Nuevo nombre de la página:",
      "page.onlyOne": "No puedes eliminar la única página",
      "tool.addPage": "Nueva página",
      "tool.renamePage": "Renombrar página actual",
      "tool.deletePage": "Eliminar página actual",
      "tool.undo": "Deshacer el último cambio",
      "tool.export": "Exportar deck (.json)",
      "tool.import": "Importar deck (.json)",
      "grid.add": "Agregar",
      "w.new": "Nuevo",
      "ed.title": "Editar widget",
      "ed.name": "Nombre",
      "ed.icon": "Icono",
      "ed.searchIcon": "Buscar icono",
      "ed.color": "Color",
      "ed.type": "Tipo",
      "ed.width": "Ancho",
      "ed.height": "Alto",
      "ed.row": "Fila",
      "ed.button": "Botón",
      "ed.action": "Acción",
      "ed.params": "Parámetros (JSON)",
      "ed.min": "Mín",
      "ed.max": "Máx",
      "ed.vparam": "Parám. valor",
      "ed.bind": "Bind estado",
      "ed.long": "Pulsación larga (opcional)",
      "ed.longNone": "— ninguna —",
      "ed.longParams": "Parámetros de la pulsación larga (JSON)",
      "ed.when": "Estado del botón (JSON, opcional)",
      "ed.whenHint": "Ej: {\"key\": \"obs.recording\", \"icon\": \"lucide:circle-stop\", \"color\": \"#f87171\", \"label\": \"Grabando\"}",
      "ed.test": "Probar",
      "ed.dup": "Duplicar",
      "ed.del": "Eliminar",
      "ed.save": "Guardar",
      "ed.badJson": "{field}: JSON inválido ({err})",
      "ed.pageAction": "Ir a página (carpeta)",
      "ip.search": "Buscar icono de lucide…",
      "ip.loading": "Cargando…",
      "ip.offline": "Sin conexión para cargar iconos",
      "ip.none": "Sin resultados",
      "np.nothing": "Nada sonando",
      "np.lyrics": "Letra",
      "pair.title": "Emparejar MiniDeck",
      "pair.reason": "Este dispositivo aún no está autorizado.",
      "pair.invalid": "El código guardado ya no es válido.",
      "pair.help": "En el equipo abre <b>{url}</b> y escanea el QR desde aquí, o escribe el código.",
      "pair.code": "Código",
      "pair.go": "Emparejar",
      "pair.scan": "Escanear QR",
      "pair.cancel": "Cancelar",
      "pair.or": "o escribe el código",
      "pair.photoHint": "Haz una foto al QR de la pantalla del equipo.",
      "pair.notFound": "No se leyó ningún QR de MiniDeck. Acércate un poco y vuelve a intentarlo.",
      "pair.scanFail": "No se pudo cargar el lector de QR.",
      "pair.checking": "Comprobando…",
      "pair.ok": "¡Emparejado!",
      "pair.badCode": "Ese código no es de este equipo o ya no es válido.",
    },
    en: {
      "status.title": "Connection status",
      "top.profile": "Switch page based on the active app",
      "top.theme": "Change theme",
      "top.fullscreen": "Full screen",
      "top.edit": "Edit deck",
      "top.about": "MiniDeck © Samons — free software under AGPL-3.0-or-later, no warranty. Source code and license",
      "top.lang": "Idioma / Language",
      "fs.exit": "Exit full screen",
      "a2hs.text": "For full screen: <b>Share</b> ⬆️ → <b>Add to Home Screen</b>, then open it from that icon.",
      "a2hs.install": "Install",
      "a2hs.close": "Close",
      "offline": "Not connected to the computer · reconnecting…",
      "toast.noConn": "Not connected to the computer",
      "toast.actionError": "Action failed",
      "toast.saveLater": "Offline: will save when reconnected",
      "toast.theme": "Theme: {name}",
      "toast.lang": "Language: English",
      "toast.longHint": "Long-press for: {action}",
      "toast.exported": "Deck exported",
      "toast.importBad": "Invalid file: {err}",
      "toast.pageMissing": "Page '{page}' does not exist",
      "confirm.import": "Replace your deck with “{name}” ({n} pages)? You can undo it.",
      "confirm.deletePage": "Delete page \"{name}\" and its {n} widgets?",
      "confirm.deleteWidget": "Delete this widget?",
      "prompt.newPage": "New page name:",
      "prompt.renamePage": "New name for this page:",
      "page.onlyOne": "You can't delete the only page",
      "tool.addPage": "New page",
      "tool.renamePage": "Rename current page",
      "tool.deletePage": "Delete current page",
      "tool.undo": "Undo last change",
      "tool.export": "Export deck (.json)",
      "tool.import": "Import deck (.json)",
      "grid.add": "Add",
      "w.new": "New",
      "ed.title": "Edit widget",
      "ed.name": "Name",
      "ed.icon": "Icon",
      "ed.searchIcon": "Search icon",
      "ed.color": "Color",
      "ed.type": "Type",
      "ed.width": "Width",
      "ed.height": "Height",
      "ed.row": "Row",
      "ed.button": "Button",
      "ed.action": "Action",
      "ed.params": "Parameters (JSON)",
      "ed.min": "Min",
      "ed.max": "Max",
      "ed.vparam": "Value param",
      "ed.bind": "State bind",
      "ed.long": "Long press (optional)",
      "ed.longNone": "— none —",
      "ed.longParams": "Long-press parameters (JSON)",
      "ed.when": "Button state (JSON, optional)",
      "ed.whenHint": "E.g. {\"key\": \"obs.recording\", \"icon\": \"lucide:circle-stop\", \"color\": \"#f87171\", \"label\": \"Recording\"}",
      "ed.test": "Test",
      "ed.dup": "Duplicate",
      "ed.del": "Delete",
      "ed.save": "Save",
      "ed.badJson": "{field}: invalid JSON ({err})",
      "ed.pageAction": "Go to page (folder)",
      "ip.search": "Search lucide icons…",
      "ip.loading": "Loading…",
      "ip.offline": "Offline: can't load icons",
      "ip.none": "No results",
      "np.nothing": "Nothing playing",
      "np.lyrics": "Lyrics",
      "pair.title": "Pair MiniDeck",
      "pair.reason": "This device isn't authorized yet.",
      "pair.invalid": "The saved code is no longer valid.",
      "pair.help": "On the computer open <b>{url}</b> and scan the QR code from here, or type the code.",
      "pair.code": "Code",
      "pair.go": "Pair",
      "pair.scan": "Scan QR code",
      "pair.cancel": "Cancel",
      "pair.or": "or type the code",
      "pair.photoHint": "Take a photo of the QR code on the computer's screen.",
      "pair.notFound": "No MiniDeck QR code found. Move a little closer and try again.",
      "pair.scanFail": "Couldn't load the QR reader.",
      "pair.checking": "Checking…",
      "pair.ok": "Paired!",
      "pair.badCode": "That code isn't for this computer or is no longer valid.",
    },
  };

  const KEY = "minideck-lang";
  function detect() {
    try {
      const saved = localStorage.getItem(KEY);
      if (saved && STRINGS[saved]) return saved;
    } catch {}
    const nav = (navigator.language || "en").slice(0, 2).toLowerCase();
    return STRINGS[nav] ? nav : "en";
  }
  let lang = detect();
  document.documentElement.lang = lang;

  function t(key, vars) {
    let s = STRINGS[lang]?.[key] ?? STRINGS.es[key] ?? key;
    if (vars) for (const [k, v] of Object.entries(vars)) s = s.split(`{${k}}`).join(String(v));
    return s;
  }

  // Textos con <b>…</b> controlados por nosotros: se insertan como HTML.
  function apply(root = document) {
    root.querySelectorAll("[data-i18n]").forEach((el) => {
      const s = t(el.dataset.i18n);
      if (/<b>/.test(s)) el.innerHTML = s; else el.textContent = s;
    });
    root.querySelectorAll("[data-i18n-title]").forEach((el) => {
      el.title = t(el.dataset.i18nTitle);
      el.setAttribute("aria-label", el.title);
    });
  }

  function setLang(l) {
    if (!STRINGS[l]) return;
    lang = l;
    document.documentElement.lang = l;
    try { localStorage.setItem(KEY, l); } catch {}
    apply();
  }

  window.MiniDeckI18n = {
    t, apply, setLang,
    get lang() { return lang; },
    languages: Object.keys(STRINGS),
  };

  if (document.readyState !== "loading") apply();
  else document.addEventListener("DOMContentLoaded", () => apply());
})();
