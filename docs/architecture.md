# Архитектура Bank Reporter

Интерактивная схема, собранная [Archify](https://github.com/tt-a1i/archify): [открыть HTML](bank-reporter.architecture.html). Типизированный исходник: [JSON](bank-reporter.architecture.json). HTML автономен и не требует работающего Bank Reporter. Archify используется только как инструмент документации и не входит в runtime Bank Reporter.

## Варианты развертывания

Основная Compose-редакция использует PostgreSQL, Redis, Celery и отдельные контейнеры. Desktop-редакция macOS сохраняет те же API, агентские skills и правила provenance, но запускает Next.js, FastAPI и browser-worker как локальные sidecar-процессы. Метаданные хранятся в SQLite, а фоновые операции выполняет встроенная очередь и планировщик. Подробности: [Desktop для macOS](macos-desktop.md).

## Контейнеры

| Сервис | Технология | Ответственность | Доступ |
|---|---|---|---|
| `web` | Next.js 16, React 19, TypeScript | интерфейс, server-side proxy к API | `127.0.0.1:3000` |
| `api` | FastAPI, Python 3.12 | REST/SSE, валидация, бизнес-операции | только Compose network |
| `worker` | Celery | агентские запуски, извлечение, отчёты | только очередь |
| `scheduler` | Celery Beat | календарь, watchlist, Telegram | только очередь |
| `browser` | Node.js 24, Chromium, agent-browser 0.37.1 | безопасная навигация, чтение, download, PDF/PNG | только Compose network |
| `postgres` | PostgreSQL 16 | метаданные, чаты, факты, provenance, аудит | только Compose network |
| `redis` | Redis 7 | broker, result backend, блокировки и прогресс | только Compose network |

`api`, `worker` и `scheduler` используют один backend image. Оригиналы и артефакты лежат в общем volume `/data`.

## Поток агентского запроса

1. Web создаёт thread/message через REST.
2. API создаёт `AnalysisRun`, публикует Celery-задачу в Redis и сразу возвращает `run_id`.
3. Web подключается к `/api/runs/{id}/events`; API отдаёт накопленные и новые события SSE.
4. Worker выбирает workflow и передаёт оркестрацию DeepSeek.
5. Модель может вызывать только инструменты из типизированного registry; каждый вызов ограничен схемой и правами manifest.
6. Инструменты ищут, скачивают, извлекают и запрашивают факты. Сетевой контент всегда считается данными, а не инструкциями.
7. События `citation`, `artifact_ready`, `failed` или `completed` сохраняются в БД и видны в потоке.

Лимиты одного запуска по умолчанию: 12 шагов, 25 web-страниц и 15 минут. Запуск можно отменить API или из интерфейса.

## Поток документа

```text
URL/upload → SSRF/MIME/size checks → immutable version in /data
           → extractor/OCR → normalized Decimal facts → ProvenanceRef
           → deterministic calculations → model interpretation → report artifacts
```

Извлечение:

- PDF: PyMuPDF и pdfplumber, OCR Tesseract `rus+eng` при слабом текстовом слое;
- XLSX: openpyxl/Polars с листом и координатами;
- CSV/DBF: определение кодировки, разделителя и масштаба;
- ZIP: ограниченная безопасная распаковка и обработка разрешённых вложений;
- HTML: заголовок, автор, дата, основное содержимое и подтверждающие фрагменты.

## Источники и доверие

Порядок для цифр: официальный сайт банка → Банк России → Минфин → профессиональные/рейтинговые обзоры → прочий открытый веб. Вторичные источники могут заполнить частичную таблицу, когда оригинал недоступен, но получают соответствующую маркировку доверия.

Сайты сначала читаются прямым HTTP. Browser-worker используется для динамических страниц, поиска и рендера. Разрешены навигация, чтение, поисковые формы и скачивание; запрещены login, платежи, внешняя загрузка файлов, изменение данных и remote eval.

## Модели

- `deepseek/deepseek-v4.1-flash` — выбор workflow, tool calls и общий ответ;
- `inclusionai/ling-3.0-flash-fin` — финансовая интерпретация и выбор визуализации;
- DeepSeek — fallback финансового шага.

Модель не является источником чисел. Формулы и сравнения считаются детерминированно. Для каждой попытки сохраняются модель, длительность, токены и ошибки, но не скрытые рассуждения.

## Хранилище данных

Основные таблицы PostgreSQL:

- `threads`, `messages`, `analysis_runs`, `run_events`;
- `model_runs`, `tool_runs`;
- `banks`, `watchlist_entries`, `integration_state`;
- `source_documents`, `document_versions`, `provenance_refs`;
- `financial_facts`, `calendar_events`;
- `reports`, `artifacts`.

Файловый volume:

- `/data/documents/{document_id}/{version_id}` — оригиналы и извлечённые материалы;
- `/data/artifacts/{report_id}` — HTML/PDF/PNG/XLSX/CSV.

Удаление всегда адресное. Новая версия URL не перезаписывает предыдущую. Redis не является системой долговременного хранения.

## Skills, workflows и MCP

`services/api/app/skills` содержит контракты, registry, каталог и workflow registry. Workflow — валидируемый DAG из skills. Локальные расчёты и storage остаются in-process; service skills обращаются к внутренним сервисам. MCP предусмотрен как транспортная граница через `MCPBinding`/`MCPInvoker`, но готовый внешний MCP server в текущий Compose не включён. Подробности: [skills-and-workflows.md](skills-and-workflows.md).

## Формирование отчёта

R04 используется для анализа одного банка/периода, R09 — для сравнения и динамики, R11 — для короткой справки. Шаблоны Lieflat подключены на закреплённом commit. Модель возвращает структурированные данные и выбор вида; произвольный JavaScript модели не исполняется. HTML проходит проверку на демоданные, внешние скрипты и числа без provenance, после чего browser-worker экспортирует PDF/PNG.

## Границы развёртывания

По умолчанию только web опубликован на loopback. API и БД наружу не выставляются. На сервере сохраняется та же граница, а пользователь подключается через SSH-туннель. Публичный reverse proxy допустим только после добавления аутентификации, HTTPS, rate limiting и политики резервного копирования.

## Ограничения архитектуры MVP

- один доверенный локальный пользователь, без tenant isolation;
- SQLAlchemy `create_all` вместо версионированных миграций;
- локальные Docker volumes вместо S3/object storage;
- один Celery queue и общий worker для OCR/agent/report jobs;
- нет внешней телеметрии и централизованного мониторинга;
- устойчивость к падению отдельного источника есть, high availability нет.
