# Установка и запуск

## Требования

- 64-битная Windows 10/11, macOS 13+ или современный Linux;
- Docker Desktop с Compose v2 либо Docker Engine + Compose plugin;
- Git для клонирования и submodule;
- интернет для первичной сборки, поиска источников и моделей;
- ключ RouterAI или OpenRouter;
- минимум 4 ГБ RAM и 20 ГБ свободного места на время первой сборки.

Для постоянной работы рекомендуются 4 vCPU, 8 ГБ RAM и 50–60 ГБ SSD. Небольшой личный стенд обычно работает на 2 vCPU/4 ГБ, но OCR, Chromium и одновременное создание PDF могут дать пики памяти.

## Windows

1. Установите Docker Desktop и включите WSL 2 backend.
2. Клонируйте проект из PowerShell:

   ```powershell
   git clone --recurse-submodules https://github.com/AHILESS161/bank-reporter.git
   Set-Location bank-reporter
   Copy-Item .env.example .env
   ```

3. Заполните `MODEL_API_KEY` и `MODEL_BASE_URL` в `.env`.
4. Выполните:

   ```powershell
   git submodule update --init --recursive
   docker compose up --build -d
   ```

5. Откройте <http://localhost:3000>.

## macOS

### Запуск для человека без опыта работы с Docker

1. Скачайте репозиторий через GitHub `Code → Download ZIP` либо используйте `git clone --recurse-submodules`.
2. Откройте `scripts/start-macos.command` через Finder. Если Gatekeeper блокирует файл, нажмите правой кнопкой → «Открыть».
3. Если Docker Desktop отсутствует, сценарий установит его через Homebrew либо откроет официальную страницу загрузки.
4. При запросе вставьте ключ. Ввод скрыт; значение сохраняется только в локальный `.env`.
5. После сборки откроется <http://localhost:3000>.

Если права запуска потерялись:

```bash
chmod +x scripts/*.command scripts/*.sh
./scripts/start-macos.command
```

Остановка без удаления данных: `scripts/stop-macos.command`.

### Apple Silicon

Compose использует multi-architecture базовые образы. Первая сборка Chromium и OCR может занять заметно больше времени. Если Docker Desktop предлагает Rosetta, она нужна только для стороннего слоя без arm64-варианта.

## Linux

```bash
git clone --recurse-submodules https://github.com/AHILESS161/bank-reporter.git
cd bank-reporter
cp .env.example .env
$EDITOR .env
docker compose up --build -d
```

Пользователь должен иметь право обращаться к Docker daemon. Не запускайте весь проект от root без необходимости.

## Первый контроль

```bash
docker compose ps
docker compose logs --tail=100 api worker browser
```

Ожидается, что сервисы `postgres`, `redis`, `browser`, `api`, `worker`, `scheduler` и `web` запущены. В браузере:

- приложение — <http://localhost:3000>;
- OpenAPI UI — <http://localhost:3000/api/docs>;
- health-check API — `docker compose exec api python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/health').read().decode())"`.

В «Настройки» проверьте доступность ключа и выбранных моделей. Сам ключ интерфейс и API обратно не показывают.

## Обновление

Перед обновлением сделайте резервную копию по [инструкции эксплуатации](operations.md#резервное-копирование).

```bash
git pull --ff-only
git submodule update --init --recursive
docker compose up --build -d
```

Текущий MVP не использует Alembic. Перед обновлением, меняющим модели БД, резервная копия обязательна.

## Остановка и удаление

Остановка с сохранением данных:

```bash
docker compose stop
```

Удаление контейнеров с сохранением volumes:

```bash
docker compose down
```

`docker compose down -v` удаляет PostgreSQL, Redis, документы и отчёты без возможности восстановления. Используйте эту команду только для осознанного полного сброса после резервной копии.

## Почему нет одного EXE

Приложение состоит из web, API, worker, scheduler, browser-worker, PostgreSQL и Redis. Один `.exe` не запускается на Mac и потребовал бы отдельной desktop-архитектуры с заменой БД и очереди. Для Mac без Docker удобнее держать Bank Reporter на сервере и давать доступ через защищённый браузерный адрес или SSH-туннель; подробности — в [эксплуатации](operations.md#развёртывание-на-сервере).
