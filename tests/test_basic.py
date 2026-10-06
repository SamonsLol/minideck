# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Modo sin JavaScript (/basic): todo con formularios HTML."""
import json

import pytest
from fastapi.testclient import TestClient

import main
from actions import action

TOKEN = "test-token"
CALLS = []


@action("t_basic_tap")
def _tap(params):
    CALLS.append(("tap", params))
    return {"message": "tap-ok"}


@action("t_basic_long")
def _long(params):
    CALLS.append(("long", params))
    return {"message": "long-ok"}


@action("t_basic_set", schema={"level": {"type": "int", "min": 0, "max": 100, "required": True}})
def _set(params):
    CALLS.append(("set", params))
    return {"message": f"level {params['level']}"}


@pytest.fixture(autouse=True)
def setup(monkeypatch):
    async def fake_state(errors=None):
        return {"t": {"on": True}, "obs": {"connected": True, "scene": "A", "scenes": ["A", "B"],
                                           "recording": True}}
    monkeypatch.setattr(main, "collect_state", fake_state)
    cfg = main.load_config()
    cfg["pages"] = [p for p in cfg["pages"] if not p["id"].startswith("nb_")]
    cfg["pages"][:0] = [
        {"id": "nb_a", "name": "NB A", "buttons": [
            {"id": "nb_tap", "label": "Tap", "icon": "lucide:play", "color": "#60a5fa",
             "action": "t_basic_tap", "params": {"x": 1},
             "longAction": "t_basic_long", "longParams": {"y": 2}},
            {"id": "nb_state", "label": "Off", "icon": "🎮", "action": "t_basic_tap",
             "when": {"key": "t.on", "label": "Encendido"}},
            {"id": "nb_folder", "label": "Carpeta", "action": "page", "params": {"page": "nb_b"}},
            {"id": "nb_slider", "type": "slider", "label": "Vol", "action": "t_basic_set",
             "valueParam": "level", "min": 0, "max": 100},
            {"id": "nb_obs", "type": "obs", "label": "OBS"},
            {"id": "nb_custom", "type": "custom:algo", "label": "Mío"},
        ]},
        {"id": "nb_b", "name": "NB B", "buttons": [
            {"id": "nb_back", "label": "Volver", "action": "page", "params": {"page": "back"}}]},
    ]
    cfg["pluginSettings"] = {"obs": {"password": "SECRETO"}}
    main.save_config(cfg)
    CALLS.clear()


@pytest.fixture
def anon():
    with TestClient(main.app, client=("192.168.1.50", 50000)) as c:
        yield c


@pytest.fixture
def client(anon):
    r = anon.post("/basic/pair", data={"code": TOKEN}, follow_redirects=False)
    assert r.status_code == 303
    return anon


# ---------------------------------------------------------- emparejar ---
def test_unpaired_shows_pair_form(anon):
    r = anon.get("/basic")
    assert r.status_code == 200
    assert 'action="/basic/pair"' in r.text and "<script" not in r.text


def test_pair_sets_secure_cookie(anon):
    r = anon.post("/basic/pair", data={"code": TOKEN}, follow_redirects=False)
    cookie = r.headers["set-cookie"].lower()
    assert "minideck_token=" in cookie and "httponly" in cookie and "samesite=strict" in cookie


def test_pair_wrong_code(anon):
    r = anon.post("/basic/pair", data={"code": "mal"})
    assert 'class="b-flash err"' in r.text
    assert "minideck_token" not in anon.cookies


def test_qr_link_sets_cookie(anon):
    r = anon.get(f"/?token={TOKEN}")
    assert "minideck_token" in r.headers.get("set-cookie", "")


def test_cookie_also_authorizes_js_api(client):
    assert client.get("/api/info").status_code == 200


def test_posts_reject_foreign_origin(client):
    r = client.post("/basic/press", data={"id": "nb_tap"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and not CALLS


def test_actions_require_pairing(anon):
    assert anon.post("/basic/press", data={"id": "nb_tap"}).status_code == 403
    assert not CALLS


# --------------------------------------------------------------- deck ---
def test_deck_renders_without_js(client):
    r = client.get("/basic?page=nb_a")
    t = r.text
    assert "<script" not in t
    assert 'action="/basic/press"' in t and 'name="long"' in t        # pulsación larga
    assert "Encendido" in t                                            # when (estado)
    assert 'href="/basic?page=nb_b&amp;from=nb_a"' in t                # carpeta
    assert 'type="range"' in t                                         # slider
    assert "⏺ REC" in t and 'value="B"' in t                           # OBS
    assert "JavaScript" in t                                           # widget propio


def test_press_and_long_press(client):
    r = client.post("/basic/press", data={"id": "nb_tap", "page": "nb_a"})
    assert "tap-ok" in r.text
    r = client.post("/basic/press", data={"id": "nb_tap", "page": "nb_a", "long": "1"})
    assert "long-ok" in r.text
    assert CALLS == [("tap", {"x": 1}), ("long", {"y": 2})]


def test_back_link_returns_to_origin(client):
    t = client.get("/basic?page=nb_b&from=nb_a").text
    assert 'href="/basic?page=nb_a"' in t


def test_widget_run_validates_params(client):
    r = client.post("/basic/run", data={"page": "nb_a", "action": "t_basic_set", "p_level": "42"})
    assert "level 42" in r.text
    r = client.post("/basic/run", data={"page": "nb_a", "action": "t_basic_set", "p_level": "500"})
    assert "entre 0 y 100" in r.text


def test_theme_and_language_cookies(client):
    client.post("/basic/prefs", data={"toggle": "theme", "back": "/basic"})
    assert 'data-theme="lcd"' in client.get("/basic").text
    client.post("/basic/prefs", data={"toggle": "lang", "back": "https://evil.example"})
    assert client.get("/basic").status_code == 200


# ------------------------------------------------------------- editor ---
def _page(pid):
    return next(p for p in main.load_config()["pages"] if p["id"] == pid)


def test_editor_add_edit_move_delete(client):
    client.post("/basic/edit/add", data={"page": "nb_a"})
    new = _page("nb_a")["buttons"][-1]
    r = client.post("/basic/edit/item", data={
        "page": "nb_a", "id": new["id"], "label": "Nuevo botón", "icon": "lucide:star",
        "color": "#ff0000", "type": "button", "w": "2", "h": "1", "action": "website",
        "params": '{"url": "https://example.com"}', "longAction": "", "longParams": "",
        "when": ""})
    assert "Guardado" in r.text or "Saved" in r.text
    b = _page("nb_a")["buttons"][-1]
    assert b["label"] == "Nuevo botón" and b["w"] == 2 and b["params"]["url"].startswith("https")
    assert "longAction" not in b and "when" not in b
    client.post("/basic/edit/move", data={"page": "nb_a", "id": b["id"], "dir": "-1"})
    assert _page("nb_a")["buttons"][-2]["id"] == b["id"]
    client.post("/basic/edit/delete", data={"page": "nb_a", "id": b["id"]})
    assert b["id"] not in [x["id"] for x in _page("nb_a")["buttons"]]


def test_editor_bad_json_keeps_form(client):
    r = client.post("/basic/edit/item", data={
        "page": "nb_a", "id": "nb_tap", "label": "X", "type": "button", "w": "1", "h": "1",
        "action": "t_basic_tap", "params": "{mal json", "longAction": "", "when": ""})
    assert "JSON" in r.text and 'name="params"' in r.text
    assert _page("nb_a")["buttons"][0]["label"] == "Tap"       # no se guardó


def test_editor_preserves_unknown_fields(client):
    cfg = main.load_config()
    _page_cfg = next(p for p in cfg["pages"] if p["id"] == "nb_a")
    _page_cfg["buttons"][0]["plugin_extra"] = {"keep": True}
    main.save_config(cfg)
    client.post("/basic/edit/item", data={
        "page": "nb_a", "id": "nb_tap", "label": "Tap2", "type": "button", "w": "1", "h": "1",
        "action": "t_basic_tap", "params": "{}", "longAction": "", "when": ""})
    b = _page("nb_a")["buttons"][0]
    assert b["label"] == "Tap2" and b["plugin_extra"] == {"keep": True}


def test_editor_pages_and_undo(client):
    client.post("/basic/edit/page", data={"op": "add", "name": "Nueva"})
    names = [p["name"] for p in main.load_config()["pages"]]
    assert "Nueva" in names
    pid = next(p["id"] for p in main.load_config()["pages"] if p["name"] == "Nueva")
    client.post("/basic/edit/page", data={"op": "rename", "page": pid, "name": "Renombrada"})
    assert _page(pid)["name"] == "Renombrada"
    client.post("/basic/edit/undo", data={"page": pid})
    assert _page(pid)["name"] == "Nueva"
    client.post("/basic/edit/page", data={"op": "delete", "page": pid})
    assert pid not in [p["id"] for p in main.load_config()["pages"]]


def test_export_without_secrets_and_import(client):
    r = client.get("/basic/export")
    assert "attachment" in r.headers["content-disposition"]
    assert "SECRETO" not in r.text and "pluginSettings" not in r.text
    deck = json.loads(r.text)
    deck["name"] = "Importado"
    client.post("/basic/edit/import", data={"json": json.dumps(deck)})
    cfg = main.load_config()
    assert cfg["name"] == "Importado"
    assert cfg["pluginSettings"]["obs"]["password"] == "SECRETO"   # se conservan
    r = client.post("/basic/edit/import", data={"json": "{\"pages\": []}"})
    assert main.load_config()["name"] == "Importado"               # inválido: no se aplica
