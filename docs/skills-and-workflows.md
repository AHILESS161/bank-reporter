# Skills, workflows и MCP

## Зачем нужен конструктор

Агентские возможности оформлены как типизированные skills, а бизнес-сценарии — как проверяемые workflows. Это позволяет добавлять источник, расчёт или экспорт отдельно, явно задавать права и затем соединять совместимые блоки без переписывания оркестратора.

## SkillManifest

Контракт находится в `services/api/app/skills/contracts.py` и включает:

- стабильный `id`, версию, название, описание и категорию;
- transport: `local`, `service` или `mcp`;
- side effects: read-only либо local write;
- список permissions и timeout;
- Pydantic input model, преобразуемую в JSON Schema для tool calling;
- опциональную model policy;
- для MCP — `MCPBinding(server, tool)`.

`SkillRegistry` валидирует вход до вызова handler и возвращает единый envelope результата. Модель не может вызвать незарегистрированный метод или передать произвольные параметры.

## Встроенные skills

| ID | Назначение | Side effect / транспорт |
|---|---|---|
| `resolve_bank` | справочник ЦБ и регистрационный номер | service, DB cache |
| `discover_documents` | поиск официальной отчётности | service, read-only web |
| `download_document` | проверка и сохранение оригинала | service, local write |
| `fetch_cbr_form` | формы ЦБ 101/102 | service, local write |
| `search_articles` | поиск официальных публикаций и статей | service, read-only browser |
| `search_professional_reports` | рейтинговые/отраслевые обзоры для контекста | service, read-only browser |
| `read_article` | извлечение основного HTML-контента | service, read-only browser |
| `list_documents` | запрос локальной библиотеки | local, read-only |
| `query_financial_facts` | Decimal-факты с provenance | local, read-only |
| `read_document` | текст, страницы, листы и ячейки | local, read-only |
| `create_report` | проверка, расчёты и HTML/PDF/PNG/XLSX/CSV | local write, Ling → DeepSeek |

## Встроенные workflows

### `document_discovery`

```text
resolve_bank → [list_documents]
            → discover_documents → download_document
            → [fetch_cbr_form]
            → [search_articles → read_article]
```

Fallback статей используется только если первичный документ недоступен. Форма 101/102 вызывается только по соответствующему запросу.

### `article_research`

```text
[resolve_bank] → search_articles → read_article
```

### `financial_analysis`

```text
[resolve_bank] → list_documents → query_financial_facts ┐
                              └→ [read_document]         │
              → [discover → download]                  ├→ create_report
              → [professional_reports]                 │
              → [fallback articles]                    ┘
```

Квадратные скобки означают необязательный узел. Профессиональные отчёты дают редакционный контекст, но не подменяют первичные цифры.

## Маршрутизация

Пользовательские workflows проверяются раньше встроенной эвристики при совпадении `trigger_hints`. Затем запросы про статьи идут в `article_research`, явный анализ — в `financial_analysis`, остальные запросы на документы — в `document_discovery`.

Workflow registry проверяет:

- что каждый `skill_id` зарегистрирован;
- что все зависимости ссылаются на существующие узлы;
- что узел не зависит сам от себя;
- что граф ацикличен и имеет топологический порядок.

Пользовательские схемы хранятся в `IntegrationState`. Через UI текущего MVP редактируется последовательность; API принимает полный manifest.

## Пример пользовательского workflow

```json
{
  "id": "my_bank_brief",
  "title": "Моя справка по банку",
  "description": "Документы, факты и короткий отчёт",
  "trigger_hints": ["сделай мою справку"],
  "nodes": [
    {"id":"bank","skill_id":"resolve_bank","depends_on":[],"optional":false},
    {"id":"docs","skill_id":"list_documents","depends_on":["bank"],"optional":false},
    {"id":"facts","skill_id":"query_financial_facts","depends_on":["docs"],"optional":false},
    {"id":"report","skill_id":"create_report","depends_on":["facts"],"optional":false}
  ]
}
```

Сначала отправьте объект на `/api/workflows/validate`, затем `PUT /api/workflows/my_bank_brief`.

## Добавление локального skill

1. Создайте Pydantic input model в `catalog.py`.
2. Добавьте метод в `SkillHost` и реализацию в `AgentService`.
3. Объявите manifest, права, timeout и side effects в `SKILL_DEFINITIONS`.
4. Добавьте узел в workflow либо создайте новый.
5. Напишите тесты позитивной схемы, невалидного input и запрещённого вызова.
6. Проверьте, что недоверенный текст не попадает в system/tool инструкции.

## MCP

MCP — уместная граница для внешних, независимо развёрнутых интеграций. В контрактах уже есть transport `mcp`, `MCPBinding` и интерфейс `MCPInvoker`. Текущий Compose не запускает готовый MCP client/server и не содержит настроенного удалённого MCP-инструмента: это extension point, а не обещание работающего подключения.

Чтобы добавить MCP skill:

1. реализуйте `MCPInvoker` с allowlist серверов, таймаутом, аутентификацией и журналированием;
2. зарегистрируйте manifest с точным `server`/`tool`, input schema и минимальными permissions;
3. преобразуйте MCP-ошибки в типизированный результат, не передавая модели скрытые детали;
4. не выносите через MCP локальные `Decimal`-расчёты, чтение БД и запись `/data` без необходимости;
5. добавьте contract/security tests для timeout, неверного JSON, prompt injection и нежелательных side effects.

Для встроенных операций in-process вызов быстрее и проще. MCP стоит применять для действительно внешних источников и reusable-интеграций, а не как обязательную сетевую прослойку между каждым блоком.
