import csv
import io
import re
import zipfile
from xml.etree import ElementTree
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import fitz
import openpyxl
import pdfplumber
import pytesseract
from charset_normalizer import from_bytes
from dbfread import DBF
from PIL import Image

from ..config import get_settings


@dataclass
class CellFact:
    label: str
    value: str
    page: int | None = None
    sheet: str | None = None
    cell_range: str | None = None


@dataclass
class ExtractionResult:
    text: str = ""
    tables: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[CellFact] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def json(self) -> dict[str, Any]:
        return {
            "tables": self.tables,
            "candidates": [asdict(item) for item in self.candidates],
            "warnings": self.warnings,
        }


class Extractor:
    allowed = {".pdf", ".xlsx", ".csv", ".dbf", ".zip", ".xml"}

    def extract(self, path: Path) -> ExtractionResult:
        suffix = path.suffix.lower()
        if suffix not in self.allowed:
            raise ValueError(f"Неподдерживаемый формат: {suffix}")
        return {
            ".pdf": self._pdf,
            ".xlsx": self._xlsx,
            ".csv": self._csv,
            ".dbf": self._dbf,
            ".zip": self._zip,
            ".xml": self._xml,
        }[suffix](path)

    def _pdf(self, path: Path) -> ExtractionResult:
        result = ExtractionResult()
        doc = fitz.open(path)
        pages: list[str] = []
        for number, page in enumerate(doc, start=1):
            text = page.get_text("text").strip()
            if len(text) < 30:
                pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
                image = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(image, lang="rus+eng").strip()
                result.warnings.append(f"OCR использован для страницы {number}")
            pages.append(f"\n--- PAGE {number} ---\n{text}")
            result.candidates.extend(self._text_candidates(text, page=number))
        result.text = "".join(pages)
        try:
            with pdfplumber.open(path) as pdf:
                for number, page in enumerate(pdf.pages, start=1):
                    for index, table in enumerate(page.extract_tables() or []):
                        rows = [[str(cell or "").strip() for cell in row] for row in table]
                        result.tables.append(
                            {"name": f"page_{number}_table_{index + 1}", "page": number, "rows": rows}
                        )
                        for row in rows:
                            if len(row) < 2 or not row[0]:
                                continue
                            for value in row[1:]:
                                if self._decimal(value) is not None:
                                    result.candidates.append(CellFact(row[0], value, page=number))
        except Exception as exc:  # table extraction is best-effort
            result.warnings.append(f"Таблицы PDF не извлечены: {exc}")
        return result

    def _xlsx(self, path: Path) -> ExtractionResult:
        result = ExtractionResult()
        workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
        chunks: list[str] = []
        for sheet in workbook.worksheets:
            rows: list[list[str]] = []
            for row_number, row in enumerate(sheet.iter_rows(values_only=True), start=1):
                values = ["" if value is None else str(value) for value in row]
                if any(values):
                    rows.append(values)
                    chunks.append(" | ".join(values))
                    for col, value in enumerate(values[1:], start=2):
                        if self._decimal(value) is not None and values[0]:
                            result.candidates.append(
                                CellFact(
                                    values[0],
                                    value,
                                    sheet=sheet.title,
                                    cell_range=f"{openpyxl.utils.get_column_letter(col)}{row_number}",
                                )
                            )
            result.tables.append({"name": sheet.title, "sheet": sheet.title, "rows": rows[:10_000]})
        result.text = "\n".join(chunks)
        return result

    def _csv(self, path: Path) -> ExtractionResult:
        raw = path.read_bytes()
        match = from_bytes(raw).best()
        text = str(match) if match else raw.decode("utf-8", errors="replace")
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;\t|")
        rows = list(csv.reader(io.StringIO(text), dialect))
        result = ExtractionResult(text=text, tables=[{"name": path.stem, "rows": rows[:50_000]}])
        for number, row in enumerate(rows, start=1):
            if len(row) >= 2 and self._decimal(row[1]) is not None:
                result.candidates.append(CellFact(row[0], row[1], sheet=path.name, cell_range=f"B{number}"))
        return result

    def _dbf(self, path: Path) -> ExtractionResult:
        table = DBF(path, load=True, char_decode_errors="replace")
        rows = [[str(record.get(name, "")) for name in table.field_names] for record in table]
        return ExtractionResult(
            text="\n".join(" | ".join(row) for row in rows),
            tables=[{"name": path.stem, "headers": table.field_names, "rows": rows}],
        )

    def _zip(self, path: Path) -> ExtractionResult:
        settings = get_settings()
        result = ExtractionResult()
        with zipfile.ZipFile(path) as archive:
            total = sum(item.file_size for item in archive.infolist())
            if total > settings.max_archive_mb * 1024 * 1024 or len(archive.infolist()) > 10_000:
                raise ValueError("Архив превышает безопасный лимит")
            for member in archive.infolist():
                member_name = Path(member.filename)
                if member.is_dir() or member_name.is_absolute() or ".." in member_name.parts:
                    continue
                if member_name.suffix.lower() not in self.allowed - {".zip"}:
                    continue
                target = get_settings().data_dir / "tmp" / f"extract-{path.stem}" / member_name.name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    output.write(source.read())
                nested = self.extract(target)
                result.text += nested.text
                result.tables.extend(nested.tables)
                result.candidates.extend(nested.candidates)
                result.warnings.extend(nested.warnings)
        return result

    def _xml(self, path: Path) -> ExtractionResult:
        root = ElementTree.fromstring(path.read_bytes())
        rows: list[list[str]] = []
        candidates: list[CellFact] = []
        for row_number, node in enumerate(root.iter(), start=1):
            children = list(node)
            if not children:
                continue
            values = {child.tag.rsplit("}", 1)[-1]: (child.text or "").strip() for child in children}
            if not any(values.values()):
                continue
            rows.append([f"{key}={value}" for key, value in values.items()])
            label = next(
                (value for key, value in values.items() if "name" in key.casefold() and value),
                node.tag.rsplit("}", 1)[-1],
            )
            for key, value in values.items():
                if self._decimal(value) is not None:
                    candidates.append(
                        CellFact(f"{label} {key}", value, sheet=path.name, cell_range=f"XML:{row_number}")
                    )
        text = "\n".join(" | ".join(row) for row in rows)
        return ExtractionResult(
            text=text,
            tables=[{"name": path.stem, "rows": rows[:50_000]}],
            candidates=candidates[:10_000],
        )

    def _text_candidates(self, text: str, page: int) -> list[CellFact]:
        candidates: list[CellFact] = []
        pattern = re.compile(r"^(.{3,100}?)\s+([()\-−]?\d[\d\s.,]*\)?)\s*$")
        for line in text.splitlines():
            match = pattern.match(line.strip())
            if match and self._decimal(match.group(2)) is not None:
                candidates.append(CellFact(match.group(1).strip(" ."), match.group(2), page=page))
        return candidates[:2000]

    @staticmethod
    def _decimal(value: str) -> Decimal | None:
        cleaned = value.strip().replace("\u00a0", "").replace(" ", "").replace("−", "-")
        negative = cleaned.startswith("(") and cleaned.endswith(")")
        cleaned = cleaned.strip("()").replace(",", ".")
        if cleaned.count(".") > 1:
            cleaned = cleaned.replace(".", "", cleaned.count(".") - 1)
        try:
            number = Decimal(cleaned)
            return -number if negative else number
        except InvalidOperation:
            return None
