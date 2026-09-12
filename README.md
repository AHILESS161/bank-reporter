# Bank Reporter

Локальный русскоязычный агент банковского корреспондента. Он ищет публичную отчётность и профильные публикации, сохраняет оригиналы, извлекает проверяемые финансовые факты, ведёт календарь событий и собирает аналитические отчёты с HTML-предпросмотром и выгрузкой в PDF, PNG, XLSX и CSV.

> Bank Reporter — аналитический инструмент, а не инвестиционная рекомендация. Шаблоны Lieflat Charts доступны только для некоммерческого использования по PolyForm Noncommercial 1.0.0.

## Что уже работает

- чат с сохраняемой историей, SSE-прогрессом, ссылками и удалением диалогов;
- поиск банка через справочник ЦБ и загрузка форм 101/102;
- поиск МСФО/РСБУ на официальных сайтах банков с безопасным браузерным fallback;
- загрузка и разбор PDF, XLSX, CSV, DBF, ZIP и XML; OCR `rus+eng` для сканов;
- финансовые факты в `Decimal` с `ProvenanceRef` до страницы, листа или ячейки;
- календарь ЦБ, Минфина и банков из watchlist, ICS и Telegram-уведомления;
- отчёты R04/R09/R11 с предпросмотром, разными шаблонами для профиля и динамики;
- конструктор из 11 типизированных skills и валидируемых workflows;
- DeepSeek для оркестрации, Ling для финансовой интерпретации и автоматический fallback;
- хранение документов, отчётов и чатов в локальном контуре без телеметрии.
- переключаемые темы: строгая деловая и розовая «Котики и кролики».
- отдельная macOS Desktop-редакция в DMG без Docker, PostgreSQL и Redis.

## Быстрый запуск

Нужны Docker Desktop, Git, интернет и API-ключ RouterAI либо OpenRouter.

```bash
git clone --recurse-submodules https://github.com/AHILESS161/bank-reporter.git
cd bank-reporter
cp .env.example .env
```

В `.env` укажите один из вариантов:

```env
# RouterAI
MODEL_API_KEY=ваш_ключ
MODEL_BASE_URL=https://routerai.ru/api/v1
```

или:

```env
# OpenRouter
MODEL_API_KEY=sk-or-v1-...
MODEL_BASE_URL=https://openrouter.ai/api/v1
```

Запуск:

```bash
git submodule update --init --recursive
docker compose up --build -d
```

Откройте <http://localhost:3000>. Проверка API: <http://localhost:3000/api/docs>.

На macOS можно дважды открыть `scripts/start-macos.command`; при первом запуске сценарий поможет установить Docker Desktop и безопасно запросит ключ. Остановка без удаления данных — `scripts/stop-macos.command`.

Для пользователя без Docker рекомендуется готовая Desktop-редакция: скачайте подходящий `arm64` или `x64` DMG из GitHub Releases, перенесите приложение в Applications и задайте ключ в разделе «Настройки». Подробности: [Bank Reporter Desktop для macOS](docs/macos-desktop.md).

## Архитектура

Web-порт привязан только к `127.0.0.1:3000`; API, PostgreSQL, Redis и browser-worker доступны лишь внутри Compose-сети. Интерактивная схема: [docs/bank-reporter.architecture.html](docs/bank-reporter.architecture.html), исходник: [docs/bank-reporter.architecture.json](docs/bank-reporter.architecture.json).

## Документация

- [Оглавление документации](docs/README.md)
- [Установка на Windows, macOS, Linux и сервер](docs/installation.md)
- [Руководство пользователя](docs/user-guide.md)
- [Архитектура и потоки данных](docs/architecture.md)
- [Настройка моделей, Telegram и лимитов](docs/configuration.md)
- [REST/SSE API](docs/api.md)
- [Skills, workflows и MCP](docs/skills-and-workflows.md)
- [Эксплуатация, ресурсы и резервное копирование](docs/operations.md)
- [Безопасность](docs/security.md)
- [Разработка и тестирование](docs/development.md)
- [Устранение неполадок](docs/troubleshooting.md)
- [Сторонние лицензии](THIRD_PARTY_NOTICES.md)

## Основные команды

```bash
docker compose ps
docker compose logs -f api worker scheduler browser web
docker compose run --rm api pytest -q
docker compose stop
docker compose up -d
```

Данные сохраняются в Docker volumes после `stop`, перезапуска и пересборки. Не выполняйте `docker compose down -v`, если не хотите безвозвратно удалить базу, документы и отчёты.

## Ограничения MVP

- нет регистрации, ролей и многопользовательской изоляции;
- нет обхода CAPTCHA, paywall, авторизации и запретов сайта;
- постоянный мониторинг работает только для watchlist и только пока запущен scheduler;
- для публичного доступа нужны отдельные HTTPS и аутентификация;
- схема БД создаётся SQLAlchemy при старте; полноценные миграции Alembic пока не добавлены;
- коммерческий релиз запрещён до замены Lieflat Charts либо получения другой лицензии.

Исходный код проекта распространяется на условиях, указанных в [LICENSE](LICENSE.md).
