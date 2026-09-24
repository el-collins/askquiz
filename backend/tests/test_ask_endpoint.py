import io

import pytest
from fastapi.testclient import TestClient

import app.main as main_module

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"fake-jpeg-payload"


@pytest.fixture
def client(monkeypatch):
    async def fake_create_pool(database_url):
        return object()

    monkeypatch.setattr(main_module, "create_pool", fake_create_pool)
    monkeypatch.setattr(main_module, "AsyncGroq", lambda **kwargs: object())

    async def default_check_and_increment(pool, device_id, cap, today):
        return True

    monkeypatch.setattr(main_module, "check_and_increment", default_check_and_increment)

    with TestClient(main_module.app) as c:
        yield c


def test_text_question_returns_answer(client, monkeypatch):
    async def fake_ask_text(groq_client, content):
        return "B. Queue"

    monkeypatch.setattr(main_module, "ask_text", fake_ask_text)

    response = client.post(
        "/ask",
        data={"type": "text", "content": "Which data structure uses FIFO?"},
        headers={"X-Device-Id": "device-1"},
    )

    assert response.status_code == 200
    assert response.json() == {"answer": "B. Queue"}


def test_text_missing_content_returns_400(client):
    response = client.post(
        "/ask", data={"type": "text"}, headers={"X-Device-Id": "device-1"}
    )
    assert response.status_code == 400


def test_text_blank_content_returns_400(client):
    response = client.post(
        "/ask",
        data={"type": "text", "content": "   "},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 400


def test_image_missing_file_returns_400(client):
    response = client.post(
        "/ask", data={"type": "image"}, headers={"X-Device-Id": "device-1"}
    )
    assert response.status_code == 400


def test_image_wrong_content_type_returns_400(client):
    response = client.post(
        "/ask",
        data={"type": "image"},
        files={"image": ("q.txt", io.BytesIO(b"not an image"), "text/plain")},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 400


def test_image_spoofed_content_type_returns_400(client):
    """A client that lies and labels non-image bytes as image/jpeg must not fool us."""
    response = client.post(
        "/ask",
        data={"type": "image"},
        files={"image": ("q.jpg", io.BytesIO(b"#!/bin/sh not an image"), "image/jpeg")},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 400


def test_image_mislabeled_but_real_jpeg_is_accepted(client, monkeypatch):
    """React Native/Expo often sends image/jpg; real JPEG bytes must not be rejected for it."""

    async def fake_ask_image(groq_client, image_bytes, mime_type):
        assert mime_type == "image/jpeg"
        return "B. Paris"

    monkeypatch.setattr(main_module, "ask_image", fake_ask_image)

    response = client.post(
        "/ask",
        data={"type": "image"},
        files={"image": ("q.jpg", io.BytesIO(JPEG_BYTES), "image/jpg")},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 200
    assert response.json() == {"answer": "B. Paris"}


def test_image_question_returns_answer(client, monkeypatch):
    async def fake_ask_image(groq_client, image_bytes, mime_type):
        return "B. Queue"

    monkeypatch.setattr(main_module, "ask_image", fake_ask_image)

    response = client.post(
        "/ask",
        data={"type": "image"},
        files={"image": ("q.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 200
    assert response.json() == {"answer": "B. Queue"}


def test_image_groq_failure_returns_502(client, monkeypatch):
    from app.groq_client import GroqAnswerError

    async def failing_ask_image(groq_client, image_bytes, mime_type):
        raise GroqAnswerError("boom")

    monkeypatch.setattr(main_module, "ask_image", failing_ask_image)

    response = client.post(
        "/ask",
        data={"type": "image"},
        files={"image": ("q.jpg", io.BytesIO(JPEG_BYTES), "image/jpeg")},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 502


def test_image_too_large_returns_413(client, monkeypatch):
    monkeypatch.setattr(main_module, "MAX_IMAGE_BYTES", 10)
    response = client.post(
        "/ask",
        data={"type": "image"},
        files={"image": ("q.jpg", io.BytesIO(b"x" * 100), "image/jpeg")},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 413


def test_image_too_large_does_not_consume_rate_limit(client, monkeypatch):
    monkeypatch.setattr(main_module, "MAX_IMAGE_BYTES", 10)

    calls = []

    async def tracking_check_and_increment(pool, device_id, cap, today):
        calls.append(device_id)
        return True

    monkeypatch.setattr(main_module, "check_and_increment", tracking_check_and_increment)

    response = client.post(
        "/ask",
        data={"type": "image"},
        files={"image": ("q.jpg", io.BytesIO(b"x" * 100), "image/jpeg")},
        headers={"X-Device-Id": "device-1"},
    )

    assert response.status_code == 413
    assert calls == []


def test_missing_device_id_header_returns_400(client):
    response = client.post("/ask", data={"type": "text", "content": "hi"})
    assert response.status_code == 400


def test_rate_limit_exceeded_returns_429(client, monkeypatch):
    async def deny(pool, device_id, cap, today):
        return False

    monkeypatch.setattr(main_module, "check_and_increment", deny)

    response = client.post(
        "/ask",
        data={"type": "text", "content": "hi"},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 429


def test_groq_failure_returns_502(client, monkeypatch):
    from app.groq_client import GroqAnswerError

    async def failing_ask_text(groq_client, content):
        raise GroqAnswerError("boom")

    monkeypatch.setattr(main_module, "ask_text", failing_ask_text)

    response = client.post(
        "/ask",
        data={"type": "text", "content": "hi"},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 502


def test_image_field_sent_as_plain_string_returns_400_not_500(client):
    """Reproduces a real production crash: a non-file "image" form field
    trips Pydantic's UploadFile validation, and its ctx.error carries a raw
    ValueError, which the old handler tried to json.dumps directly and
    crashed with a 500 instead of returning the intended 400."""
    response = client.post(
        "/ask",
        data={"type": "image", "image": "not-a-file"},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 400
    assert response.json()["detail"]
