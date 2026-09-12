# REST и SSE API

API доступен web-клиенту через same-origin proxy на `http://localhost:3000/api/...`. Внутри Compose FastAPI слушает `api:8000`. Интерактивная спецификация: <http://localhost:3000/api/docs>, OpenAPI JSON: <http://localhost:3000/api/openapi.json>.

## Общие правила

- JSON кодируется UTF-8, время — ISO 8601;
- идентификаторы — строки UUID;
- фоновые операции возвращают `run_id`, `report` или `task_id` до окончания работы;
- для сообщений и отчётов используйте `Idempotency-Key`; discover принимает `idempotency_key` в JSON;
- `404` — объект не найден, `409` — конфликт состояния, `413` — превышен размер, `415` — тип не поддержан, `422` — ошибка валидации/разбора, `503` — очередь недоступна.

## Чаты и запуски

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/threads` | создать чат |
| `GET` | `/api/threads` | последние 100 чатов |
| `DELETE` | `/api/threads/{id}` | удалить неактивный чат |
| `GET` | `/api/threads/{id}/messages` | история сообщений |
| `POST` | `/api/threads/{id}/messages` | отправить сообщение и создать run |
| `GET` | `/api/runs/{id}/events` | поток событий SSE |
| `POST` | `/api/runs/{id}/cancel` | запросить отмену |

```bash
curl -X POST http://localhost:3000/api/threads \
  -H 'Content-Type: application/json' \
  -d '{"title":"МСФО МКБ 2025"}'
```

```bash
curl -X POST http://localhost:3000/api/threads/THREAD_ID/messages \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: mkb-2025-001' \
  -d '{"content":"Найди МСФО МКБ за 2025 год"}'
```

Ответ: `{"run_id":"..."}`.

SSE каждую секунду отдаёт строки `data: {json}`. Типы событий: `status`, `tool_started`, `tool_completed`, `citation`, `artifact_ready`, `token`, `failed`, `completed`. Поток закрывается после `completed`, `partial`, `cancelled` или `failed`.

```bash
curl -N http://localhost:3000/api/runs/RUN_ID/events
```

## Банки и watchlist

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/api/banks/search?q=мкб` | разрешить название через ЦБ |
| `GET` | `/api/watchlist` | список наблюдения |
| `PUT` | `/api/watchlist/{cbr_reg_number}` | включить мониторинг |
| `DELETE` | `/api/watchlist/{cbr_reg_number}` | прекратить мониторинг |

Если банк ещё не искался, `PUT` требует `{"bank_name":"..."}`. Предпочтительно сначала вызвать поиск и использовать точный регистрационный номер.

## Документы

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/api/documents` | последние 200 документов |
| `POST` | `/api/documents/upload` | multipart upload PDF/XLSX/CSV/DBF/ZIP |
| `POST` | `/api/documents/discover` | фоновый поиск отчётности |
| `GET` | `/api/documents/{id}` | карточка документа |
| `GET` | `/api/documents/{id}/preview` | inline-предпросмотр PDF |
| `GET` | `/api/documents/{id}/download` | оригинал |
| `DELETE` | `/api/documents/{id}` | запись, версии и локальные файлы |

```bash
curl -X POST http://localhost:3000/api/documents/discover \
  -H 'Content-Type: application/json' \
  -d '{"bank_query":"МКБ","document_type":"МСФО","period":"2025","idempotency_key":"discover-mkb-2025"}'
```

```bash
curl -X POST http://localhost:3000/api/documents/upload \
  -F 'file=@report.pdf'
```

## Статьи

`POST /api/articles/search`:

```json
{
  "query": "качество кредитного портфеля",
  "bank": "ВТБ",
  "date_from": "2026-01-01",
  "date_to": "2026-06-30",
  "domains": ["cbr.ru", "interfax.ru"],
  "limit": 20
}
```

Ответ содержит `title`, `url`, `source`, `published_at`, `author`, `language`, `excerpt`, `trust_tier` и `score`.

## Календарь

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/api/calendar?from=&to=&bank=&type=&status=` | события до 1000 записей |
| `GET` | `/api/calendar.ics` | полный ICS-файл |
| `POST` | `/api/calendar/sync` | поставить ручную синхронизацию в очередь |

Параметры `from` и `to` — ISO datetime, `bank` — регистрационный номер ЦБ.

## Отчёты и артефакты

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/reports` | создать аналитический отчёт |
| `GET` | `/api/reports` | последние 200 отчётов |
| `GET` | `/api/reports/{id}` | состояние и артефакты |
| `POST` | `/api/reports/{id}/rebuild` | пересобрать завершённый отчёт |
| `DELETE` | `/api/reports/{id}` | удалить отчёт и артефакты |
| `GET` | `/api/reports/{id}/preview` | inline HTML с жёстким CSP |
| `GET` | `/api/artifacts/{id}/download` | скачать артефакт |

```bash
curl -X POST http://localhost:3000/api/reports \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: report-mkb-2025-v1' \
  -d '{
    "title":"МКБ: динамика прибыли",
    "document_ids":["DOCUMENT_ID"],
    "report_kind":"comparison",
    "question":"Сравни 2025 и 2024 годы",
    "output_formats":["html","pdf","png","xlsx","csv"]
  }'
```

`report_kind`: `financial`, `comparison` или `brief`. `document_ids` не может быть пустым.

## Skills и workflows

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/api/skills` | manifest и JSON Schema всех skills |
| `GET` | `/api/workflows` | встроенные и пользовательские DAG |
| `POST` | `/api/workflows/validate` | проверить граф без сохранения |
| `PUT` | `/api/workflows/{id}` | сохранить пользовательский workflow |
| `DELETE` | `/api/workflows/{id}` | удалить пользовательский workflow |

Встроенные workflows нельзя удалить или перезаписать. Точная схема payload доступна в OpenAPI и описана в [skills-and-workflows.md](skills-and-workflows.md).

## Состояние

- `GET /health` — liveness API внутри Compose-сети (наружу web проксирует только `/api/*`);
- `GET /api/settings/status` — провайдер, наличие/валидность ключа и slugs моделей без раскрытия секрета.

## Настройки и Telegram

| Метод | Путь | Назначение |
|---|---|---|
| `PUT` | `/api/settings` | сохранить разрешенные runtime-настройки |
| `POST` | `/api/settings/model/test` | выполнить минимальный запрос к основной модели |
| `POST` | `/api/settings/telegram/discover` | найти последний чат, написавший сохраненному боту |
| `POST` | `/api/settings/telegram/test` | отправить тестовое уведомление |

Поля `model_api_key` и `telegram_bot_token` принимаются, но никогда не возвращаются. Пустое секретное поле не затирает сохраненное значение. Для явного удаления предусмотрены `clear_model_api_key` и `clear_telegram_bot_token`.
