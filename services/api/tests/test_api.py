from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Artifact, DocumentVersion, Report, SourceDocument
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
        listed = client.get("/api/threads")
        assert listed.status_code == 200
        assert listed.json()[0]["id"] == thread.json()["id"]
        messages = client.get(f"/api/threads/{thread.json()['id']}/messages")
        assert messages.status_code == 200
        assert messages.json() == []
        deleted = client.delete(f"/api/threads/{thread.json()['id']}")
        assert deleted.status_code == 204
        assert client.get(f"/api/threads/{thread.json()['id']}/messages").status_code == 404


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


def test_report_delete_removes_database_record_and_artifacts(tmp_path, monkeypatch):
    artifact_dir = tmp_path / "artifacts"
    report_dir = artifact_dir / "delete-report"
    report_dir.mkdir(parents=True)
    artifact_path = report_dir / "report.html"
    artifact_path.write_text("report", encoding="utf-8")
    monkeypatch.setattr("app.services.storage.get_settings", lambda: SimpleNamespace(data_dir=tmp_path))
    with TestClient(app) as client, SessionLocal() as db:
        report = Report(id="delete-report", title="Удалить", report_kind="financial", document_ids=[], status="completed")
        db.add(report)
        db.flush()
        db.add(Artifact(report_id=report.id, format="html", mime_type="text/html", storage_path=str(artifact_path), size_bytes=6, sha256="2" * 64))
        db.commit()

        report_id = report.id
        response = client.delete(f"/api/reports/{report_id}")
        assert response.status_code == 204
        db.expunge_all()
        assert db.get(Report, report_id) is None
        assert not report_dir.exists()


def test_report_can_be_rebuilt_in_place(monkeypatch):
    queued: list[tuple] = []
    monkeypatch.setattr("app.main.create_report_task.delay", lambda *args: queued.append(args))
    with TestClient(app) as client, SessionLocal() as db:
        report = Report(title="Динамика", report_kind="financial", document_ids=[], status="completed")
        db.add(report)
        db.commit()
        report_id = report.id

        response = client.post(f"/api/reports/{report_id}/rebuild")
        assert response.status_code == 200
        assert response.json()["status"] == "queued"
        assert queued[0][0] == report_id
        assert "динамику" in queued[0][1]


def test_pdf_document_is_listed_and_previewed_inline(tmp_path):
    pdf = tmp_path / "official-report.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    with TestClient(app) as client, SessionLocal() as db:
        document = SourceDocument(
            title="Официальная отчетность",
            document_type="annual_report",
            reporting_standard="IFRS",
            source_tier="official_bank",
            status="parsed",
        )
        db.add(document)
        db.flush()
        db.add(
            DocumentVersion(
                document_id=document.id,
                sha256="1" * 64,
                mime_type="application/pdf",
                size_bytes=pdf.stat().st_size,
                storage_path=str(pdf),
            )
        )
        db.commit()

        listed = client.get("/api/documents").json()
        item = next(item for item in listed if item["id"] == document.id)
        assert item["previewable"] is True
        assert item["mime_type"] == "application/pdf"

        response = client.get(f"/api/documents/{document.id}/preview")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
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
