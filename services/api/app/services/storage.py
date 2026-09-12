import shutil
import uuid
from pathlib import Path

from ..config import get_settings
from .security import safe_filename


class Storage:
    def __init__(self, root: Path | None = None):
        self.root = root or get_settings().data_dir

    def document_path(self, document_id: str, version_id: str, filename: str) -> Path:
        target = self.root / "documents" / document_id / version_id / safe_filename(filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def artifact_path(self, report_id: str, filename: str) -> Path:
        target = self.root / "artifacts" / report_id / safe_filename(filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    def temporary_path(self, suffix: str = "") -> Path:
        path = self.root / "tmp" / f"{uuid.uuid4()}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def remove_document(self, document_id: str) -> None:
        target = (self.root / "documents" / document_id).resolve()
        expected = (self.root / "documents").resolve()
        if target.parent != expected:
            raise ValueError("Некорректный путь документа")
        if target.exists():
            shutil.rmtree(target)
