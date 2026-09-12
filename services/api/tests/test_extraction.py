from pathlib import Path
import zipfile

import openpyxl
import pytest

from app.config import get_settings
from app.services.extraction import Extractor


def test_csv_extraction(tmp_path: Path):
    path = tmp_path / "facts.csv"
    path.write_text("Показатель;Значение\nЧистая прибыль;1 200,5\n", encoding="utf-8")
    result = Extractor().extract(path)
    assert "Чистая прибыль" in result.text
    assert result.candidates[0].cell_range == "B2"


def test_xlsx_preserves_cell_coordinate(tmp_path: Path):
    path = tmp_path / "facts.xlsx"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "МСФО"
    sheet.append(["Активы", 500])
    workbook.save(path)
    result = Extractor().extract(path)
    assert result.candidates[0].sheet == "МСФО"
    assert result.candidates[0].cell_range == "B1"


def test_cbr_xml_is_preserved_as_table(tmp_path: Path):
    path = tmp_path / "form101.xml"
    path.write_text("<root><row><Name>Активы</Name><Amount>1250.50</Amount></row></root>", encoding="utf-8")
    result = Extractor().extract(path)
    assert "Активы" in result.text
    assert result.candidates[0].value == "1250.50"
    assert result.candidates[0].cell_range.startswith("XML:")


def test_zip_bomb_limit_uses_uncompressed_size(tmp_path: Path):
    path = tmp_path / "oversized.zip"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("large.csv", b"0" * (1024 * 1024 + 1))
    settings = get_settings()
    original = settings.max_archive_mb
    settings.max_archive_mb = 1
    try:
        with pytest.raises(ValueError, match="безопасный лимит"):
            Extractor().extract(path)
    finally:
        settings.max_archive_mb = original
