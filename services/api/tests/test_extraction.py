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


def test_bank_statement_candidates_keep_period_and_scale():
    text = """Обобщенный консолидированный отчет о финансовом положении
в миллионах российских рублей
2025
2024
Всего активов
4 873 717
5 008 951
Кредиты клиентам
12
2 352 372
2 697 626
Всего капитала
371 906
349 301
"""
    result = Extractor()._financial_statement_candidates(text, page=7)
    assets = [item for item in result if item.label == "Всего активов"]
    loans = [item for item in result if item.label == "Кредиты клиентам"]
    assert [(item.value, item.period_end) for item in assets] == [
        ("4 873 717", "2025-12-31"),
        ("5 008 951", "2024-12-31"),
    ]
    assert loans[0].value == "2 352 372"
    assert all(item.unit_scale == 1_000_000 for item in assets + loans)


def test_trillion_values_fit_database_scale():
    result = Extractor()._financial_statement_candidates(
        "Пресс-релиз за 2025 год\nтрлн ₽\nСовокупные активы\n4,9", page=1
    )
    assert result[0].value == "4900.0"
    assert result[0].unit_scale == 1_000_000_000
    assert result[0].period_end == "2025-12-31"


def test_pdf_table_candidates_keep_year_columns_and_billions():
    rows = [
        ["в млрд руб.", "", "2025 г.", "2024 г."],
        ["Чистая прибыль", "", "22,6", "20,9"],
        ["Операционные расходы", "", "(35,6)", "(41,5)"],
    ]
    result = Extractor()._pdf_table_candidates(
        rows,
        "Пресс-релиз МСФО за 2025 год\n2025 г.\n2024 г.\nв млрд руб., если не указано иное",
        page=1,
    )
    profit = [item for item in result if item.label == "Чистая прибыль"]
    assert [(item.value, item.period_end) for item in profit] == [
        ("22,6", "2025-12-31"),
        ("20,9", "2024-12-31"),
    ]
    assert all(item.unit_scale == 1_000_000_000 for item in profit)
