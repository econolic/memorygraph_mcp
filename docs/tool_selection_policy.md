# Tool Selection Policy For LLM Orchestrator

Этот документ задает, как LLM должна выбирать инструменты MCP в `hybrid-kb-mcp`.

## 1. Цель

- Уменьшить галлюцинации.
- Привязывать утверждения к evidence.
- Использовать минимально достаточный набор tools.
- Сохранять только валидные факты в memory.

## 2. Короткая таблица выбора

- `kb.search`:
  - использовать для фактологии, определений, поиска документации, цитат;
  - mode по умолчанию: `hybrid`.
- `kb.graph_expand`:
  - использовать для зависимостей, impact analysis, путей между сущностями.
- `kb.explain`:
  - использовать, когда нужно объяснить релевантность найденного результата.
- `kb.memory.search`:
  - использовать для персонального/сессионного контекста пользователя.
- `kb.memory.upsert`:
  - использовать для сохранения подтвержденных фактов, решений, предпочтений.
- `kb.memory.delete`:
  - использовать при запросе удаления памяти.

## 3. Правила маршрутизации

1. Если вопрос содержит “что это”, “где описано”, “покажи источник”, “цитату”, сначала вызывай `kb.search`.
   - Если пользователь ограничивает поиск по источнику/свежести, передавай `filters.sources`, `filters.tags`, `filters.updated_after`.
2. Если вопрос содержит “зависимость”, “влияние”, “кто использует”, “цепочка”, вызывай:
   - `kb.search(mode=hybrid)` и затем
   - `kb.graph_expand`.
3. Если пользователь просит “почему ты так ответил”, вызывай `kb.explain`.
4. Если в запросе есть “как мы делали раньше”, “мой прошлый контекст”, сначала вызывай `kb.memory.search`, затем `kb.search`.
5. Не сохраняй в память ничего без `citations` и достаточного `confidence`.
6. Если пользователь явно просит обновить KB/пересканировать проект:
   - сначала предпочитай `kb.ingest.git_diff` (быстрее и дешевле);
   - используй `kb.ingest.filesystem`, если нужен полный перескан или git baseline недоступен.

## 4. Политика вызовов (обязательная)

Перед финальным ответом модель должна пройти шаги:

1. Определить intent (`fact_lookup`, `relation_impact`, `explainability`, `memory_context`, `memory_delete`).
2. Выбрать tool-set.
3. Выполнить tool calls.
4. Проверить, что в ответе есть evidence для ключевых утверждений.
5. Только после этого сформировать текст ответа.

Если tool вернул ошибку:

- деградировать к ближайшему безопасному варианту;
- явно отметить ограничение (“не удалось получить граф, ответ на основе vector evidence”).

## 5. Рекомендуемый системный блок для оркестратора

```text
Ты работаешь с MCP tools базы знаний.
Всегда сначала решай, нужен ли вызов tools.
Если утверждение можно проверить через KB, сначала вызывай tool.
Приоритет:
1) kb.memory.search для user/workspace контекста;
2) kb.search для фактов и цитат;
3) kb.graph_expand для связей и влияния;
4) kb.explain для объяснения релевантности.
Сохраняй новые факты только через kb.memory.upsert и только с citations и confidence.
Не выдумывай источники. Если evidence нет — сообщи это явно.
```

## 6. Few-shot примеры

### Example 1: Фактология

- User: “Где документирован контракт API Z?”
- Plan:
  - call `kb.search(mode=hybrid, query='контракт API Z')`
  - answer with citations.

### Example 2: Зависимости

- User: “Какие сервисы зависят от API Z?”
- Plan:
  - call `kb.search(mode=hybrid, query='сервисы зависят API Z')`
  - extract entity URIs from results
  - call `kb.graph_expand(seed_entities=[...], depth=2, edge_types=['DEPENDS_ON','CALLS'])`
  - answer with graph paths + citations.

### Example 3: Объяснение

- User: “Почему этот результат релевантен?”
- Plan:
  - call `kb.explain(uris=[...])`
  - summarize vector/graph reasons.

### Example 4: Память пользователя

- User: “Что мы решили по lagerid в прошлый раз?”
- Plan:
  - call `kb.memory.search(query='lagerid decision', workspace_id, subject, session_id)`
  - call `kb.search(query='lagerid')` для верификации
  - answer with “memory + evidence”.

### Example 5: Сохранение решения

- User: “Запомни: используем Qdrant 1.17.0 для prod.”
- Plan:
  - verify by `kb.search` (если применимо)
  - call `kb.memory.upsert(items=[{type:'decision', text:'...', citations:[...], confidence:0.9}])`
  - confirm save id.

### Example 6: Удаление памяти

- User: “Удалить всё, что ты помнишь обо мне в этом workspace.”
- Plan:
  - call `kb.memory.delete(all_for_subject=true, workspace_id, subject)`
  - confirm deleted_count.

### Example 7: Принудительное обновление индекса

- User: “Обнови знания по последним изменениям в репозитории.”
- Plan:
  - call `kb.ingest.git_diff(repo_root='...', workspace_id, acl_subject, since_ref='HEAD~1')`
  - если измененных файлов нет или baseline неизвестен, fallback на `kb.ingest.filesystem(root_path='...')`
  - call `kb.search` для smoke-проверки свежих данных.

## 7. JSON decision schema (опционально)

Можно использовать промежуточный structured шаг:

```json
{
  "intent": "fact_lookup|relation_impact|explainability|memory_context|memory_delete",
  "tools": [
    {
      "name": "kb.search",
      "reason": "Need evidence with citations"
    }
  ],
  "requires_citations": true
}
```

## 8. Антипаттерны

- Отвечать без tools на проверяемые вопросы.
- Сохранять memory без citations.
- Использовать только graph без первоначального retrieval evidence.
- Давать “уверенный” ответ при пустом результате tools.
- Вызывать полный `kb.ingest.filesystem` без необходимости, когда достаточно `kb.ingest.git_diff`.

## 9. Минимальный SLA для ответа

- Для ключевых утверждений должны быть citations.
- Если citations отсутствуют, ответ должен явно содержать дисклеймер.
- При деградации (например, граф недоступен) это должно быть указано в ответе.
- Если в `decision_trace.identity_source=legacy_acl`, помечать ответ как compatibility-mode и запрашивать переход на header auth.
- При отладке retrieval учитывать `debug.filters_effective`, `debug.graph_acl_enforced`, `debug.fusion_mode`.
