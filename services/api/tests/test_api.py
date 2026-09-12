from fastapi.testclient import TestClient

from app.main import app
from app.services.cbr import CBRConnector


def test_health_and_thread():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["openrouter_configured"] is False
        config = client.get("/api/settings/status")
        assert config.status_code == 200
        assert config.json()["openrouter_key_present"] is False
        thread = client.post("/api/threads", json={"title": "Тест"})
        assert thread.status_code == 200
        assert thread.json()["title"] == "Тест"


def test_bank_search(monkeypatch):
    monkeypatch.setattr(CBRConnector, "_soap_search", lambda *_: [])
    with TestClient(app) as client:
        response = client.get("/api/banks/search", params={"q": "ВТБ"})
        assert response.status_code == 200
        assert response.json()[0]["cbr_reg_number"] == "1000"


def test_upload_csv():
    with TestClient(app) as client:
        response = client.post(
            "/api/documents/upload",
            files={"file": ("report.csv", "Показатель;Значение\nАктивы;1000\n", "text/csv")},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "parsed"
