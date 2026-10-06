# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Tienda de plugins (server/plugin_store.py). Sin red: el descargador se
sustituye por uno que devuelve un zip construido en memoria."""
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

import main
import plugin_store
from actions import META, OWNERS, PLUGINS, REGISTRY, STATE_SOURCES
from paths import USER_PLUGINS_DIR

TOKEN = {"X-MiniDeck-Token": "test-token"}
LOCAL = {**TOKEN, "Host": "localhost:8765"}

PLUGIN_PY = '''
from actions import action, plugin_settings

@action("{pid}_ping")
def ping(params):
    return {{"message": "pong " + str(plugin_settings("{pid}").get("name"))}}

@action("{pid}_get", state=True)
def get(params):
    return {{"state": {{}}}}
'''


def make_zip(files: dict[str, str], symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = 0o120777 << 16
            zf.writestr(info, "/etc/passwd")
    return buf.getvalue()


def plugin_files(prefix: str, pid: str, settings: dict | None = None) -> dict:
    manifest = {"name": f"Plugin {pid}", "version": "1.2.3", "author": "Test",
                "requires": ["paquete-falso"], "settings": settings or {"name": "x"}}
    return {f"{prefix}plugin.json": json.dumps(manifest),
            f"{prefix}plugin.py": PLUGIN_PY.format(pid=pid)}


@pytest.fixture(autouse=True)
def no_system_state(monkeypatch):
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


@pytest.fixture
def fake_net(monkeypatch):
    """urls → bytes. Lo que no esté en el dict da 404."""
    served: dict[str, bytes] = {}
    calls: list[str] = []

    def fake_download(url):
        calls.append(url)
        if url not in served:
            raise plugin_store.NotFound()
        return served[url]
    monkeypatch.setattr(plugin_store, "download", fake_download)
    served["_calls"] = calls
    return served


def _cleanup(local_client, pid):
    if pid in PLUGINS:
        local_client.delete(f"/api/plugins/{pid}", headers=LOCAL)


def test_install_from_repo_url_falls_back_to_master(local_client, fake_net):
    fake_net["https://codeload.github.com/someone/minideck-tplug/zip/refs/heads/master"] = \
        make_zip({**plugin_files("minideck-tplug-master/", "tplug"),
                  "minideck-tplug-master/README.md": "hola"})
    try:
        r = local_client.post("/api/plugins/install",
                              json={"url": "https://github.com/someone/minideck-tplug"},
                              headers=LOCAL)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] and body["plugin"]["id"] == "tplug"
        assert body["plugin"]["status"] == "loaded"
        assert body["requires"] == ["paquete-falso"]
        assert fake_net["_calls"][0].endswith("/main")        # probó main primero
        # funciona al instante, sin reiniciar
        assert "tplug_ping" in REGISTRY and OWNERS["tplug_ping"] == "tplug"
        assert REGISTRY["tplug_ping"]({})["message"] == "pong x"
        assert "tplug_get" in STATE_SOURCES
        assert (USER_PLUGINS_DIR / "tplug" / "README.md").exists()
        assert not [p for p in USER_PLUGINS_DIR.iterdir() if p.name.startswith(".")]
    finally:
        _cleanup(local_client, "tplug")


def test_install_from_tree_subfolder(local_client, fake_net):
    fake_net["https://codeload.github.com/x/repo/zip/refs/heads/dev"] = make_zip({
        **plugin_files("repo-dev/plugins/tsub/", "tsub"),
        **plugin_files("repo-dev/plugins/otro/", "otro"),
        "repo-dev/README.md": "raiz"})
    try:
        r = local_client.post("/api/plugins/install",
                              json={"url": "https://github.com/x/repo/tree/dev/plugins/tsub"},
                              headers=LOCAL)
        assert r.status_code == 200, r.text
        assert r.json()["plugin"]["id"] == "tsub"
        assert "tsub_ping" in REGISTRY and "otro_ping" not in REGISTRY
        assert not (USER_PLUGINS_DIR / "tsub" / "README.md").exists()
        # reinstalar (actualizar) reemplaza la carpeta y recarga
        r = local_client.post("/api/plugins/install",
                              json={"url": "https://github.com/x/repo/tree/dev/plugins/tsub"},
                              headers=LOCAL)
        assert r.status_code == 200 and "tsub_ping" in REGISTRY
    finally:
        _cleanup(local_client, "tsub")


def test_install_direct_zip_shallowest_plugin(local_client, fake_net):
    fake_net["https://example.com/descargas/cosa.zip"] = make_zip({
        **plugin_files("tzip/", "tzip"), **plugin_files("tzip/sub/nested/", "nested")})
    try:
        r = local_client.post("/api/plugins/install",
                              json={"url": "https://example.com/descargas/cosa.zip"},
                              headers=LOCAL)
        assert r.status_code == 200, r.text
        assert r.json()["plugin"]["id"] == "tzip"
    finally:
        _cleanup(local_client, "tzip")


@pytest.mark.parametrize("bad", [
    {"../evil.py": "x", "repo-main/plugin.py": "x"},
    {"repo-main/../../evil.py": "x", "repo-main/plugin.py": "x"},
    {"/abs/evil.py": "x", "repo-main/plugin.py": "x"},
    {"C:/evil.py": "x", "repo-main/plugin.py": "x"},
])
def test_zip_slip_rejected(local_client, fake_net, bad):
    fake_net["https://codeload.github.com/x/tslip/zip/refs/heads/main"] = make_zip(bad)
    r = local_client.post("/api/plugins/install",
                          json={"url": "https://github.com/x/tslip"}, headers=LOCAL)
    assert r.status_code == 400 and "peligroso" in r.json()["error"]
    assert "tslip" not in PLUGINS
    assert not (USER_PLUGINS_DIR.parent / "evil.py").exists()
    assert not [p for p in USER_PLUGINS_DIR.iterdir() if p.name.startswith(".")]


def test_zip_symlink_rejected(local_client, fake_net):
    fake_net["https://codeload.github.com/x/tlink/zip/refs/heads/main"] = make_zip(
        plugin_files("tlink-main/", "tlink"), symlink="tlink-main/enlace")
    r = local_client.post("/api/plugins/install",
                          json={"url": "https://github.com/x/tlink"}, headers=LOCAL)
    assert r.status_code == 400 and "simbólico" in r.json()["error"]
    assert "tlink" not in PLUGINS


def test_bundled_id_rejected(local_client, fake_net):
    fake_net["https://codeload.github.com/x/minideck-clock/zip/refs/heads/main"] = \
        make_zip(plugin_files("minideck-clock-main/", "clock"))
    r = local_client.post("/api/plugins/install",
                          json={"url": "https://github.com/x/minideck-clock"}, headers=LOCAL)
    assert r.status_code == 409
    assert "incluido" in r.json()["error"]
    assert not PLUGINS["clock"]["user"]


@pytest.mark.parametrize("url", ["http://github.com/x/y", "file:///etc/passwd",
                                 "ftp://example.com/p.zip", "https://example.com/no-zip",
                                 "github.com/x/y", ""])
def test_bad_urls_rejected(local_client, fake_net, url):
    r = local_client.post("/api/plugins/install", json={"url": url}, headers=LOCAL)
    assert r.status_code == 400
    assert fake_net["_calls"] == []


def test_not_a_plugin(local_client, fake_net):
    fake_net["https://codeload.github.com/x/nada/zip/refs/heads/main"] = \
        make_zip({"nada-main/README.md": "x"})
    r = local_client.post("/api/plugins/install",
                          json={"url": "https://github.com/x/nada"}, headers=LOCAL)
    assert r.status_code == 400 and "plugin" in r.json()["error"]


def test_install_and_uninstall_only_local(client, local_client, fake_net):
    r = client.post("/api/plugins/install", json={"url": "https://github.com/x/y"},
                    headers=TOKEN)
    assert r.status_code == 403
    assert client.delete("/api/plugins/hello", headers=TOKEN).status_code == 403
    assert "hello" in PLUGINS
    # el token sigue siendo obligatorio aunque sea local
    r = local_client.post("/api/plugins/install", json={"url": "https://github.com/x/y"},
                          headers={"Host": "localhost:8765"})
    assert r.status_code == 401
    assert fake_net["_calls"] == []


def test_uninstall_removes_actions_and_folder(local_client, fake_net):
    fake_net["https://codeload.github.com/x/tdel/zip/refs/heads/main"] = \
        make_zip(plugin_files("tdel-main/", "tdel"))
    r = local_client.post("/api/plugins/install",
                          json={"url": "https://github.com/x/tdel"}, headers=LOCAL)
    assert r.status_code == 200 and "tdel_ping" in REGISTRY
    r = local_client.delete("/api/plugins/tdel", headers=LOCAL)
    assert r.status_code == 200 and r.json()["ok"]
    for name in ("tdel_ping", "tdel_get"):
        assert name not in REGISTRY and name not in OWNERS and name not in META
    assert "tdel_get" not in STATE_SOURCES
    assert "tdel" not in PLUGINS
    assert not (USER_PLUGINS_DIR / "tdel").exists()
    assert local_client.delete("/api/plugins/tdel", headers=LOCAL).status_code == 404


def test_cannot_uninstall_bundled(local_client):
    r = local_client.delete("/api/plugins/clock", headers=LOCAL)
    assert r.status_code == 400
    assert "clock" in PLUGINS


def test_store_list(client):
    r = client.get("/api/plugins/store", headers=TOKEN)
    assert r.status_code == 200
    data = r.json()
    assert data["canInstall"] is False
    hello = next(p for p in data["plugins"] if p["id"] == "hello")
    assert hello["name"] == "Hola mundo" and hello["user"] is True
    assert hello["schema"] == [{"key": "greeting", "type": "str", "secret": False,
                                "default": "¡Hola!"}]
    assert "greeting" in hello["settings"]
    obs = next(p for p in data["plugins"] if p["id"] == "obs")
    kinds = {s["key"]: (s["type"], s["secret"]) for s in obs["schema"]}
    assert kinds == {"host": ("str", False), "port": ("int", False),
                     "password": ("str", True)}
    assert client.get("/api/plugins/store").status_code == 401


def _restore_cfg(cfg):
    main.save_config(cfg)


def test_settings_coerce_validate_and_mask(client):
    orig = main.load_config()
    try:
        r = client.put("/api/plugins/obs/settings", headers=TOKEN,
                       json={"settings": {"port": "4460", "password": "s3creto",
                                          "host": "pc.local"}})
        assert r.status_code == 200, r.text
        assert r.json()["settings"]["password"] == plugin_store.MASK
        saved = main.load_config()["pluginSettings"]["obs"]
        assert saved == {"port": 4460, "password": "s3creto", "host": "pc.local"}
        from actions import plugin_settings
        assert plugin_settings("obs")["port"] == 4460

        # GET enmascara el secreto
        obs = next(p for p in client.get("/api/plugins/store", headers=TOKEN).json()["plugins"]
                   if p["id"] == "obs")
        assert obs["settings"]["password"] == plugin_store.MASK
        assert "s3creto" not in json.dumps(obs)

        # devolver la máscara conserva el secreto anterior
        r = client.put("/api/plugins/obs/settings", headers=TOKEN,
                       json={"settings": {"password": plugin_store.MASK, "port": 4461}})
        assert r.status_code == 200
        saved = main.load_config()["pluginSettings"]["obs"]
        assert saved["password"] == "s3creto" and saved["port"] == 4461

        # tipos incorrectos y claves desconocidas
        r = client.put("/api/plugins/obs/settings", headers=TOKEN,
                       json={"settings": {"port": "abc"}})
        assert r.status_code == 400 and "port" in r.json()["error"]
        r = client.put("/api/plugins/obs/settings", headers=TOKEN,
                       json={"settings": {"inventado": 1}})
        assert r.status_code == 400 and "inventado" in r.json()["error"]
        assert client.put("/api/plugins/noexiste/settings", headers=TOKEN,
                          json={"settings": {}}).status_code == 404

        # bool y lista (texto con una entrada por línea)
        r = client.put("/api/plugins/indicators/settings", headers=TOKEN,
                       json={"settings": {"weather_enabled": "false"}})
        assert main.load_config()["pluginSettings"]["indicators"]["weather_enabled"] is False
        r = client.put("/api/plugins/homeassistant/settings", headers=TOKEN,
                       json={"settings": {"entities": "light.salon\n\n switch.tv \n",
                                          "token": ""}})
        assert r.status_code == 200
        ha = main.load_config()["pluginSettings"]["homeassistant"]
        assert ha["entities"] == ["light.salon", "switch.tv"] and ha["token"] == ""
        ha_view = next(p for p in client.get("/api/plugins/store", headers=TOKEN)
                       .json()["plugins"] if p["id"] == "homeassistant")
        assert ha_view["settings"]["token"] == ""       # vacío → "" (no máscara)
    finally:
        _restore_cfg(orig)


def test_settings_require_token(client):
    r = client.put("/api/plugins/obs/settings", json={"settings": {"port": 1}})
    assert r.status_code == 401


def test_enable_disable_writes_disabled_plugins(client):
    orig = main.load_config()
    try:
        r = client.post("/api/plugins/hello/enabled", headers=TOKEN, json={"enabled": False})
        assert r.status_code == 200 and "reiniciar" in r.json()["message"]
        assert "hello" in main.load_config()["disabledPlugins"]
        hello = next(p for p in client.get("/api/plugins/store", headers=TOKEN)
                     .json()["plugins"] if p["id"] == "hello")
        assert hello["enabled"] is False
        r = client.post("/api/plugins/hello/enabled", headers=TOKEN, json={"enabled": True})
        assert r.status_code == 200
        assert "hello" not in main.load_config()["disabledPlugins"]
        assert client.post("/api/plugins/hello/enabled", headers=TOKEN,
                           json={"enabled": "no"}).status_code == 400
    finally:
        _restore_cfg(orig)
