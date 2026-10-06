# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Plugins OBS y Home Assistant: no necesitan OBS ni HA reales."""
import base64
import hashlib
import json
import socket
import sys
import threading
import time

import pytest
from websockets.sync.server import serve

import main  # noqa: F401  (carga los plugins)
from actions import PLUGINS, REGISTRY

obs = sys.modules["minideck_plugins.obs"]
ha = sys.modules["minideck_plugins.homeassistant"]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(autouse=True)
def reset_caches():
    obs._drop()
    obs._cache.update(data=None, t=0.0, fail_t=0.0)
    ha._cache.update(data=None, t=0.0, fail_t=0.0, key=None)
    yield
    obs._drop()


def test_plugins_loaded():
    for pid in ("obs", "homeassistant"):
        assert PLUGINS[pid]["status"] == "loaded", PLUGINS[pid].get("error")
    for name in ("obs_get", "obs_scene", "obs_record_toggle", "obs_stream_toggle",
                 "obs_record_pause_toggle", "obs_mute_toggle", "obs_replay_save",
                 "ha_get", "ha_service", "ha_toggle", "ha_scene"):
        assert name in REGISTRY


# ------------------------------------------------------------------- OBS ---
def test_obs_auth_string_known_vector():
    secret = base64.b64encode(hashlib.sha256(b"pw" + b"s").digest())
    expected = base64.b64encode(hashlib.sha256(secret + b"c").digest()).decode()
    assert obs.auth_string("pw", "s", "c") == expected


def test_obs_get_offline_is_fast(monkeypatch):
    port = _free_port()
    monkeypatch.setattr(obs, "_settings", lambda: {"host": "127.0.0.1", "port": port,
                                                    "password": ""})
    t0 = time.monotonic()
    r = obs.obs_get({})
    assert r["state"]["obs"]["connected"] is False
    assert time.monotonic() - t0 < 4
    # back-off: la siguiente consulta sale de la caché sin intentar conectar
    t0 = time.monotonic()
    assert obs.obs_get({})["state"]["obs"]["connected"] is False
    assert time.monotonic() - t0 < 0.1


def test_obs_action_offline_raises_clear_error(monkeypatch):
    port = _free_port()
    monkeypatch.setattr(obs, "_settings", lambda: {"host": "127.0.0.1", "port": port,
                                                    "password": ""})
    with pytest.raises(RuntimeError, match="No se pudo conectar con OBS"):
        obs.obs_record_toggle({})


def _fake_obs(password: str):
    """Servidor obs-websocket v5 mínimo para probar el protocolo."""
    st = {"recording": False, "scene": "Juego"}

    def handler(ws):
        hello = {"obsWebSocketVersion": "5.0.0", "rpcVersion": 1}
        if password:
            hello["authentication"] = {"challenge": "ch4ll", "salt": "s4lt"}
        ws.send(json.dumps({"op": 0, "d": hello}))
        ident = json.loads(ws.recv())
        assert ident["op"] == 1 and ident["d"]["rpcVersion"] == 1
        if password and ident["d"].get("authentication") != obs.auth_string(
                password, "s4lt", "ch4ll"):
            ws.close(4009, "Authentication failed")
            return
        ws.send(json.dumps({"op": 2, "d": {"negotiatedRpcVersion": 1}}))
        for raw in ws:
            d = json.loads(raw)["d"]
            rt, data, ok = d["requestType"], {}, True
            if rt == "GetRecordStatus":
                data = {"outputActive": st["recording"], "outputPaused": False}
            elif rt == "GetStreamStatus":
                data = {"outputActive": False}
            elif rt == "GetSceneList":
                data = {"currentProgramSceneName": st["scene"],
                        "scenes": [{"sceneName": "Chat"}, {"sceneName": "Juego"}]}
            elif rt == "ToggleRecord":
                st["recording"] = not st["recording"]
            elif rt == "SetCurrentProgramScene":
                st["scene"] = d["requestData"]["sceneName"]
            else:
                ok = False
            ws.send(json.dumps({"op": 7, "d": {
                "requestType": rt, "requestId": d["requestId"],
                "requestStatus": {"result": ok, "code": 100 if ok else 204},
                "responseData": data}}))

    server = serve(handler, "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.socket.getsockname()[1]


def test_obs_protocol_with_fake_server(monkeypatch):
    server, port = _fake_obs("secreto")
    try:
        monkeypatch.setattr(obs, "_settings", lambda: {"host": "127.0.0.1", "port": port,
                                                        "password": "secreto"})
        snap = obs.obs_get({})["state"]["obs"]
        assert snap == {"connected": True, "recording": False, "paused": False,
                        "streaming": False, "scene": "Juego", "scenes": ["Juego", "Chat"]}
        r = obs.obs_record_toggle({})
        assert r["message"] == "Grabación iniciada"
        assert r["state"]["obs"]["recording"] is True
        r = obs.obs_scene({"scene": "Chat"})
        assert r["state"]["obs"]["scene"] == "Chat"
        with pytest.raises(RuntimeError, match="OBS rechazó"):
            obs.obs_replay_save({})
    finally:
        obs._drop()
        server.shutdown()


def test_obs_wrong_password(monkeypatch):
    server, port = _fake_obs("secreto")
    try:
        monkeypatch.setattr(obs, "_settings", lambda: {"host": "127.0.0.1", "port": port,
                                                        "password": "mala"})
        with pytest.raises(RuntimeError, match="Contraseña de OBS incorrecta"):
            obs.obs_record_toggle({})
        assert obs.obs_get({})["state"]["obs"]["connected"] is False
    finally:
        server.shutdown()


# -------------------------------------------------------- Home Assistant ---
@pytest.mark.parametrize("domain", ["", "Light", "light/../x", "light?a=1", "../api"])
def test_ha_service_rejects_invalid_domain(monkeypatch, domain):
    called = []
    monkeypatch.setattr(ha, "_http", lambda *a, **k: called.append(a))
    with pytest.raises(ValueError):
        ha.ha_service({"domain": domain, "service": "toggle", "entity_id": "light.salon"})
    assert not called


def test_ha_rejects_invalid_entity(monkeypatch):
    monkeypatch.setattr(ha, "_http", lambda *a, **k: pytest.fail("no debe llamar a HA"))
    with pytest.raises(ValueError):
        ha.ha_toggle({"entity_id": "light.salon/../../x"})


def test_ha_service_builds_request(monkeypatch):
    calls = []

    def fake_http(method, path, body=None):
        calls.append((method, path, body))
        return []
    monkeypatch.setattr(ha, "_http", fake_http)
    ha.ha_service({"domain": "light", "service": "turn_on", "entity_id": "light.salon",
                   "data": {"brightness_pct": 40}})
    ha.ha_scene({"entity_id": "scene.cine"})
    assert calls == [
        ("POST", "/api/services/light/turn_on",
         {"brightness_pct": 40, "entity_id": "light.salon"}),
        ("POST", "/api/services/scene/turn_on", {"entity_id": "scene.cine"}),
    ]


def test_ha_missing_token_message(monkeypatch):
    monkeypatch.setattr(ha, "_settings", lambda: {"url": "http://x:8123", "token": ""})
    with pytest.raises(RuntimeError, match="token"):
        ha.ha_toggle({"entity_id": "light.salon"})


def test_ha_get_without_config_is_fast(monkeypatch):
    monkeypatch.setattr(ha, "_http", lambda *a, **k: pytest.fail("no debe usar la red"))
    t0 = time.monotonic()
    r = ha.ha_get({})   # ajustes por defecto: sin token ni entidades
    assert r == {"state": {"ha": {"connected": False, "entities": {}}}}
    assert time.monotonic() - t0 < 0.5


def test_ha_get_unreachable_does_not_raise(monkeypatch):
    port = _free_port()
    monkeypatch.setattr(ha, "_settings", lambda: {
        "url": f"http://127.0.0.1:{port}", "token": "t", "entities": ["light.salon"]})
    r = ha.ha_get({})
    assert r["state"]["ha"]["connected"] is False
