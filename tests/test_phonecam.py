# SPDX-License-Identifier: AGPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Samons
"""Webcam del móvil: el teléfono envía JPEG y el PC los sirve (OBS, MJPEG)."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import main
import phonecam

LOCAL = {"Host": "localhost:8765"}


def fake_jpeg(w=640, h=360, fill=b"x"):
    """JPEG mínimo con cabecera SOF0 (el servidor no lo decodifica)."""
    sof = (b"\xff\xc0\x00\x11\x08" + h.to_bytes(2, "big") + w.to_bytes(2, "big")
           + b"\x03\x01\x22\x00\x02\x11\x01\x03\x11\x01")
    return b"\xff\xd8" + sof + fill * 64 + b"\xff\xd9"


@pytest.fixture(autouse=True)
def reset_hub(monkeypatch):
    monkeypatch.setattr(phonecam, "hub", phonecam.Hub())
    monkeypatch.setattr(phonecam.vcam, "available", lambda: False)


@pytest.fixture
def phone():
    with TestClient(main.app, client=("192.168.1.60", 50000)) as c:
        yield c


@pytest.fixture
def pc():
    with TestClient(main.app, client=("127.0.0.1", 50000)) as c:
        yield c


def test_jpeg_size():
    assert phonecam.jpeg_size(fake_jpeg(1280, 720)) == (1280, 720)
    assert phonecam.jpeg_size(b"\xff\xd8nada") == (0, 0)


def test_publish_requires_pairing(phone):
    with pytest.raises(WebSocketDisconnect) as exc:
        with phone.websocket_connect("/phonecam/ws") as ws:
            ws.receive_bytes()
    assert exc.value.code == 4401


def test_rejects_non_jpeg(phone):
    with phone.websocket_connect("/phonecam/ws?token=test-token") as ws:
        ws.send_bytes(b"GIF89a esto no es un jpeg")
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_bytes()
    assert exc.value.code == 4400
    assert phonecam.hub.frame is None


def test_frames_reach_pc(phone, pc):
    frame = fake_jpeg(1280, 720)
    with phone.websocket_connect("/phonecam/ws?token=test-token") as ws:
        ws.send_bytes(frame)
        ws.send_text("ping")                 # latido: se ignora
        # que el servidor procese antes de consultar
        for _ in range(50):
            if phonecam.hub.frame:
                break
            import time
            time.sleep(0.02)
        st = pc.get("/api/phonecam/status", headers={"X-MiniDeck-Token": "test-token"}).json()
        assert st["live"] is True and st["width"] == 1280 and st["height"] == 720
        # desde el propio PC (OBS) sin token
        r = pc.get("/phonecam/snapshot.jpg", headers=LOCAL)
        assert r.status_code == 200 and r.content == frame
        assert pc.get("/phonecam/view", headers=LOCAL).status_code == 200


def test_remote_viewers_need_token(phone):
    phonecam.hub.frame = fake_jpeg()
    assert phone.get("/phonecam/snapshot.jpg").status_code == 403
    assert phone.get("/phonecam/stream.mjpg").status_code == 403
    assert phone.get("/phonecam/view").status_code == 403
    assert phone.get("/phonecam/snapshot.jpg?token=test-token").status_code == 200


def test_mjpeg_stream():
    """Un flujo MJPEG no termina nunca (el cliente de pruebas lo esperaría):
    se prueba el generador de partes directamente."""
    import asyncio

    async def scenario():
        frame = fake_jpeg()
        await phonecam.hub.publish(frame)

        async def connected():
            return False
        gen = phonecam.mjpeg_parts(connected)
        first = await gen.__anext__()
        viewers = phonecam.hub.viewers
        await gen.aclose()
        return first, frame, viewers, phonecam.hub.viewers

    first, frame, during, after = asyncio.run(scenario())
    assert first.startswith(b"--minideckframe")
    assert frame in first
    assert (during, after) == (1, 0)


def test_second_phone_takes_over(phone):
    with phone.websocket_connect("/phonecam/ws?token=test-token") as first:
        first.send_bytes(fake_jpeg())
        with phone.websocket_connect("/phonecam/ws?token=test-token") as second:
            second.send_bytes(fake_jpeg(fill=b"y"))
            with pytest.raises(WebSocketDisconnect) as exc:
                first.receive_bytes()
            assert exc.value.code == 4409
