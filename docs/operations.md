# Эксплуатация

## Сервисы и жизненный цикл

```bash
docker compose up -d
docker compose ps
docker compose stop
```

`stop` сохраняет контейнеры и volumes. `down` удаляет контейнеры/сеть, но сохраняет named volumes. Для пересборки конкретной части:

```bash
docker compose up --build -d api worker scheduler
docker compose up --build -d web
docker compose up --build -d browser
```

## Расписание, Europe/Moscow

| Задача | Расписание |
|---|---|
| синхронизация редакционного календаря | ежедневно 06:00 |
| прогноз событий watchlist | ежедневно 06:20 |
| проверка публикаций ключевой ставки | каждые 30 минут, 08:00–19:59 |
| Telegram-дайджест | ежедневно 08:00 |
| Telegram-напоминания | каждый час |
| Telegram-команды | каждую минуту |
| ожидаемые документы watchlist | каждые 30 минут |

Если локальный компьютер выключен, пропущенные проверки сами по себе не выполняются. Для непрерывного мониторинга нужен постоянно работающий сервер.

## Ресурсы и диск

Ориентиры для небольшой личной установки:

| Режим | CPU | RAM | Диск |
|---|---:|---:|---:|
| минимальный тестовый | 2 vCPU | 4 ГБ | 30 ГБ SSD |
| рекомендуемый постоянный | 4 vCPU | 8 ГБ | 50–60 ГБ SSD |

В простое стек обычно занимает меньше 1 ГБ RAM, но Chromium, OCR и экспорт PDF создают кратковременные пики. Docker images после первой сборки занимают примерно 3,5–5 ГБ; build cache может временно потребовать ещё 15–20 ГБ. `/data` растёт вместе с оригиналами, версиями и экспортами — грубый ориентир 1–3 размера исходных файлов.

Проверка:

```bash
docker stats --no-stream
docker system df
docker compose exec postgres du -sh /var/lib/postgresql/data
docker compose exec api du -sh /data
```

Безопасно удалять неиспользуемый build cache после успешной сборки:

```bash
docker builder prune
```

Команда спросит подтверждение. `docker system prune --volumes` для этого проекта не рекомендуется: она может удалить данные остановленных сервисов.

## Логи и диагностика

```bash
docker compose logs --tail=200 api
docker compose logs --tail=200 worker
docker compose logs --tail=200 scheduler
docker compose logs --tail=200 browser
docker compose logs -f --since=10m api worker
```

Health:

```bash
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
curl http://localhost:3000/api/settings/status
```

В журнале модели сохраняются slug, длительность, токены и ошибка. Скрытые рассуждения и значение API-ключа сохраняться не должны.

## Резервное копирование

Полная копия состоит из PostgreSQL и volume `artifacts`. Redis можно не восстанавливать: это очередь/кэш, а не основной источник данных.

### PostgreSQL

```bash
docker compose exec -T postgres pg_dump -U bank_reporter -d bank_reporter -Fc > bank-reporter-db.dump
```

### Документы и артефакты

Узнайте точное имя volume:

```bash
docker volume ls --filter name=bank-reporter
```

Скопируйте содержимое volume штатным backup-инструментом Docker Desktop либо временным контейнером в каталог, доступ к которому ограничен. В backup попадут исходные банковские документы; храните его как конфиденциальные рабочие данные.

### Восстановление

1. Остановите `api`, `worker` и `scheduler`.
2. Восстановите volume `/data`.
3. Восстановите дамп в пустую/проверенную БД через `pg_restore`.
4. Запустите сервисы и проверьте библиотеку, один чат и один preview.

Не восстанавливайте дамп поверх рабочей БД без отдельной проверки: возможны дубликаты и конфликт схемы.

## Развёртывание на сервере

Для Ubuntu/Debian установите Docker Engine и Compose plugin, клонируйте репозиторий, создайте `.env` с правами `600` и запустите Compose. Оставьте публикацию `127.0.0.1:3000:3000`.

Доступ с Mac/Windows через SSH:

```bash
ssh -N -L 3000:127.0.0.1:3000 user@server.example
```

После подключения откройте <http://localhost:3000>. Это подходит одному доверенному пользователю и не требует публиковать приложение в интернет.

Для общего публичного URL сначала добавьте reverse proxy с HTTPS, аутентификацию, rate limiting, журнал доступа и регулярные backups. Текущий MVP без этих мер публиковать нельзя.

## Обновление production-стенда

1. Сделайте backup БД и `/data`.
2. Зафиксируйте текущий commit и проверьте release notes.
3. Выполните `git pull --ff-only` и обновите submodules.
4. Соберите images до остановки старых контейнеров, если позволяет диск.
5. Запустите `docker compose up -d`.
6. Проверьте health, очередь, настройки модели, чат, PDF preview и календарь.

Из-за отсутствия Alembic нельзя считать обновление схемы автоматически обратимым.

## Удаление данных

- чат удаляется через UI/API и не затрагивает документы;
- отчёт удаляется вместе с его артефактами, но не оригиналами;
- документ удаляется вместе с версиями и файлами;
- удаление банка из watchlist только выключает будущий мониторинг.

Полный сброс volumes необратим. Перед ним отдельно проверьте имена Compose project и volumes и сделайте backup.
