# Разработка

## Структура репозитория

```text
apps/web/                 Next.js UI и API proxy
services/api/             FastAPI, Celery, агент, skills, extraction, reports
services/browser/         Node/Chromium/agent-browser и action policy
services/api/tests/       unit, fixture, contract и security tests
third_party/lieflat-charts/ закреплённый submodule шаблонов
scripts/                  macOS launcher и получение Lieflat
docs/                     пользовательская и техническая документация
docker-compose.yml        локальный runtime
```

## Стек

- Python 3.12, FastAPI, SQLAlchemy, Pydantic, Celery;
- PostgreSQL 16, Redis 7;
- Next.js 16, React 19, TypeScript;
- Node.js 24, Chromium, agent-browser 0.37.1;
- PyMuPDF, pdfplumber, Tesseract, openpyxl, Polars и DBF parser;
- Lieflat Charts на закреплённом commit.

## Запуск dev-стека

```bash
cp .env.example .env
git submodule update --init --recursive
docker compose up --build -d
docker compose logs -f api worker web
```

Код backend/web сейчас копируется в images при build; после изменения пересоберите соответствующий сервис.

## Тесты

Полный backend suite:

```bash
docker compose run --rm api pytest -q
```

Frontend production build:

```bash
docker compose build web
```

Проверка Compose:

```bash
docker compose config
docker compose ps
```

Покрываемые классы сценариев:

- банк/алиасы, периоды, единицы и Decimal;
- ЦБ, browser parsing и extraction fixtures;
- model routing, JSON validation и fallback;
- отчёты, professional context и provenance;
- SSRF, prompt injection, MIME, archive и action policy;
- skills/workflows, Telegram и API contracts.

## Изменение моделей данных

Таблицы описаны в `services/api/app/models.py`, и при старте вызывается SQLAlchemy `create_all`. Alembic пока отсутствует. Для несовместимого изменения:

1. сделайте дамп тестовой БД;
2. добавьте явный migration mechanism либо одноразовый проверяемый migration script;
3. проверьте upgrade на копии production данных;
4. опишите rollback;
5. не полагайтесь на `create_all` для изменения существующих колонок.

## Добавление источника

1. Создайте connector/service с timeout и ограничением размера.
2. Пропустите URL через общую SSRF-защиту и redirect validation.
3. Укажите trust tier и сохраняйте canonical URL/hash.
4. Добавьте fixtures, parser tests, failure и blocked-source cases.
5. Зарегистрируйте skill только если capability должна быть доступна агенту.

## Добавление метрики

- используйте `Decimal`, не `float`;
- храните исходное значение, currency, unit scale и период;
- привяжите к точному `ProvenanceRef`;
- реализуйте формулу как чистую Python-функцию;
- добавьте unit tests на ноль, отрицательные значения, разные масштабы и отсутствующий период;
- не поручайте модели арифметику.

## Добавление шаблона отчёта

1. Определите intent: профиль, динамика, сравнение или brief.
2. Добавьте детерминированный adapter в reporting/Lieflat layer.
3. Принимайте от модели только структурированные данные, подписи, выводы и refs.
4. Не исполняйте model-generated JS.
5. Проверьте offline HTML, CSP, отсутствие demo data и source coverage каждого числа.
6. Создайте golden tests для HTML и export PDF/PNG/XLSX/CSV.

## Добавление skill/workflow

Следуйте отдельному документу [skills-and-workflows.md](skills-and-workflows.md). Минимальный набор тестов: manifest schema, valid/invalid input, permissions, timeout, side effects, неизвестный skill, цикл и topological order.

## Код-стайл и готовность изменения

Перед commit:

```bash
docker compose run --rm api pytest -q
docker compose build web
git diff --check
```

Изменение готово, когда happy path и частичный failure path понятны пользователю, числа имеют provenance, секреты не логируются, API остаётся совместимым либо изменение описано, а документация обновлена.
