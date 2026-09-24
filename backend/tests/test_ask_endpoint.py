import io

import pytest
from fastapi.testclient import TestClient

import app.main as main_module


@pytest.fixture
def client(monkeypatch):
    async def fake_create_pool(database_url):
        return object()

    monkeypatch.setattr(main_module, "create_pool", fake_create_pool)
    monkeypatch.setattr(main_module, "Groq", lambda **kwargs: object())

    async def default_check_and_increment(pool, device_id, cap, today):
        return True

    monkeypatch.setattr(main_module, "check_and_increment", default_check_and_increment)

    with TestClient(main_module.app) as c:
        yield c


def test_text_question_returns_answer(client, monkeypatch):
    monkeypatch.setattr(main_module, "ask_text", lambda groq_client, content: "B. Queue")

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


def test_image_too_large_returns_413(client, monkeypatch):
    monkeypatch.setattr(main_module, "MAX_IMAGE_BYTES", 10)
    response = client.post(
        "/ask",
        data={"type": "image"},
        files={"image": ("q.jpg", io.BytesIO(b"x" * 100), "image/jpeg")},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 413


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

    def failing_ask_text(groq_client, content):
        raise GroqAnswerError("boom")

    monkeypatch.setattr(main_module, "ask_text", failing_ask_text)

    response = client.post(
        "/ask",
        data={"type": "text", "content": "hi"},
        headers={"X-Device-Id": "device-1"},
    )
    assert response.status_code == 502
