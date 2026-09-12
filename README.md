# Bank Reporter

Локальный агент банковского корреспондента: поиск публичной отчетности и статей, проверяемый финансовый анализ, календарь событий, Telegram-уведомления и отчеты с HTML-предпросмотром и экспортом в PDF/PNG/CSV/XLSX.

> Аналитический инструмент не является источником инвестиционных рекомендаций. Шаблоны Lieflat Charts лицензированы по PolyForm Noncommercial 1.0.0 и не предназначены для коммерческого использования без отдельного разрешения.

## Запуск на macOS с нуля

Самый простой и воспроизводимый вариант — Docker Desktop. Знать Docker не требуется: сценарий установки сам проверит окружение, предложит установить Docker Desktop, запросит ключ RouterAI скрытым вводом и запустит приложение.

1. Скачайте репозиторий через `Code → Download ZIP` и распакуйте его либо выполните:

   ```bash
   git clone --recurse-submodules https://github.com/AHILESS161/bank-reporter.git
   cd bank-reporter
   ```

2. В Finder откройте папку `scripts`, нажмите правой кнопкой по `start-macos.command` и выберите «Открыть». Если macOS не разрешает запуск, выполните в Terminal:

   ```bash
   chmod +x scripts/*.command scripts/*.sh
   ./scripts/start-macos.command
   ```

3. При первом запуске:

   - если установлен Homebrew, Docker Desktop установится автоматически;
   - без Homebrew откроется официальная страница Docker — установите приложение и повторно запустите сценарий;
   - вставьте API-ключ RouterAI, когда сценарий попросит его. Ввод ключа на экране не отображается.

4. После сборки браузер откроет <http://localhost:3000>.

Для следующих запусков используйте тот же `scripts/start-macos.command`. Для остановки без удаления документов — `scripts/stop-macos.command`.

## Ручной запуск

1. Скопируйте `.env.example` в `.env`.
2. Для RouterAI задайте:

   ```env
   MODEL_API_KEY=sk-...
   MODEL_BASE_URL=https://routerai.ru/api/v1
   ```

   Также поддерживается OpenRouter через `MODEL_BASE_URL=https://openrouter.ai/api/v1` и ключ `sk-or-v1-…`.

3. Подготовьте закрепленную версию Lieflat Charts:

   ```bash
   git submodule update --init --recursive
   ```

4. Запустите стек:

   ```bash
   docker compose up --build -d
   ```

5. Откройте <http://localhost:3000>.

Telegram необязателен. Для уведомлений заполните `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` в `.env`.

Если антивирус или корпоративный прокси подменяет HTTPS-сертификаты, экспортируйте его
корневой сертификат в PEM/CRT, положите файл в каталог `certs/` и пересоберите сервисы.
Проверка TLS при этом остаётся включённой.

## Возможности MVP

- агентский чат с SSE-прогрессом и инструментами поиска, скачивания и разбора;
- live-справочник банков и формы 101/102 из веб-службы ЦБ;
- PDF/XLSX/CSV/DBF/ZIP, OCR `rus+eng`, версии оригиналов и точный provenance;
- календарь ЦБ/Минфина и прогноз публикаций банков из watchlist;
- поиск статей через Yandex → Bing RSS с `agent-browser`;
- детерминированные `Decimal`-расчеты и модели DeepSeek/Ling через RouterAI или OpenRouter;
- отчеты Lieflat R04/R09/R11 со встроенным HTML-предпросмотром и экспортом;
- Telegram-дайджесты, напоминания и команды `/today`, `/week`, `/mute`, `/unmute`.

Наружу публикуется только `127.0.0.1:3000`; API, PostgreSQL, Redis и browser-worker остаются во внутренней Docker-сети.

## Разработка

- API/OpenAPI: <http://localhost:3000/api/docs>
- тесты API: `docker compose run --rm api pytest`
- сборка frontend: `docker compose build web`
- состояние сервисов: `docker compose ps`

Архитектура описана в [docs/architecture.md](docs/architecture.md), сторонние лицензии — в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
