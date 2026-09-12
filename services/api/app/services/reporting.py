import csv
import html
from decimal import Decimal
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Artifact, DocumentVersion, FinancialFact, ProvenanceRef, Report, SourceDocument
from .browser import BrowserClient
from .financial import growth
from .lieflat import LIEFLAT_COMMIT, report_contract, rung_chart, select_chart
from .model_router import ModelRouter, ModelUnavailable
from .security import file_sha256
from .storage import Storage


class ReportService:
    def __init__(self, db: Session, analysis_run_id: str | None = None):
        self.db = db
        self.storage = Storage()
        self.models = ModelRouter(db, analysis_run_id)

    def create(self, report: Report, question: str, output_formats: list[str]) -> Report:
        report.status = "processing"
        self.db.commit()
        rows = self._facts(report.document_ids)
        try:
            narrative = self.models.finance_narrative(rows, question)
        except ModelUnavailable as exc:
            narrative = {
                "summary": "Финансовая интерпретация не сформирована.",
                "highlights": [],
                "risks": [str(exc)],
                "chart": {"template": "F1", "metric_codes": []},
            }
            report.status = "partial"
        report.summary = narrative["summary"]
        html_path = self.storage.artifact_path(report.id, "report.html")
        html_path.write_text(self._html(report, narrative, rows), encoding="utf-8")
        self._artifact(report, "html", "text/html", html_path)
        if "xlsx" in output_formats:
            xlsx = self.storage.artifact_path(report.id, "report.xlsx")
            self._xlsx(xlsx, narrative, rows, self._calculations(rows))
            self._artifact(
                report, "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", xlsx
            )
        if "csv" in output_formats:
            csv_path = self.storage.artifact_path(report.id, "facts.csv")
            self._csv(csv_path, rows)
            self._artifact(report, "csv", "text/csv", csv_path)
        if "pdf" in output_formats or "png" in output_formats:
            pdf = self.storage.artifact_path(report.id, "report.pdf") if "pdf" in output_formats else None
            png = self.storage.artifact_path(report.id, "report.png") if "png" in output_formats else None
            try:
                BrowserClient().render(str(html_path), str(pdf) if pdf else None, str(png) if png else None)
                if pdf and pdf.exists():
                    self._artifact(report, "pdf", "application/pdf", pdf)
                if png and png.exists():
                    self._artifact(report, "png", "image/png", png)
            except Exception:
                report.status = "partial"
        if report.status != "partial":
            report.status = "completed"
        self.db.commit()
        self.db.refresh(report)
        return report

    def _facts(self, document_ids: list[str]) -> list[dict]:
        statement = (
            select(FinancialFact, ProvenanceRef, SourceDocument)
            .join(ProvenanceRef, FinancialFact.provenance_id == ProvenanceRef.id)
            .join(DocumentVersion, FinancialFact.document_version_id == DocumentVersion.id)
            .join(SourceDocument, DocumentVersion.document_id == SourceDocument.id)
            .where(SourceDocument.id.in_(document_ids))
            .order_by(FinancialFact.period_end, FinancialFact.metric_code)
        )
        return [
            {
                "id": fact.id,
                "metric_code": fact.metric_code,
                "label": fact.label,
                "value": str(fact.value),
                "currency": fact.currency,
                "unit_scale": fact.unit_scale,
                "period_end": fact.period_end,
                "confidence": fact.confidence,
                "document": document.title,
                "source_url": provenance.source_url,
                "page": provenance.page,
                "sheet": provenance.sheet,
                "cell_range": provenance.cell_range,
            }
            for fact, provenance, document in self.db.execute(statement).all()
        ]

    def _html(self, report: Report, narrative: dict, facts: list[dict]) -> str:
        contract = report_contract(report.report_kind, self.models.settings.lieflat_dir)
        requested_chart = narrative.get("chart", {}).get("template", "F1")
        chart_id = select_chart(requested_chart, facts)
        chart = rung_chart(facts, chart_id)
        highlights = "".join(
            f'<li data-provenance="{html.escape(",".join(item.get("fact_ids", [])))}">'
            f"{html.escape(item.get('text', ''))}<sup>{', '.join(html.escape(x) for x in item.get('fact_ids', []))}</sup></li>"
            for item in narrative.get("highlights", [])
        )
        risks = "".join(f"<li>{html.escape(str(item))}</li>" for item in narrative.get("risks", []))
        sources = "".join(
            f'<li id="fact-{html.escape(str(item["id"]))}"><a href="{html.escape(str(item.get("source_url") or "#"))}">'
            f"{html.escape(item['document'])}</a> · {html.escape(str(item.get('page') or item.get('sheet') or item.get('cell_range') or 'источник'))} · факт {html.escape(str(item['id']))}</li>"
            for item in facts
        )
        width = "600px" if contract.report_id == "R11" else "1080px"
        return f'''<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{html.escape(report.title)}</title>
<!-- Lieflat source: {contract.source_file} @ {LIEFLAT_COMMIT}; candidates: {", ".join(contract.candidates)}; {html.escape(contract.selection_reason)} -->
<style>:root{{--bg:#F7F2EB;--ink:#081F5C;--muted:rgba(8,31,92,.60);--faint:rgba(8,31,92,.32);--grid:rgba(8,31,92,.16)}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:Arial,sans-serif;display:flex;justify-content:center;padding:40px 20px;font-variant-numeric:tabular-nums}}.sheet{{width:{width};max-width:100%;display:grid;grid-template-columns:92px 1fr}}.spine{{border-right:1px solid var(--ink);position:relative}}.spine b{{display:block;writing-mode:vertical-rl;font-size:34px;letter-spacing:.05em;padding:12px}}.content{{padding-left:36px}}header{{border-bottom:1px solid var(--ink);padding-bottom:22px}}.eyebrow,h2{{font-size:10px;letter-spacing:.15em;text-transform:uppercase}}h1{{font-size:44px;line-height:1;letter-spacing:-.04em}}.lead{{font-size:18px;line-height:1.45}}section{{margin-top:36px}}.grid{{display:grid;grid-template-columns:minmax(0,2fr) minmax(220px,1fr);gap:34px}}li{{margin:10px 0;line-height:1.45}}sup{{font-size:7px;color:var(--muted)}}a{{color:var(--ink)}}footer{{border-top:1px solid var(--ink);margin-top:42px;padding-top:12px;color:var(--muted);font-size:9px;letter-spacing:.07em}}@media(max-width:720px){{.sheet{{display:block}}.spine{{display:none}}.content{{padding:0}}.grid{{display:block}}}}@media print{{body{{padding:0}}}}</style></head>
<body><main class="sheet" data-lieflat-report="{contract.report_id}" data-lieflat-chart="{chart_id}" data-lieflat-commit="{LIEFLAT_COMMIT}"><div class="spine"><b>{html.escape(report.title)}</b></div><div class="content"><header><p class="eyebrow">BANK REPORTER · {contract.report_id} · ПРОВЕРЯЕМЫЙ АНАЛИЗ</p><h1>{html.escape(report.title)}</h1><p class="lead">{html.escape(narrative["summary"])}</p></header><div class="grid"><section><h2>Показатели</h2>{chart if facts else "<p>Нормализованные показатели не найдены.</p>"}</section><aside><section><h2>Основные выводы</h2><ol>{highlights or "<li>Требуется ручная проверка извлечения.</li>"}</ol></section><section><h2>Ограничения</h2><ul>{risks}</ul></section></aside></div><section><h2>Источники и координаты</h2><ol>{sources or "<li>Источники не привязаны.</li>"}</ol></section><footer>Не является инвестиционной рекомендацией. Каждое число связано с ProvenanceRef. Lieflat Charts · PolyForm Noncommercial 1.0.0.</footer></div></main></body></html>'''

    @staticmethod
    def _xlsx(path: Path, narrative: dict, facts: list[dict], calculations: list[dict]) -> None:
        workbook = Workbook()
        summary = workbook.active
        summary.title = "Выводы"
        summary.append(["Резюме", narrative.get("summary")])
        summary.append([])
        for item in narrative.get("highlights", []):
            summary.append([item.get("text"), ",".join(item.get("fact_ids", []))])
        facts_sheet = workbook.create_sheet("Факты")
        facts_sheet.append(
            ["ID", "Показатель", "Название", "Значение", "Валюта", "Масштаб", "Период", "Уверенность"]
        )
        for item in facts:
            facts_sheet.append(
                [
                    item["id"],
                    item["metric_code"],
                    item["label"],
                    item["value"],
                    item["currency"],
                    item["unit_scale"],
                    str(item["period_end"] or ""),
                    item["confidence"],
                ]
            )
        calculation_sheet = workbook.create_sheet("Расчеты")
        calculation_sheet.append(
            ["Показатель", "Предыдущий период", "Текущий период", "Изменение, %", "Fact IDs"]
        )
        for item in calculations:
            calculation_sheet.append(
                [
                    item["metric_code"],
                    item["previous_period"],
                    item["current_period"],
                    item["growth_percent"],
                    ",".join(item["fact_ids"]),
                ]
            )
        sources = workbook.create_sheet("Источники")
        sources.append(["Документ", "URL", "Страница", "Лист", "Ячейка"])
        for item in facts:
            sources.append(
                [item["document"], item["source_url"], item["page"], item["sheet"], item["cell_range"]]
            )
        workbook.save(path)

    @staticmethod
    def _calculations(facts: list[dict]) -> list[dict]:
        grouped: dict[str, list[dict]] = {}
        for item in facts:
            if item.get("period_end"):
                grouped.setdefault(str(item["metric_code"]), []).append(item)
        output: list[dict] = []
        for metric_code, items in grouped.items():
            ordered = sorted(items, key=lambda item: item["period_end"])
            for previous, current in zip(ordered, ordered[1:], strict=False):
                change = growth(Decimal(str(current["value"])), Decimal(str(previous["value"])))
                output.append(
                    {
                        "metric_code": metric_code,
                        "previous_period": str(previous["period_end"]),
                        "current_period": str(current["period_end"]),
                        "growth_percent": str(change) if change is not None else "n/a",
                        "fact_ids": [str(previous["id"]), str(current["id"])],
                    }
                )
        return output

    @staticmethod
    def _csv(path: Path, facts: list[dict]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=list(facts[0].keys()) if facts else ["metric_code", "value"]
            )
            writer.writeheader()
            writer.writerows(facts)

    def _artifact(self, report: Report, fmt: str, mime: str, path: Path) -> None:
        self.db.add(
            Artifact(
                report_id=report.id,
                format=fmt,
                mime_type=mime,
                storage_path=str(path),
                size_bytes=path.stat().st_size,
                sha256=file_sha256(path),
            )
        )
        self.db.flush()
