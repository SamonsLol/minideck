# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Robustez: validación de params, timeouts, copias/deshacer, logs,
pulsación larga y decks por defecto por sistema."""
import asyncio
import json
import time

import pytest
from fastapi.testclient import TestClient

import main
from actions import META, REGISTRY, action, validate_params

TOKEN = {"X-MiniDeck-Token": "test-token"}


@pytest.fixture(autouse=True)
def no_system_state(monkeypatch):
    async def fake_collect_state(errors=None):
        return {}
    monkeypatch.setattr(main, "collect_state", fake_collect_state)


@pytest.fixture
def client():
    with TestClient(main.app, client=("192.168.1.50", 50000)) as c:
        yield c


def _result(ws):
    for _ in range(10):
        msg = ws.receive_json()
        if msg["type"] == "result":
            return msg
    raise AssertionError("sin resultado")


# ----------------------------------------------------------- validación ---
@action("t_schema", schema={"level": {"type": "int", "min": 0, "max": 10, "required": True},
                            "mode": {"type": "str", "choices": ["a", "b"]},
                            "$oneOf": [["x", "y"]]})
def _t_schema(params):
    return {"message": f"level={params['level']}"}


@pytest.mark.parametrize("params,error", [
    ({"x": 1}, "Falta el parámetro 'level'"),
    ({"x": 1, "level": 11}, "entre 0 y 10"),
    ({"x": 1, "level": "abc"}, "debe ser un número"),
    ({"x": 1, "level": True}, "tipo int"),
    ({"x": 1, "level": 1, "mode": "z"}, "uno de: a, b"),
    ({"level": 1}, "Falta uno de: x, y"),
])
def test_validate_params_errors(params, error):
    with pytest.raises(ValueError, match=error):
        validate_params("t_schema", dict(params))


def test_validate_params_coerces_numeric_strings():
    p = {"level": "5", "y": 1}
    validate_params("t_schema", p)
    assert p["level"] == 5


def test_invalid_params_reported_to_client(client):
    with client.websocket_connect("/ws?token=test-token") as ws:
        ws.receive_json()
        ws.send_json({"type": "run", "action": "t_schema", "params": {"y": 1, "level": 99}})
        msg = _result(ws)
        assert msg["ok"] is False and "entre 0 y 10" in msg["message"]


def test_core_actions_have_schemas():
    for name in ("hotkey", "launch", "command", "website", "volume_set", "macro", "power"):
        if name in META:
            assert META[name]["schema"], name


def test_schema_endpoint(client):
    data = client.get("/api/actions/schema", headers=TOKEN).json()
    assert data["website"]["schema"]["url"]["required"] is True
    assert "sysmon_get" not in data            # las fuentes de estado no se listan


# -------------------------------------------------------------- timeout ---
@action("t_slow", timeout=0.2)
def _t_slow(params):
    time.sleep(1)


def test_action_timeout():
    res = asyncio.run(main.run_action("t_slow", {}))
    assert res["ok"] is False and "tardó más" in res["message"]


# ------------------------------------------------------ copias / deshacer ---
def _set_label(text):
    cfg = main.load_config()
    cfg["name"] = text
    main.save_config(cfg)


def test_backups_and_undo(client):
    _set_label("A")
    _set_label("B")
    _set_label("C")
    assert main.load_config()["name"] == "C"
    assert len(client.get("/api/backups", headers=TOKEN).json()) >= 2
    with client.websocket_connect("/ws?token=test-token") as ws:
        ws.receive_json()
        ws.send_json({"type": "undo"})
        assert _result(ws)["ok"] is True
    assert main.load_config()["name"] == "B"
    main.restore_backup()
    assert main.load_config()["name"] == "A"


def test_backups_are_capped():
    for i in range(main.MAX_BACKUPS + 5):
        _set_label(f"n{i}")
    assert len(main.list_backups()) <= main.MAX_BACKUPS


def test_restore_unknown_backup(client):
    r = client.post("/api/backups/restore", json={"name": "../../etc/passwd"}, headers=TOKEN)
    assert r.status_code == 400


# ------------------------------------------------------------------ logs ---
def test_logs_endpoint(client):
    main.log.warning("marca-de-prueba-log")
    for h in main.logging.getLogger().handlers:
        h.flush()
    text = client.get("/api/logs?lines=50", headers=TOKEN).text
    assert "marca-de-prueba-log" in text


# ------------------------------------------------------ pulsación larga ---
@action("t_tap")
def _t_tap(params):
    return {"message": "tap"}


@action("t_long")
def _t_long(params):
    return {"message": f"long {params.get('n')}"}


def test_long_press(client):
    cfg = main.load_config()
    cfg["pages"][0]["buttons"].append({"id": "lp", "label": "LP", "action": "t_tap",
                                       "longAction": "t_long", "longParams": {"n": 7}})
    main.save_config(cfg)
    with client.websocket_connect("/ws?token=test-token") as ws:
        ws.receive_json()
        ws.send_json({"type": "press", "buttonId": "lp"})
        assert _result(ws)["message"] == "tap"
        ws.send_json({"type": "press", "buttonId": "lp", "long": True})
        assert _result(ws)["message"] == "long 7"


# --------------------------------------------------- decks por defecto ---
@pytest.mark.parametrize("os_name", ["windows", "macos", "linux"])
def test_default_decks_are_valid(os_name):
    path = main.CONFIG_PATH.parent  # noqa: F841  (solo para importar paths)
    from paths import DEFAULTS_DIR
    cfg = json.loads((DEFAULTS_DIR / f"deck.default.{os_name}.json").read_text(encoding="utf-8"))
    main.validate_config(cfg)
    ids = [b["id"] for p in cfg["pages"] for b in p["buttons"]]
    page_ids = {p["id"] for p in cfg["pages"]}
    for p in cfg["pages"]:
        assert len({b["id"] for b in p["buttons"]}) == len(p["buttons"]), p["id"]
        for b in p["buttons"]:
            if b.get("action") == "page":
                assert b["params"]["page"] in page_ids | {"back"}
    assert ids


def test_registry_has_page_independent_actions():
    # "page" es una acción del cliente: no debe existir en el servidor
    assert "page" not in REGISTRY


# ---------------------------------------------------------------- iconos ---
def test_icon_proxy_caches_and_works_offline(client, monkeypatch, tmp_path):
    import icons
    monkeypatch.setattr(icons, "ICON_CACHE_DIR", tmp_path)
    calls = []

    def fake_download(pack, name):
        calls.append((pack, name))
        return '<svg stroke="currentColor"></svg>'

    monkeypatch.setattr(icons, "_download", fake_download)
    r = client.get("/iconify/lucide/play.svg?color=%23ff0000")   # sin token: público
    assert r.status_code == 200 and 'stroke="#ff0000"' in r.text
    assert r.headers["content-type"].startswith("image/svg+xml")

    def offline(pack, name):
        raise AssertionError("no debería descargar: está en caché")

    monkeypatch.setattr(icons, "_download", offline)
    assert client.get("/iconify/lucide/play.svg").status_code == 200
    assert calls == [("lucide", "play")]


def test_icon_proxy_rejects_bad_input(client):
    assert client.get("/iconify/lucide/..%2Fsecret.svg").status_code in (400, 404)
    assert client.get("/iconify/Lucide/play.svg").status_code == 400
    assert client.get("/iconify/lucide/play.svg?color=red;x").status_code == 400


def test_icon_proxy_missing_icon(client, monkeypatch, tmp_path):
    import icons
    monkeypatch.setattr(icons, "ICON_CACHE_DIR", tmp_path)
    monkeypatch.setattr(icons, "_download", lambda pack, name: None)
    icons._failed.clear()
    assert client.get("/iconify/lucide/no-existe.svg").status_code == 404


def test_actions_not_starved_by_slow_io():
    """Con las descargas de iconos atascadas (sin internet), los botones
    deben seguir respondiendo al instante: usan otro pool de hilos."""
    async def scenario():
        blockers = [main.in_pool(main.IO_POOL, time.sleep, 1.5) for _ in range(12)]
        t0 = time.monotonic()
        res = await main.run_action("t_tap", {})
        elapsed = time.monotonic() - t0
        await asyncio.gather(*blockers)
        return res, elapsed

    res, elapsed = asyncio.run(scenario())
    assert res["ok"] is True
    assert elapsed < 1.0, elapsed
