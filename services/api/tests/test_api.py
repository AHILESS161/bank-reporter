from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Artifact, Report
from app.services.cbr import CBRConnector


def test_health_and_thread():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["openrouter_configured"] is False
        config = client.get("/api/settings/status")
        assert config.status_code == 200
        assert config.json()["model_key_present"] is False
        thread = client.post("/api/threads", json={"title": "Тест"})
        assert thread.status_code == 200
        assert thread.json()["title"] == "Тест"


def test_report_preview_is_inline_and_sandboxed(tmp_path):
    preview = tmp_path / "report.html"
    preview.write_text("<!doctype html><title>Preview</title>", encoding="utf-8")
    with TestClient(app) as client, SessionLocal() as db:
        report = Report(title="Preview", report_kind="financial", document_ids=[])
        db.add(report)
        db.flush()
        db.add(
            Artifact(
                report_id=report.id,
                format="html",
                mime_type="text/html",
                storage_path=str(preview),
                size_bytes=preview.stat().st_size,
                sha256="0" * 64,
            )
        )
        db.commit()
        response = client.get(f"/api/reports/{report.id}/preview")
        assert response.status_code == 200
        assert response.headers["content-disposition"] == "inline"
        assert "frame-ancestors 'self'" in response.headers["content-security-policy"]


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
