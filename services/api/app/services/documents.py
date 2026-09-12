import mimetypes
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import DocumentVersion, FinancialFact, ProvenanceRef, SourceDocument
from .extraction import Extractor
from .financial import map_candidates
from .network import public_download
from .security import file_sha256, safe_filename
from .storage import Storage


ALLOWED_MIME = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/zip",
    "application/x-zip-compressed",
    "application/octet-stream",
    "application/vnd.dbf",
    "application/x-dbf",
    "application/xml",
    "text/xml",
}


class DocumentService:
    def __init__(self, db: Session):
        self.db = db
        self.storage = Storage()
        self.extractor = Extractor()

    def ingest_path(
        self,
        source: Path,
        title: str,
        source_url: str | None = None,
        source_tier: str = "user",
        bank_reg_number: str | None = None,
        document_type: str = "other",
        reporting_standard: str | None = None,
    ) -> SourceDocument:
        settings = get_settings()
        size = source.stat().st_size
        if size > settings.max_file_mb * 1024 * 1024:
            raise ValueError("Файл превышает лимит")
        mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
        if mime not in ALLOWED_MIME:
            raise ValueError(f"Запрещенный MIME: {mime}")
        digest = file_sha256(source)
        existing_version = self.db.scalar(select(DocumentVersion).where(DocumentVersion.sha256 == digest))
        if existing_version:
            return existing_version.document
        document = SourceDocument(
            title=title,
            source_url=source_url,
            source_tier=source_tier,
            bank_reg_number=bank_reg_number,
            document_type=document_type,
            reporting_standard=reporting_standard,
            status="processing",
        )
        self.db.add(document)
        self.db.flush()
        version = DocumentVersion(
            document_id=document.id, sha256=digest, mime_type=mime, size_bytes=size, storage_path=""
        )
        self.db.add(version)
        self.db.flush()
        target = self.storage.document_path(document.id, version.id, source.name)
        target.write_bytes(source.read_bytes())
        version.storage_path = str(target)
        try:
            result = self.extractor.extract(target)
            version.extracted_text = result.text[:5_000_000]
            version.parsed_data = result.json()
            self._store_facts(document, version, result.json().get("candidates", []))
            document.status = "parsed"
        except Exception as exc:
            version.parsed_data = {"warnings": [str(exc)]}
            document.status = "failed"
        self.db.commit()
        self.db.refresh(document)
        return document

    def download(self, url: str, **metadata) -> SourceDocument:
        temp = self.storage.temporary_path(Path(url.split("?", 1)[0]).suffix or ".bin")
        max_bytes = get_settings().max_file_mb * 1024 * 1024
        final_url = public_download(url, temp, timeout=60, max_bytes=max_bytes)
        return self.ingest_path(
            temp, metadata.pop("title", safe_filename(url)), source_url=final_url, **metadata
        )

    def _store_facts(
        self, document: SourceDocument, version: DocumentVersion, candidates: list[dict]
    ) -> None:
        for item in map_candidates(candidates):
            provenance = ProvenanceRef(
                document_version_id=version.id,
                source_url=document.source_url,
                page=item.location.get("page"),
                sheet=item.location.get("sheet"),
                cell_range=item.location.get("cell_range"),
                excerpt=f"{item.label}: {item.value}",
            )
            self.db.add(provenance)
            self.db.flush()
            self.db.add(
                FinancialFact(
                    document_version_id=version.id,
                    provenance_id=provenance.id,
                    bank_reg_number=document.bank_reg_number,
                    metric_code=item.metric_code,
                    label=item.label,
                    value=item.value,
                    confidence=item.confidence,
                    currency="RUB",
                )
            )
