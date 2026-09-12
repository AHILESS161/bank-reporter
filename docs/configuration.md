# Конфигурация

Для обычной настройки используйте раздел **Настройки** в интерфейсе. Там можно сохранить ключ модели, адрес OpenAI-совместимого API, Telegram-токен, Chat ID, приоритетные домены и лимиты агента. Изменения применяются без перезапуска. Секреты хранятся в `runtime-settings.json` локального каталога данных и никогда не возвращаются через API открытым текстом.

Пустое поле ключа или токена означает «оставить сохраненное значение». В Docker-редакции runtime-настройки находятся в volume `/data`; в Desktop-редакции — в `~/Library/Application Support/Bank Reporter/data`.

Переменные в корневом `.env` остаются альтернативой для администратора. Файл исключён из Git. После ручного изменения переменных пересоздайте затронутые контейнеры:

```bash
docker compose up -d --force-recreate api worker scheduler
```

## Переменные окружения

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `MODEL_API_KEY` | пусто | ключ основного OpenAI-compatible провайдера |
| `MODEL_BASE_URL` | `https://routerai.ru/api/v1` | базовый URL RouterAI/OpenRouter/совместимого API |
| `OPENROUTER_API_KEY` | пусто | legacy fallback, если `MODEL_API_KEY` пуст |
| `OPENROUTER_BASE_URL` | `https://openrouter.ai/api/v1` | legacy fallback URL |
| `ORCHESTRATOR_MODEL` | `deepseek/deepseek-v4.1-flash` | оркестратор и tool calling |
| `FINANCE_MODEL` | `inclusionai/ling-3.0-flash-fin` | финансовая интерпретация |
| `FINANCE_FALLBACK_MODEL` | `deepseek/deepseek-v4.1-flash` | fallback финансового шага |
| `TELEGRAM_BOT_TOKEN` | пусто | токен BotFather; Telegram отключён без него |
| `TELEGRAM_CHAT_ID` | пусто | получатель уведомлений |
| `TASK_BACKEND` | `celery` | `celery` для Compose, `local` для Desktop |
| `APP_TIMEZONE` | `Europe/Moscow` | расписания и представление времени |
| `DATABASE_URL` | задаётся Compose | SQLAlchemy DSN PostgreSQL |
| `REDIS_URL` | задаётся Compose | broker/result backend Celery |
| `BROWSER_SERVICE_URL` | задаётся Compose | внутренний browser-worker |
| `DATA_DIR` | `/data` | корень документов и артефактов |
| `LIEFLAT_DIR` | `/opt/lieflat-charts` | read-only checkout шаблонов |
| `WEB_ORIGIN` | `http://localhost:3000` | разрешённый web origin |
| `MAX_AGENT_STEPS` | `12` | максимум инструментальных шагов, 1–30 |
| `MAX_WEB_PAGES` | `25` | максимум прочитанных страниц, 1–100 |
| `MAX_FILE_MB` | `100` | максимальный входной файл, 1–500 МБ |
| `MAX_ARCHIVE_MB` | `500` | максимум после распаковки, 1–2000 МБ |
| `TRUSTED_MEDIA_DOMAINS` | список в `config.py` | приоритетные домены СМИ через запятую |

Compose намеренно переопределяет `DATABASE_URL`, `REDIS_URL`, `BROWSER_SERVICE_URL` и `DATA_DIR`, чтобы контейнеры находили друг друга по внутренним DNS-именам. Обычно эти четыре значения менять не надо.

## RouterAI

```env
MODEL_API_KEY=ваш_ключ_routerai
MODEL_BASE_URL=https://routerai.ru/api/v1
ORCHESTRATOR_MODEL=deepseek/deepseek-v4.1-flash
FINANCE_MODEL=inclusionai/ling-3.0-flash-fin
FINANCE_FALLBACK_MODEL=deepseek/deepseek-v4.1-flash
```

Ключ RouterAI не обязан иметь префикс OpenRouter. Проверка формата учитывает выбранный `MODEL_BASE_URL`. После запуска откройте «Настройки» или вызовите `GET /api/settings/status`.

## OpenRouter

Предпочтительный новый вариант также использует универсальные поля:

```env
MODEL_API_KEY=sk-or-v1-...
MODEL_BASE_URL=https://openrouter.ai/api/v1
```

Поля `OPENROUTER_API_KEY` и `OPENROUTER_BASE_URL` сохранены для совместимости. Если заданы оба набора, `MODEL_*` имеет приоритет.

## Политика fallback модели

Ling вызывается для финансовой интерпретации. DeepSeek автоматически заменяет его при API-ошибке, timeout, невалидном JSON после повторов, провале проверки формул/цитат или сообщении модели о невозможности выполнить шаг. Если не проходит и fallback, отчёт остаётся частичным/ошибочным с причиной; уверенный текст не фабрикуется.

## Telegram

```env
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=123456789
```

Перезапустите `api`, `worker` и `scheduler`. Бот только отправляет уведомления и обрабатывает `/today`, `/week`, `/mute`, `/unmute`; полноценного агентского чата через Telegram нет.

## Приоритетные СМИ

Пример:

```env
TRUSTED_MEDIA_DOMAINS=interfax.ru,rbc.ru,kommersant.ru,vedomosti.ru,tass.ru,frankmedia.ru,banki.ru
```

Это влияет на ранжирование контекста, но не превращает вторичный источник в первичный.

## Корпоративный TLS proxy

Если прокси/антивирус выпускает собственные сертификаты, экспортируйте корневой сертификат в PEM/CRT и положите его в `certs/`. Compose монтирует каталог read-only и вызывает `update-ca-certificates` в backend/browser images. Затем пересоберите:

```bash
docker compose build --no-cache api browser
docker compose up -d
```

Не отключайте TLS verification и не добавляйте неизвестные сертификаты.

## Секреты

- не коммитьте `.env`, токены, дампы БД и cookies;
- на сервере ограничьте права файла: `chmod 600 .env`;
- ротируйте ключ, если он попал в чат, screenshot, лог или Git history;
- интерфейс статуса сообщает только наличие/валидность ключа, но не возвращает значение.
