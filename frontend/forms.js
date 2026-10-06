/* SPDX-License-Identifier: AGPL-3.0-or-later
   SPDX-FileCopyrightText: 2026 Samons */
/* ============================================================
   MiniDeck — formularios sin JSON para el editor
   - paramsForm(): campos a partir del esquema de la acción
     (texto, números, listas, sí/no…) en vez de escribir JSON.
   - whenForm(): "estado del botón" (cuándo cambia de aspecto).
   El JSON sigue disponible en "Avanzado" y ambos se mantienen
   sincronizados: el formulario escribe en el <textarea> JSON, que
   es lo que el editor guarda.
   ============================================================ */
(() => {
  const T = (k, v) => window.MiniDeckI18n.t(k, v);
  const has = (k) => T(k) !== k;

  /* Nombre legible de un parámetro: traducción conocida o el propio nombre. */
  function paramLabel(name) {
    return has("param." + name) ? T("param." + name)
      : name.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
  }
  function choiceLabel(name, value) {
    const k = `choice.${name}.${value}`;
    return has(k) ? T(k) : String(value);
  }
  function actionLabel(action) {
    return has("act." + action) ? `${T("act." + action)} · ${action}` : action;
  }

  function el(tag, attrs = {}, text) {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "class") n.className = v; else n.setAttribute(k, v === true ? "" : v);
    }
    if (text !== undefined) n.textContent = text;
    return n;
  }

  /* Reglas de los campos: del esquema; si no hay, de los valores actuales o
     del ejemplo del docstring (todos como texto). */
  function rulesFor(info, values) {
    const rules = {};
    const schema = info?.schema || {};
    for (const [k, r] of Object.entries(schema)) if (!k.startsWith("$")) rules[k] = { ...r };
    if (!Object.keys(rules).length && info?.example) {
      try {
        for (const [k, v] of Object.entries(JSON.parse(info.example))) rules[k] = guessRule(v);
      } catch { /* ejemplo no-JSON */ }
    }
    for (const [k, v] of Object.entries(values || {})) if (!rules[k]) rules[k] = guessRule(v);
    for (const g of schema.$oneOf || []) for (const k of g) if (rules[k]) rules[k].oneOf = g;
    return rules;
  }
  function guessRule(v) {
    if (typeof v === "boolean") return { type: "bool" };
    if (typeof v === "number") return { type: Number.isInteger(v) ? "int" : "float" };
    if (Array.isArray(v)) return { type: "list" };
    if (v && typeof v === "object") return { type: "dict" };
    return { type: "str" };
  }

  const PLACEHOLDERS = {
    keys: "ctrl+shift+m", url: "https://…", path: "C:/…/app.exe", app: "chrome",
    cmd: "…", text: "…", name: "…", scene: "…", entity_id: "light.salon", input: "Mic/Aux",
  };

  /* Pinta el formulario en `box` y llama a onChange(params) en cada cambio.
     ctx.pages: [{id,name}] para la acción "page". */
  function paramsForm(box, action, info, values, onChange, ctx = {}) {
    box.textContent = "";
    values = { ...(values || {}) };
    const rules = action === "page" ? { page: { type: "page", required: true } }
      : rulesFor(info, values);
    const keys = Object.keys(rules);
    if (!keys.length) {
      box.appendChild(el("p", { class: "pf-empty" }, T("form.noParams")));
      return;
    }
    const emit = () => onChange({ ...values });

    for (const key of keys) {
      const r = rules[key];
      const id = `pf-${Math.random().toString(36).slice(2, 8)}`;
      const row = el("div", { class: "pf-row" });
      const lab = el("label", { for: id }, paramLabel(key) + (r.required ? " *" : ""));
      row.appendChild(lab);
      let input;
      const cur = values[key];

      if (r.type === "page") {
        input = el("select", { id });
        input.appendChild(el("option", { value: "back" }, T("form.pageBack")));
        for (const p of ctx.pages || []) input.appendChild(el("option", { value: p.id }, p.name || p.id));
        input.value = cur ?? (ctx.pages?.[0]?.id || "back");
        if (cur === undefined) { values[key] = input.value; }
        input.onchange = () => { values[key] = input.value; emit(); };
      } else if (r.choices) {
        input = el("select", { id });
        if (!r.required) input.appendChild(el("option", { value: "" }, T("form.default")));
        for (const c of r.choices) input.appendChild(el("option", { value: c }, choiceLabel(key, c)));
        input.value = cur ?? (r.required ? r.choices[0] : "");
        if (r.required && cur === undefined) values[key] = input.value;
        input.onchange = () => {
          if (input.value === "") delete values[key]; else values[key] = input.value;
          emit();
        };
      } else if (r.type === "bool") {
        input = el("select", { id });
        input.appendChild(el("option", { value: "" }, T("form.default")));
        input.appendChild(el("option", { value: "true" }, T("form.yes")));
        input.appendChild(el("option", { value: "false" }, T("form.no")));
        input.value = cur === undefined ? "" : String(cur);
        input.onchange = () => {
          if (input.value === "") delete values[key]; else values[key] = input.value === "true";
          emit();
        };
      } else if (r.type === "int" || r.type === "float") {
        const wrap = el("div", { class: "pf-num" });
        const num = el("input", { id, type: "number", inputmode: "decimal",
                                  step: r.type === "int" ? 1 : "any", min: r.min, max: r.max });
        num.value = cur ?? "";
        let range = null;
        if (r.min !== undefined && r.max !== undefined && r.max - r.min <= 1000) {
          range = el("input", { type: "range", min: r.min, max: r.max,
                                step: r.type === "int" ? 1 : "any", "aria-label": paramLabel(key) });
          range.value = cur ?? Math.round((r.min + r.max) / 2);
          range.oninput = () => { num.value = range.value; num.oninput(); };
          wrap.appendChild(range);
        }
        num.oninput = () => {
          if (num.value === "") delete values[key];
          else values[key] = r.type === "int" ? parseInt(num.value, 10) : parseFloat(num.value);
          if (range && num.value !== "") range.value = num.value;
          emit();
        };
        wrap.appendChild(num);
        input = wrap;
      } else if (r.type === "list" && (cur === undefined || (Array.isArray(cur) && cur.every((x) => typeof x !== "object")))) {
        // lista simple: un elemento por línea
        input = el("textarea", { id, rows: 3, placeholder: T("form.onePerLine") });
        input.value = Array.isArray(cur) ? cur.join("\n") : "";
        input.oninput = () => {
          const items = input.value.split("\n").map((s) => s.trim()).filter(Boolean);
          if (items.length) values[key] = items; else delete values[key];
          emit();
        };
      } else if (r.type === "list" || r.type === "dict") {
        // estructura compleja (p. ej. pasos de una macro): JSON solo aquí
        input = el("textarea", { id, rows: 4, class: "pf-json", spellcheck: "false" });
        input.value = cur === undefined ? "" : JSON.stringify(cur, null, 2);
        const err = el("small", { class: "pf-err" });
        input.oninput = () => {
          const raw = input.value.trim();
          if (!raw) { delete values[key]; err.textContent = ""; emit(); return; }
          try { values[key] = JSON.parse(raw); err.textContent = ""; emit(); }
          catch { err.textContent = T("form.badJson"); }
        };
        row.appendChild(input);
        row.appendChild(err);
        row.appendChild(el("small", { class: "pf-help" }, T("form.complex")));
        box.appendChild(row);
        continue;
      } else {
        input = el("input", { id, type: key === "url" ? "url" : "text",
                              placeholder: PLACEHOLDERS[key] || "", autocomplete: "off",
                              autocapitalize: "off", spellcheck: "false" });
        input.value = cur ?? "";
        input.oninput = () => {
          if (input.value === "") delete values[key]; else values[key] = input.value;
          emit();
        };
      }
      row.appendChild(input);
      if (r.oneOf) row.appendChild(el("small", { class: "pf-help" },
                                      T("form.oneOf", { fields: r.oneOf.map(paramLabel).join(" / ") })));
      box.appendChild(row);
    }
    emit();   // valores por defecto de campos obligatorios
  }

  /* Rutas del estado en vivo con valor simple (para sugerir "cuándo"). */
  function livePaths(obj, prefix = "", out = [], depth = 0) {
    if (!obj || typeof obj !== "object" || depth > 4 || out.length > 300) return out;
    for (const [k, v] of Object.entries(obj)) {
      const p = prefix ? `${prefix}.${k}` : k;
      if (v !== null && typeof v === "object" && !Array.isArray(v)) livePaths(v, p, out, depth + 1);
      else if (["boolean", "string", "number"].includes(typeof v)) out.push(p);
    }
    return out;
  }

  /* Formulario de "estado del botón". onChange(when|null). */
  function whenForm(box, when, onChange, live) {
    box.textContent = "";
    const w = { ...(when || {}) };
    const listId = "pf-live-paths";
    let dl = document.getElementById(listId);
    if (!dl) { dl = el("datalist", { id: listId }); document.body.appendChild(dl); }
    dl.textContent = "";
    for (const p of livePaths(live)) dl.appendChild(el("option", { value: p }));

    const fields = [
      ["key", "text", T("form.whenKey"), T("form.whenKeyHelp")],
      ["equals", "text", T("form.whenEquals"), T("form.whenEqualsHelp")],
      ["label", "text", T("form.whenLabel")],
      ["icon", "text", T("form.whenIcon"), "lucide:circle-stop · 🔴"],
      ["color", "color", T("form.whenColor")],
    ];
    const emit = () => onChange(w.key ? { ...w } : null);
    for (const [k, type, label, help] of fields) {
      const id = `pf-w-${k}`;
      const row = el("div", { class: "pf-row" });
      row.appendChild(el("label", { for: id }, label));
      const input = el("input", { id, type, autocomplete: "off", autocapitalize: "off",
                                  spellcheck: "false", list: k === "key" ? listId : null,
                                  placeholder: k === "key" ? "obs.recording"
                                    : k === "icon" ? help : null });
      if (type === "color") {
        input.value = w.color || "#f87171";
        const use = el("input", { type: "checkbox", "aria-label": label });
        use.checked = Boolean(w.color);
        const wrap = el("div", { class: "pf-num" });
        use.onchange = () => { if (use.checked) w.color = input.value; else delete w.color; emit(); };
        input.oninput = () => { use.checked = true; w.color = input.value; emit(); };
        wrap.append(use, input);
        row.appendChild(wrap);
      } else {
        input.value = w[k] ?? "";
        input.oninput = () => {
          if (input.value === "") delete w[k];
          else w[k] = k === "equals" ? coerce(input.value) : input.value;
          emit();
        };
        row.appendChild(input);
        if (help && k === "key") row.appendChild(el("small", { class: "pf-help" }, help));
        if (help && k === "equals") row.appendChild(el("small", { class: "pf-help" }, help));
      }
      box.appendChild(row);
    }
  }
  function coerce(s) {
    if (s === "true" || s === "false") return s === "true";
    return s.trim() !== "" && !isNaN(Number(s)) ? Number(s) : s;
  }

  window.MiniDeckForms = { paramsForm, whenForm, actionLabel, paramLabel };
})();
