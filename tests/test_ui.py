# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Tests de interfaz con un navegador real (Playwright).

Se saltan si Playwright o su navegador no están instalados:
    pip install playwright && playwright install chromium
En Windows sin Chromium descargado: MINIDECK_TEST_BROWSER=msedge
"""
import os
import socket
import threading
import time

import pytest

pw = pytest.importorskip("playwright.sync_api")

import uvicorn  # noqa: E402

import main  # noqa: E402
from actions import action  # noqa: E402

UI_STATE = {"on": False}


@action("t_ui_get", state=True)
def _t_ui_get(params):
    return {"state": {"t_ui": {"on": UI_STATE["on"], "ent": {"light.salon": {"state": "on"}}}}}


@action("t_ui_tap")
def _t_ui_tap(params):
    return {"message": "toque-corto"}


@action("t_ui_long")
def _t_ui_long(params):
    return {"message": "toque-largo"}


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def server():
    cfg = main.load_config()
    cfg["pages"] = [p for p in cfg["pages"] if p["id"] not in ("ui_a", "ui_b")]
    cfg["pages"].insert(0, {"id": "ui_a", "name": "UI A", "buttons": [
        {"id": "ui_folder", "label": "Carpeta", "icon": "lucide:folder", "action": "page",
         "params": {"page": "ui_b"}},
        {"id": "ui_long", "label": "Largo", "icon": "lucide:timer", "action": "t_ui_tap",
         "longAction": "t_ui_long", "longParams": {}},
        {"id": "ui_state", "label": "Apagado", "icon": "lucide:circle", "action": "t_ui_tap",
         "when": {"key": "t_ui.on", "label": "Encendido", "color": "#f87171"}},
        {"id": "ui_dot", "label": "Luz", "icon": "lucide:lamp", "action": "t_ui_tap",
         "when": {"key": "t_ui.ent.light.salon.state", "equals": "on", "label": "Luz ON"}},
    ]})
    cfg["pages"].insert(1, {"id": "ui_b", "name": "UI B", "buttons": [
        {"id": "ui_back", "label": "Volver", "icon": "lucide:arrow-left", "action": "page",
         "params": {"page": "back"}},
    ]})
    main.save_config(cfg)

    orig_sources = main._state_sources
    main._state_sources = lambda: ["t_ui_get"]   # nada de audio/red reales
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(main.app, host="127.0.0.1", port=port,
                                        log_level="warning"))
    srv.install_signal_handlers = lambda: None
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield f"http://localhost:{port}"
    srv.should_exit = True
    th.join(timeout=5)
    main._state_sources = orig_sources


@pytest.fixture(scope="module")
def browser():
    channel = os.environ.get("MINIDECK_TEST_BROWSER") or None
    with pw.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel=channel)
        except Exception as exc:  # noqa: BLE001
            pytest.skip(f"navegador no disponible: {exc}")
        yield b
        b.close()


def _open(browser, server, width=390, height=844, lang="es"):
    ctx = browser.new_context(viewport={"width": width, "height": height},
                              is_mobile=width < 600, has_touch=True, locale=lang)
    ctx.add_init_script(f"localStorage.setItem('minideck-lang', '{lang}')")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(server + "/")
    page.wait_for_selector(".page-tab")
    page.wait_for_function("document.querySelectorAll('#grid > *').length > 0")
    return ctx, page, errors


OVERFLOW_JS = """() => {
  const grid = document.getElementById('grid').getBoundingClientRect();
  const bad = [];
  for (const el of document.querySelectorAll('#grid > *')) {
    const r = el.getBoundingClientRect();
    if (r.left < grid.left - 1 || r.right > grid.right + 1)
      bad.push(`${el.className} sale de la rejilla`);
    for (const c of el.querySelectorAll('*')) {
      const cr = c.getBoundingClientRect();
      if (cr.width && (cr.right > r.right + 2 || cr.left < r.left - 2)
          && getComputedStyle(c).position !== 'fixed')
        bad.push(`${el.className} > ${c.className || c.tagName} se desborda`);
    }
  }
  // barra superior: ningún botón visible puede quedar cortado fuera de la pantalla
  for (const el of document.querySelectorAll('.topbar button, .topbar a, .topbar h1')) {
    const r = el.getBoundingClientRect();
    if (r.width && (r.right > innerWidth + 1 || r.left < -1))
      bad.push(`topbar: ${el.id || el.tagName} cortado`);
  }
  if (document.documentElement.scrollWidth > innerWidth + 1) bad.push('scroll horizontal');
  return bad;
}"""


@pytest.mark.parametrize("width,height", [(340, 700), (360, 780), (390, 844), (768, 1024),
                                          (844, 390), (1180, 820)])   # vertical y horizontal
def test_no_overflow_on_any_page(browser, server, width, height):
    ctx, page, errors = _open(browser, server, width=width, height=height)
    tabs = page.locator(".page-tab")
    problems = {}
    for i in range(tabs.count()):
        name = tabs.nth(i).inner_text()
        tabs.nth(i).click()
        page.wait_for_timeout(250)
        bad = page.evaluate(OVERFLOW_JS)
        if bad:
            problems[name] = bad[:5]
    ctx.close()
    assert not errors, errors
    assert not problems, problems


def test_folder_navigation(browser, server):
    ctx, page, _ = _open(browser, server)
    page.locator(".page-tab", has_text="UI A").click()
    page.click('.key[data-id="ui_folder"]')
    page.wait_for_selector('.key[data-id="ui_back"]')
    page.click('.key[data-id="ui_back"]')
    page.wait_for_selector('.key[data-id="ui_folder"]')
    ctx.close()


def test_long_press(browser, server):
    ctx, page, _ = _open(browser, server)
    page.locator(".page-tab", has_text="UI A").click()
    key = page.locator('.key[data-id="ui_long"]')
    key.click()
    page.wait_for_function("document.getElementById('toast').textContent.includes('toque-corto')")
    box = key.bounding_box()
    # registra los eventos de puntero para diagnosticar si falla
    page.evaluate("""() => { window._ev = [];
      const k = document.querySelector('.key[data-id="ui_long"]');
      for (const ev of ['pointerdown', 'pointerup', 'pointercancel', 'pointerleave', 'click'])
        k.addEventListener(ev, () => window._ev.push(ev)); }""")
    page.mouse.move(box["x"] + 20, box["y"] + 20)
    page.mouse.down()
    page.wait_for_timeout(1200)   # umbral 550 ms: margen amplio para CI lentos
    page.mouse.up()
    try:
        page.wait_for_function(
            "document.getElementById('toast').textContent.includes('toque-largo')", timeout=8000)
    except Exception:
        info = page.evaluate("""() => ({ev: window._ev, page: state.currentPage,
          toast: document.getElementById('toast').textContent, ws: state.ws.readyState})""")
        raise AssertionError(f"pulsación larga no llegó: {info} box={box}") from None
    ctx.close()


def test_stateful_button(browser, server):
    UI_STATE["on"] = False
    ctx, page, _ = _open(browser, server)
    page.locator(".page-tab", has_text="UI A").click()
    label = page.locator('.key[data-id="ui_state"] .label')
    assert label.inner_text() == "Apagado"
    # clave con puntos dentro del id de entidad (estilo Home Assistant)
    page.wait_for_function(
        "document.querySelector('.key[data-id=\"ui_dot\"] .label').textContent === 'Luz ON'")
    UI_STATE["on"] = True
    page.wait_for_function(
        "document.querySelector('.key[data-id=\"ui_state\"] .label').textContent === 'Encendido'",
        timeout=5000)
    ctx.close()


def test_offline_banner(browser, server):
    ctx, page, _ = _open(browser, server)
    page.wait_for_function("document.getElementById('statusDot').classList.contains('connected')")
    assert page.locator("#offlineBanner").is_hidden()
    page.evaluate("state.ws.close()")
    page.wait_for_selector("#offlineBanner", state="visible")
    page.wait_for_selector("#offlineBanner", state="hidden", timeout=8000)   # reconecta
    ctx.close()


def test_language_toggle(browser, server):
    ctx, page, _ = _open(browser, server, lang="en")
    assert page.locator("#langBtn").inner_text() == "EN"
    assert page.locator("#editBtn").get_attribute("title") == "Edit deck"
    page.click("#langBtn")
    assert page.locator("#langBtn").inner_text() == "ES"
    assert page.locator("#editBtn").get_attribute("title") == "Editar deck"
    ctx.close()


def test_editor_preserves_unknown_fields_and_fills_template(browser, server):
    cfg = main.load_config()
    btn = next(b for p in cfg["pages"] if p["id"] == "ui_a" for b in p["buttons"]
               if b["id"] == "ui_long")
    btn["custom_field"] = 42
    main.save_config(cfg)
    ctx, page, _ = _open(browser, server)
    page.locator(".page-tab", has_text="UI A").click()
    page.click("#editBtn")
    # en modo edición las teclas se "mueven" (animación): forzar el clic
    page.click('.key[data-id="ui_long"]', force=True)
    page.wait_for_selector("#editSheet.open")
    assert page.locator(".f-long").input_value() == "t_ui_long"
    page.click(".sheet-save")
    page.wait_for_timeout(600)
    saved = next(b for p in main.load_config()["pages"] if p["id"] == "ui_a"
                 for b in p["buttons"] if b["id"] == "ui_long")
    assert saved["custom_field"] == 42 and saved["longAction"] == "t_ui_long"
    # plantilla de params al cambiar de acción
    page.click('.key[data-id="ui_folder"]', force=True)
    page.wait_for_selector("#editSheet.open")
    page.fill(".f-params", "{}")
    page.select_option(".f-action", "website")
    assert '"url"' in page.locator(".f-params").input_value()
    ctx.close()


def test_export_never_includes_plugin_secrets(browser, server):
    cfg = main.load_config()
    cfg["pluginSettings"] = {"homeassistant": {"token": "SECRETO-HA"},
                             "obs": {"password": "SECRETO-OBS"}}
    main.save_config(cfg)
    ctx, page, _ = _open(browser, server)
    page.click("#editBtn")
    with page.expect_download() as dl:
        page.locator(".page-tab.tool", has_text="⇩").click()
    text = open(dl.value.path(), encoding="utf-8").read()
    ctx.close()
    assert "SECRETO" not in text and "pluginSettings" not in text
    assert '"pages"' in text


def _qr_png(tmp_path, text, name="qr.png"):
    import segno
    path = tmp_path / name
    segno.make(text, error="m").save(str(path), scale=8, border=4)
    return path


def _unpaired(browser, server):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="es")
    ctx.add_init_script("localStorage.setItem('minideck-lang', 'es')")
    page = ctx.new_page()
    page.route("**/api/pair", lambda r: r.fulfill(status=403, body="{}"))  # "otro móvil"
    page.goto(server + "/")
    page.wait_for_selector("#pairing .pair-scan")
    return ctx, page


def test_pair_by_scanning_qr_photo(browser, server, tmp_path):
    """La PWA instalada no comparte el token con el navegador: se empareja
    escaneando el QR desde la propia app (foto → jsQR)."""
    qr = _qr_png(tmp_path, f"http://192.168.1.50:8765/?token={main.auth.TOKEN}")
    ctx, page = _unpaired(browser, server)
    with page.expect_file_chooser() as fc:
        page.click("#pairing .pair-scan")
    fc.value.set_files(str(qr))
    page.wait_for_selector("#pairing", state="detached", timeout=15000)
    assert page.evaluate("localStorage.getItem('minideck-token')") == main.auth.TOKEN
    page.wait_for_function("document.getElementById('statusDot').classList.contains('connected')")
    ctx.close()


def test_pair_rejects_qr_from_other_computer(browser, server, tmp_path):
    qr = _qr_png(tmp_path, "http://10.0.0.9:8765/?token=token-de-otro-equipo", "otro.png")
    ctx, page = _unpaired(browser, server)
    with page.expect_file_chooser() as fc:
        page.click("#pairing .pair-scan")
    fc.value.set_files(str(qr))
    page.wait_for_function(
        "document.querySelector('#pairing .pair-status').textContent.includes('no es de este')")
    assert page.evaluate("localStorage.getItem('minideck-token')") in (None, "")
    ctx.close()


def test_pair_photo_without_qr(browser, server, tmp_path):
    from PIL import Image
    blank = tmp_path / "blank.png"
    Image.new("RGB", (400, 300), "white").save(blank)
    ctx, page = _unpaired(browser, server)
    with page.expect_file_chooser() as fc:
        page.click("#pairing .pair-scan")
    fc.value.set_files(str(blank))
    page.wait_for_function(
        "document.querySelector('#pairing .pair-status').textContent.includes('Acércate')")
    ctx.close()


def _ui_a_order():
    page = next(p for p in main.load_config()["pages"] if p["id"] == "ui_a")
    return [b["id"] for b in page["buttons"]]


def test_drag_to_reorder_with_mouse(browser, server):
    """En el navegador de escritorio (ratón) se puede arrastrar para reordenar."""
    before = _ui_a_order()
    ctx = browser.new_context(viewport={"width": 1100, "height": 800}, locale="es")
    ctx.add_init_script("localStorage.setItem('minideck-lang', 'es')")
    page = ctx.new_page()
    page.goto(server + "/")
    page.wait_for_selector(".page-tab")
    page.locator(".page-tab", has_text="UI A").click()
    page.click("#editBtn")
    page.wait_for_timeout(400)
    src = page.locator(f'.key[data-id="{before[0]}"]').bounding_box()
    dst = page.locator(f'.key[data-id="{before[-1]}"]').bounding_box()
    page.mouse.move(src["x"] + src["width"] / 2, src["y"] + src["height"] / 2)
    page.mouse.down()
    page.wait_for_timeout(450)                      # mantener para empezar a arrastrar
    page.mouse.move(dst["x"] + dst["width"] / 2, dst["y"] + dst["height"] / 2, steps=25)
    page.wait_for_timeout(200)
    page.mouse.up()
    page.wait_for_timeout(800)
    after = _ui_a_order()
    page.click("#editBtn")
    ctx.close()
    assert after != before and after[-1] == before[0], (before, after)
    # dejarlo como estaba para el resto de tests
    cfg = main.load_config()
    pg = next(p for p in cfg["pages"] if p["id"] == "ui_a")
    pg["buttons"].sort(key=lambda b: before.index(b["id"]))
    main.save_config(cfg)


def test_escape_leaves_fullscreen_and_restores_topbar(browser, server):
    ctx = browser.new_context(viewport={"width": 1100, "height": 800}, locale="es")
    page = ctx.new_page()
    page.goto(server + "/")
    page.wait_for_selector(".page-tab")
    page.click("#fsBtn")
    page.wait_for_function("document.body.classList.contains('immersive')")
    assert page.locator(".topbar").is_hidden()
    assert page.locator("#fsExit").is_visible()          # salida visible con ratón
    page.keyboard.press("Escape")
    page.wait_for_function("!document.body.classList.contains('immersive')")
    assert page.locator(".topbar").is_visible()
    # y el botón ✕ también sirve
    page.click("#fsBtn")
    page.click("#fsExit")
    page.wait_for_function("!document.body.classList.contains('immersive')")
    ctx.close()


@pytest.mark.parametrize("path", ["/", "/panel.html"])
def test_lcd_theme_reaches_editors(browser, server, path):
    """Con el tema LCD, el editor del deck y el Panel de widgets también son claros."""
    ctx = browser.new_context(viewport={"width": 1000, "height": 700}, locale="es")
    ctx.add_init_script("localStorage.setItem('minideck-theme', 'lcd')")
    page = ctx.new_page()
    page.goto(server + path)
    if path == "/":
        page.wait_for_selector(".page-tab")
        page.locator(".page-tab", has_text="UI A").click()
        page.click("#editBtn")
        page.click('.key[data-id="ui_long"]', force=True)
        page.wait_for_selector("#editSheet.open")
        sel = "#editSheet"
    else:
        page.wait_for_timeout(500)
        sel = "body"
    bg = page.evaluate(f"getComputedStyle(document.querySelector('{sel}')).backgroundColor")
    rgb = [int(x) for x in bg[bg.index("(") + 1:bg.index(")")].split(",")[:3]]
    ctx.close()
    assert sum(rgb) / 3 > 150, f"{path}: fondo oscuro con tema LCD ({bg})"


def test_everything_works_without_javascript(browser, server):
    """JavaScript desactivado: / lleva al modo básico, y emparejar, pulsar,
    abrir carpetas y editar funcionan con formularios."""
    ctx = browser.new_context(java_script_enabled=False, viewport={"width": 390, "height": 844},
                              locale="es")
    page = ctx.new_page()
    page.goto(server + "/")
    page.wait_for_url("**/basic", timeout=10000)
    page.fill('input[name="code"]', main.auth.TOKEN)
    page.click(".b-pair button")
    page.wait_for_selector(".b-tabs")
    page.click('.b-tab:has-text("UI A")')
    page.click('form:has(input[value="ui_long"]) .b-key')        # toque
    assert "toque-corto" in page.locator(".b-flash").inner_text()
    page.click('form:has(input[value="ui_long"]) .b-long')       # "mantener"
    assert "toque-largo" in page.locator(".b-flash").inner_text()
    page.click('a.b-key:has-text("Carpeta")')                    # carpeta
    page.click('a.b-key:has-text("Volver")')
    assert page.locator('.b-tab.on').inner_text() == "UI A"
    # editor sin JS
    page.click('a.b-btn[href^="/basic/edit"]')
    page.click('li:has-text("Largo") a.b-mini')
    page.fill('input[name="label"]', "Largo editado")
    page.click("button.b-primary")
    assert page.locator(".b-flash").is_visible()
    labels = [b.get("label") for p in main.load_config()["pages"] if p["id"] == "ui_a"
              for b in p["buttons"]]
    assert "Largo editado" in labels
    ctx.close()
    # dejarlo como estaba
    cfg = main.load_config()
    for p in cfg["pages"]:
        for b in p["buttons"]:
            if b.get("label") == "Largo editado":
                b["label"] = "Largo"
    main.save_config(cfg)


def test_browser_posts_are_accepted(browser, server):
    """Regresión: con Referrer-Policy no-referrer el navegador enviaba
    "Origin: null" y la protección anti-CSRF rechazaba los POST legítimos
    (p. ej. guardar un widget desde el Panel)."""
    ctx, page, _ = _open(browser, server)
    status = page.evaluate("""async () => (await MiniDeckAuth.api('/api/custom_widget', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({id: 'regresion_origin', name: 'R', html: '<b>x</b>'})})).status""")
    ctx.close()
    assert status == 200
    assert "regresion_origin" in main.load_config().get("customWidgets", {})
