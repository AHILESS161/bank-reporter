import json

from app.services import gazprombank


def test_gazprombank_catalog_selects_requested_year_and_returns_attachments(monkeypatch):
    html = (
        '"label":"МСФО отчетность","value":341,"children":['
        '{"label":"2026","value":79789,"children":null},'
        '{"label":"2025","value":65989,"children":null}]}'
    )
    payload = {
        "data": [
            {
                "name": "Обобщенная консолидированная отчетность по МСФО за 2025 год",
                "src": "/upload/report.pdf",
                "createdAt": "2026.03.30 17:22:18",
                "attachments": [
                    {
                        "name": "Дополнительные материалы к МСФО за 2025 год",
                        "src": "/upload/analytics.xlsx",
                    }
                ],
            }
        ]
    }
    calls: list[list[str]] = []

    def fake_sequence(urls, **_kwargs):
        calls.append(urls)
        if len(urls) == 1:
            return [(urls[0], html.encode())]
        assert "sectionId=65989" in urls[-1]
        return [(urls[0], html.encode()), (urls[-1], json.dumps(payload).encode())]

    monkeypatch.setattr(gazprombank, "public_get_sequence", fake_sequence)
    result = gazprombank.discover_gazprombank_documents("МСФО", "2025 год")

    assert [item["url"] for item in result] == [
        "https://www.gazprombank.ru/upload/report.pdf",
        "https://www.gazprombank.ru/upload/analytics.xlsx",
    ]
    assert all(item["reporting_year"] == 2025 for item in result)
    assert len(calls) == 2


def test_gazprombank_catalog_returns_empty_for_unknown_year(monkeypatch):
    html = (
        '"label":"РСБУ отчетность","value":82471,"children":['
        '{"label":"2025","value":82475,"children":null}]}'
    )
    monkeypatch.setattr(
        gazprombank,
        "public_get_sequence",
        lambda urls, **_kwargs: [(urls[0], html.encode())],
    )

    assert gazprombank.discover_gazprombank_documents("РСБУ", "2023") == []
