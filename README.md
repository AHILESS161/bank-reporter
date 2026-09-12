# Bank Reporter

Локальный агент банковского корреспондента: поиск публичной отчетности и статей, проверяемый финансовый анализ, календарь публикаций, Telegram-уведомления и экспорт отчетов.

> Прототип не является источником инвестиционных рекомендаций. Встроенные шаблоны Lieflat Charts имеют лицензию PolyForm Noncommercial 1.0.0 и не могут использоваться коммерчески без отдельного разрешения.

## Быстрый запуск

1. Скопируйте `.env.example` в `.env` и задайте `OPENROUTER_API_KEY`.
2. Инициализируйте закрепленный submodule: `git submodule update --init --recursive` (или запустите `powershell -ExecutionPolicy Bypass -File scripts/fetch-lieflat.ps1`, который также проверит commit).
3. Запустите `docker compose up --build` — дальше весь стек поднимается одной командой.
4. Откройте <http://localhost:3000>.

Telegram необязателен. Для уведомлений заполните `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID`.

## Что входит в MVP

- агентский чат с SSE-прогрессом, инструментами поиска/скачивания/разбора и лимитами запуска;
- live-справочник банков и формы 101/102 из веб-службы ЦБ;
- PDF/XLSX/CSV/DBF/ZIP, OCR `rus+eng`, неизменяемые версии и точный provenance;
- календарь ЦБ/Минфина, прогноз публикаций watchlist и экспорт ICS;
- поиск профильных статей через Yandex → Bing RSS с `agent-browser`, доменными ограничениями и дедупликацией;
- детерминированные `Decimal`-расчеты, модели DeepSeek/Ling с проверяемым fallback;
- офлайн-отчеты Lieflat R04/R09/R11 и выгрузки HTML/PDF/PNG/CSV/XLSX;
- Telegram-дайджесты, напоминания и команды `/today`, `/week`, `/mute`, `/unmute`.

Наружу публикуется только `127.0.0.1:3000`; API, PostgreSQL, Redis и browser-worker остаются во внутренней Docker-сети.

## Разработка

- API/OpenAPI: <http://localhost:3000/api/docs>
- Проверка API: `docker compose run --rm api pytest`
- Проверка frontend: `docker compose run --rm web npm test`
- Статус сервисов: `docker compose ps`
- Все оригиналы и артефакты сохраняются в Docker volume `artifacts` до ручного удаления.

Архитектура и ограничения описаны в [docs/architecture.md](docs/architecture.md).

Собственный код пока распространяется без предоставления лицензии (`LICENSE.md`). Уведомления и ограничения сторонних компонентов перечислены в `THIRD_PARTY_NOTICES.md`.
