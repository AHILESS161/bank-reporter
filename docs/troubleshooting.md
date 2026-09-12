# Устранение неполадок

## Агент не отвечает после добавления ключа

1. Убедитесь, что ключ находится в корневом `.env`, а не в `.env.example`.
2. Для RouterAI должны быть заданы именно:

   ```env
   MODEL_API_KEY=...
   MODEL_BASE_URL=https://routerai.ru/api/v1
   ```

3. Пересоздайте backend-контейнеры:

   ```bash
   docker compose up -d --force-recreate api worker scheduler
   ```

4. Проверьте статус и логи:

   ```bash
   curl http://localhost:3000/api/settings/status
   docker compose logs --tail=200 worker api
   ```

5. Проверьте наличие выбранных slugs у провайдера. Ключ RouterAI не нужно заменять на OpenRouter, если endpoint RouterAI доступен.

## После обновления страницы пропал чат

Чаты должны храниться в PostgreSQL. Проверьте `docker compose ps postgres api`, затем `GET /api/threads`. Если список пуст после `down -v`, volume был удалён и восстановить историю можно только из backup. Если API возвращает чаты, но UI их не показывает, очистите только состояние активной вкладки браузера и выберите чат из списка; не очищайте Docker volumes.

## Не создаётся отчёт

- нужен хотя бы один существующий `document_id`;
- дождитесь статуса документа `parsed`;
- проверьте worker и browser;
- для PDF/PNG нужен здоровый Chromium;
- при отсутствии модели HTML может быть собран только из проверяемых фактов с явным ограничением;
- статус `failed` и причина видны в карточке/логах.

```bash
docker compose logs --tail=300 worker browser
```

## В отчёте нет динамики

Для динамики нужны два сопоставимых значения одного metric code, одинаковой валюты и масштаба, с разными периодами. Запрос должен явно содержать сравнение/динамику. Используйте два годовых или два одинаковых промежуточных периода; не смешивайте МСФО группы с РСБУ банка без явной оговорки.

## Найден только пресс-релиз, а не PDF

Проверьте официальный IR-раздел вручную и передайте прямую публичную ссылку. Агент не обходит CAPTCHA/paywall/login. Он может сохранить press release и собрать частичную таблицу, но обязан отметить, что это не полный отчёт.

## PDF не открывается в preview

- preview поддерживает только MIME `application/pdf`;
- `410` означает, что запись есть, а файл volume отсутствует;
- проверьте `/data` и права volume;
- внешний viewer браузера может блокироваться корпоративной политикой — используйте «Скачать PDF».

## Календарь не обновляется

```bash
docker compose ps scheduler worker redis
docker compose logs --tail=200 scheduler worker
curl -X POST http://localhost:3000/api/calendar/sync
```

Синхронизация требует интернета. Watchlist-события появляются только для добавленных банков. Локальный компьютер должен быть включён в момент расписания.

## Событие календаря не кликабельно

Ссылка появляется только при наличии безопасного `source_url`. Для прогнозного или ещё не опубликованного события ссылки может не быть. После обнаружения публикации статус должен перейти в `published` и открыть первоисточник.

## Docker не запускается

```bash
docker version
docker compose version
docker compose config
docker compose ps -a
```

На Windows проверьте, что Docker Desktop запущен и WSL 2 работает. На Mac дождитесь состояния «Docker Desktop is running». После нехватки диска перезапустите Docker Desktop и только затем Compose.

## Куда уходит место

```bash
docker system df
docker system df -v
docker compose exec api du -sh /data
```

Основные потребители: build cache, образы Chromium/OCR, PostgreSQL и `/data`. Для cache используйте `docker builder prune`. Документы и отчёты удаляйте через UI, чтобы записи БД и файлы оставались согласованными. Не применяйте `docker system prune --volumes`, если нужны данные.

## OCR медленный или ошибается

OCR запускается только для PDF без достаточного текстового слоя. Убедитесь, что скан не повёрнут, имеет приемлемое разрешение и использует русский/английский язык. OCR-цифры всегда сверяйте с изображением страницы.

## TLS/certificate error

Корпоративный proxy может подменять сертификаты. Экспортируйте доверенный корневой CA в `certs/`, пересоберите `api` и `browser`. Не устанавливайте `verify=false` и не отключайте TLS глобально.

## Удаление заблокировано с 409

Чат нельзя удалить во время активного run; отчёт — в `queued`/`processing`. Отмените запуск или дождитесь завершения и повторите. Это защищает от удаления файлов, которые ещё записываются.

## Быстрый диагностический набор

```bash
docker compose ps
docker compose logs --tail=100 api worker browser scheduler
docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"
curl http://localhost:3000/api/settings/status
docker system df
```

Перед отправкой логов удалите ключи, токены, URL с секретными query-параметрами и содержимое пользовательских документов.
