import json

import pytest
from fastapi.testclient import TestClient

import main
from actions import PLUGINS, REGISTRY

TOKEN = {"X-MiniDeck-Token": "test-token"}
LOCAL = {"Host": "localhost:8765"}


@pytest.fixture(autouse=True)
def no_system_state(monkeypatch):
    """Los tests no deben tocar el sistema real (audio, AppleScript, red)."""
    async def fake_collect_state(errors=None):
        return {}
    monkeypatch.setattr(main, "collect_state", fake_collect_state)


@pytest.fixture
def client():
    with TestClient(main.app, client=("192.168.1.50", 50000)) as c:
        yield c


@pytest.fixture
def local_client():
    with TestClient(main.app, client=("127.0.0.1", 50000)) as c:
        yield c


# ------------------------------------------------------------------ auth ---
def test_api_requires_token(client):
    assert client.get("/api/config").status_code == 401
    assert client.get("/api/config", headers={"X-MiniDeck-Token": "mal"}).status_code == 401
    assert client.get("/api/config", headers=TOKEN).status_code == 200
    assert client.get("/api/config?token=test-token").status_code == 200


def test_frontend_is_public(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "auth.js" in r.text


def test_pair_and_qr_only_from_localhost(client, local_client):
    assert client.get("/api/pair").status_code == 403
    assert client.get("/qr").status_code == 403
    r = local_client.get("/api/pair", headers=LOCAL)
    assert r.status_code == 200 and r.json()["token"] == "test-token"
    assert local_client.get("/qr", headers=LOCAL).status_code == 200


def test_pair_blocks_dns_rebinding(local_client):
    # cliente local pero Host de otro dominio → ataque de DNS rebinding
    r = local_client.get("/api/pair", headers={"Host": "evil.example:8765"})
    assert r.status_code == 403


def test_pair_blocks_cross_origin(local_client):
    r = local_client.get("/api/pair", headers={**LOCAL, "Origin": "https://evil.example"})
    assert r.status_code == 403


def test_post_rejects_foreign_origin(client):
    r = client.post("/api/custom_widget", json={"id": "x"},
                    headers={**TOKEN, "Origin": "https://evil.example"})
    assert r.status_code == 403


def test_pip_only_local(client):
    r = client.post("/api/pip", json={"package": "requests"}, headers=TOKEN)
    assert r.status_code == 403


def test_websocket_rejects_without_token(client):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
    assert exc.value.code == 4401


def test_websocket_flow(client):
    with client.websocket_connect("/ws?token=test-token") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "config"
        assert msg["data"]["pages"]
        ws.send_json({"type": "run", "action": "hello_say", "params": {"name": "Samons"}})
        for _ in range(5):
            msg = ws.receive_json()
            if msg["type"] == "result":
                break
        assert msg["ok"] is True
        assert msg["message"] == "¡Hola! Samons"
        assert msg["state"]["hello"]["count"] >= 1


def test_manifest_start_url(client):
    assert client.get("/manifest.webmanifest").json()["start_url"] == "/"
    data = client.get("/manifest.webmanifest?token=test-token").json()
    assert data["start_url"] == "/?token=test-token"
    assert client.get("/manifest.webmanifest?token=mal").json()["start_url"] == "/"


# ---------------------------------------------------------------- config ---
def test_config_seeded_from_default():
    assert main.CONFIG_PATH.exists()
    cfg = json.loads(main.CONFIG_PATH.read_text(encoding="utf-8"))
    assert cfg["pages"]


@pytest.mark.parametrize("bad", [None, [], {}, {"pages": []}, {"pages": [{"name": "x"}]},
                                 {"pages": [{"id": "a", "buttons": "no"}]}])
def test_validate_config_rejects_garbage(bad):
    with pytest.raises(ValueError):
        main.validate_config(bad)


def test_save_config_does_not_corrupt_on_invalid():
    before = main.CONFIG_PATH.read_text(encoding="utf-8")
    with pytest.raises(ValueError):
        main.save_config({"pages": []})
    assert main.CONFIG_PATH.read_text(encoding="utf-8") == before


# --------------------------------------------------------------- plugins ---
def test_user_plugin_loaded_with_settings():
    info = PLUGINS["hello"]
    assert info["status"] == "loaded"
    assert info["user"] is True
    assert "hello_say" in info["actions"]
    assert REGISTRY["hello_say"]({"name": "x"})["message"] == "¡Hola! x"
    assert "hello_get" in info["actions"]


def test_incompatible_plugin_skipped():
    assert PLUGINS["otherplat"]["status"] == "skipped"


def test_broken_plugin_reports_error():
    assert PLUGINS["broken"]["status"] == "error"
    assert "paquete_que_no_existe_xyz" in PLUGINS["broken"]["error"]


def test_bundled_plugins_discovered():
    for pid in ("sysmon", "clock", "indicators"):
        assert pid in PLUGINS


def test_plugins_api(client):
    assets = client.get("/api/plugins", headers=TOKEN).json()
    assert {"type": "js", "url": "/plugins/hello/widget.js?v=1.0.0"} in assets
    info = client.get("/api/plugins/info", headers=TOKEN).json()
    ids = {p["id"]: p for p in info["plugins"]}
    assert ids["hello"]["status"] == "loaded"
    assert "macro" in info["core_actions"]


def test_plugin_static_no_traversal(client):
    assert client.get("/plugins/hello/widget.js").status_code == 200
    assert client.get("/plugins/hello/plugin.py").status_code == 404
    assert client.get("/plugins/hello/..%2F..%2Fconfig%2Fauth_token").status_code == 404
    assert client.get("/plugins/nope/widget.js").status_code == 404


def test_unknown_action(client):
    with client.websocket_connect("/ws?token=test-token") as ws:
        ws.receive_json()
        ws.send_json({"type": "run", "action": "no_existe", "params": {}})
        for _ in range(5):
            msg = ws.receive_json()
            if msg["type"] == "result":
                break
        assert msg["ok"] is False
