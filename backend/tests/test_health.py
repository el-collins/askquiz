from fastapi.testclient import TestClient

import app.main as main_module


def test_health_returns_ok(monkeypatch):
    async def fake_create_pool(database_url):
        return object()

    monkeypatch.setattr(main_module, "create_pool", fake_create_pool)
    monkeypatch.setattr(main_module, "Groq", lambda **kwargs: object())

    with TestClient(main_module.app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
