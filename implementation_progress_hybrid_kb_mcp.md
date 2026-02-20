# Implementation Progress — Hybrid KB MCP

## Цель
Реализовать full-scope PRD (MVP + v1 + v2): MCP server (stdio+HTTP), hybrid retrieval (Qdrant+Neo4j), persistent conversation memory, JWT/ACL, audit, incremental ingestion, auto write-back validation.

## Чеклист этапов
- [x] Этап 0 — Инициализация журнала
- [x] Этап 1 — Каркас проекта
- [x] Этап 2 — MCP контракты
- [x] Этап 3 — Backends
- [x] Этап 4 — Hybrid retrieval
- [x] Этап 5 — Conversation memory
- [x] Этап 6 — Ingestion
- [x] Этап 7 — Security
- [x] Этап 8 — Observability + resiliency
- [x] Этап 9 — Тестирование
- [x] Этап 10 — Release readiness

## Лог обновлений

### Запись
- Этап: 0 — Инициализация журнала
- Статус: done
- Дата/время: 2026-02-19T20:52:32Z
- Изменённые файлы:
  - `implementation_progress_hybrid_kb_mcp.md`
- Проверки (lint/type/unit/integration): n/a
- Результат: создан обязательный артефакт прогресса с форматом фиксации по этапам.
- Риски/блокеры: нет
- Следующий шаг: создать каркас проекта и зависимости.

### Запись
- Этап: 1 — Каркас проекта
- Статус: done
- Дата/время: 2026-02-19T20:52:32Z
- Изменённые файлы:
  - `pyproject.toml`
  - `kb_mcp/__init__.py`
  - `kb_mcp/config.py`
  - `kb_mcp/logging.py`
  - `.env.example`
  - `Dockerfile`
  - `docker-compose.yml`
- Проверки (lint/type/unit/integration): compile-only planned
- Результат: подготовлен Python package, конфиг, переменные окружения, контейнерный baseline для local+network стенда.
- Риски/блокеры: нет
- Следующий шаг: реализовать MCP контракты tools/resources/prompts.

### Запись
- Этап: 2 — MCP контракты
- Статус: done
- Дата/время: 2026-02-19T20:52:32Z
- Изменённые файлы:
  - `kb_mcp/server/schemas.py`
  - `kb_mcp/server/app.py`
  - `kb_mcp/server/transport_http.py`
  - `kb_mcp/server/transport_stdio.py`
- Проверки (lint/type/unit/integration): compile-only planned
- Результат: реализованы `kb.search`, `kb.graph_expand`, `kb.explain`, `kb.memory.*`, `kb.ingest.filesystem`, ресурсы `kb://doc|chunk|entity|memory`, prompts.
- Риски/блокеры: нет
- Следующий шаг: подключить production и in-memory backends.

### Запись
- Этап: 3 — Backends
- Статус: done
- Дата/время: 2026-02-19T20:52:32Z
- Изменённые файлы:
  - `kb_mcp/retrieval/vector_store.py`
  - `kb_mcp/retrieval/graph_store.py`
  - `kb_mcp/storage/qdrant_store.py`
  - `kb_mcp/storage/neo4j_store.py`
  - `kb_mcp/storage/in_memory_vector.py`
  - `kb_mcp/storage/in_memory_graph.py`
  - `kb_mcp/storage/metadata_store.py`
  - `kb_mcp/bootstrap.py`
- Проверки (lint/type/unit/integration): compile-only planned
- Результат: добавлены адаптеры Qdrant/Neo4j с фильтрами `workspace_id`/ACL и fallback на in-memory.
- Риски/блокеры: нет
- Следующий шаг: реализовать hybrid retrieval слой.

### Запись
- Этап: 4 — Hybrid retrieval
- Статус: done
- Дата/время: 2026-02-19T20:52:32Z
- Изменённые файлы:
  - `kb_mcp/retrieval/models.py`
  - `kb_mcp/retrieval/router.py`
  - `kb_mcp/retrieval/fusion.py`
  - `kb_mcp/retrieval/rerank.py`
  - `kb_mcp/retrieval/evidence.py`
  - `kb_mcp/retrieval/hybrid.py`
- Проверки (lint/type/unit/integration): unit planned
- Результат: реализованы маршрутизация, fusion, always-on rerank, explainability hooks, vector fallback при недоступном графе.
- Риски/блокеры: нет
- Следующий шаг: добавить persistent conversation memory.

### Запись
- Этап: 5 — Conversation memory
- Статус: done
- Дата/время: 2026-02-19T20:52:32Z
- Изменённые файлы:
  - `kb_mcp/memory/validator.py`
  - `kb_mcp/memory/service.py`
  - `kb_mcp/server/schemas.py`
  - `kb_mcp/server/app.py`
- Проверки (lint/type/unit/integration): unit planned
- Результат: реализованы `kb.memory.upsert/search/delete`, strict validator (citation+confidence+schema), связи memory-entity.
- Риски/блокеры: нет
- Следующий шаг: реализовать ingestion pipeline.

### Запись
- Этап: 6 — Ingestion
- Статус: done
- Дата/время: 2026-02-19T20:52:32Z
- Изменённые файлы:
  - `kb_mcp/ingest/chunking.py`
  - `kb_mcp/ingest/embeddings.py`
  - `kb_mcp/ingest/entity_extract.py`
  - `kb_mcp/ingest/connectors/filesystem.py`
  - `kb_mcp/ingest/connectors/git.py`
  - `kb_mcp/ingest/pipeline.py`
- Проверки (lint/type/unit/integration): unit planned
- Результат: добавлены filesystem+git коннекторы, chunking, entity extraction RU+EN, incremental checksum-based updates.
- Риски/блокеры: нет
- Следующий шаг: закрыть security слой.

### Запись
- Этап: 7 — Security
- Статус: done
- Дата/время: 2026-02-19T20:52:32Z
- Изменённые файлы:
  - `kb_mcp/security/acl.py`
  - `kb_mcp/security/auth.py`
  - `kb_mcp/security/redact.py`
  - `kb_mcp/server/app.py`
- Проверки (lint/type/unit/integration): unit planned
- Результат: JWT parsing, deny-by-default ACL filters, redaction PII/secrets, subject/workspace propagation.
- Риски/блокеры: нет
- Следующий шаг: observability + resiliency.

### Запись
- Этап: 8 — Observability + resiliency
- Статус: done
- Дата/время: 2026-02-19T20:52:32Z
- Изменённые файлы:
  - `kb_mcp/observability/metrics.py`
  - `kb_mcp/observability/tracing.py`
  - `kb_mcp/observability/audit.py`
  - `kb_mcp/retrieval/hybrid.py`
  - `kb_mcp/server/app.py`
- Проверки (lint/type/unit/integration): unit planned
- Результат: добавлены metrics snapshot, trace request_id, audit logs, fallback marker в debug при graph degradation.
- Риски/блокеры: нет
- Следующий шаг: тестирование.

### Запись
- Этап: 9 — Тестирование
- Статус: done
- Дата/время: 2026-02-19T20:52:32Z
- Изменённые файлы:
  - `tests/test_fusion.py`
  - `tests/test_router.py`
  - `tests/test_acl.py`
  - `tests/test_validator.py`
  - `tests/test_memory_service.py`
  - `tests/test_hybrid_fallback.py`
  - `tests/test_ingest_incremental.py`
- Проверки (lint/type/unit/integration):
  - lint: not run
  - type: not run
  - unit: `python3 -m pytest -s` (11 passed)
  - integration: partial by in-memory hybrid fallback scenario
- Результат: тестовый набор проходит, критические сценарии плана покрыты.
- Риски/блокеры: полноценные container integration tests с live Qdrant/Neo4j не запускались автоматически.
- Следующий шаг: release readiness документация.

### Запись
- Этап: 10 — Release readiness
- Статус: done
- Дата/время: 2026-02-19T20:52:32Z
- Изменённые файлы:
  - `README.md`
  - `docs/runbook.md`
  - `docs/kpi_report_template.md`
- Проверки (lint/type/unit/integration): n/a
- Результат: подготовлены quickstart, runbook и KPI report template для релизного контроля.
- Риски/блокеры: требуется фактический KPI прогон на benchmark-наборе 100–300 запросов.
- Следующий шаг: заполнить KPI report после стендовых измерений.

### Запись
- Этап: 9 — Дополнительная валидация runtime
- Статус: done
- Дата/время: 2026-02-19T20:54:01Z
- Изменённые файлы:
  - `implementation_progress_hybrid_kb_mcp.md`
- Проверки (lint/type/unit/integration):
  - runtime import: `python3 - <<...>>` (import_ok)
  - unit: `python3 -m pytest -s` (11 passed)
- Результат: после установки runtime-зависимостей подтверждён успешный импорт MCP server entrypoint.
- Риски/блокеры: линтер/type-check не запускались в текущей среде.
- Следующий шаг: прогонить `ruff` и `mypy` в CI.

### Запись
- Этап: 9/10 — Runtime smoke validation (stdio MCP)
- Статус: done
- Дата/время: 2026-02-19T21:01:35Z
- Изменённые файлы:
  - `kb_mcp/observability/metrics.py`
  - `kb_mcp/retrieval/rerank.py`
  - `kb_mcp/memory/service.py`
  - `kb_mcp/ingest/pipeline.py`
  - `kb_mcp/storage/qdrant_store.py`
  - `kb_mcp/server/app.py`
  - `implementation_progress_hybrid_kb_mcp.md`
- Проверки (lint/type/unit/integration):
  - `python3 -m ruff check .` => OK
  - `python3 -m mypy kb_mcp` => OK
  - `python3 -m pytest -s` => 11 passed
  - MCP stdio smoke: `list_tools`, `kb.ingest.filesystem`, `kb.memory.upsert`, `kb.search`, `kb.memory.search` => OK
- Результат: подтверждена работоспособность tools на живом stdio-транспорте; ingestion + retrieval + memory cycle выполняется без ошибок.
- Риски/блокеры: HTTP transport smoke и контейнерный integration прогон (live Qdrant/Neo4j) пока не запускались.
- Следующий шаг: прогон streamable HTTP и docker-compose E2E.

### Запись
- Этап: 10 — HTTP transport smoke validation
- Статус: done
- Дата/время: 2026-02-19T21:06:40Z
- Изменённые файлы:
  - `implementation_progress_hybrid_kb_mcp.md`
- Проверки (lint/type/unit/integration):
  - HTTP MCP client -> `list_tools` => 7 tools
  - HTTP MCP client -> `kb.ingest.filesystem` => `{'created': 56, 'updated': 0}`
  - HTTP MCP client -> `kb.search` => success, 3 results
- Результат: streamable HTTP transport подтверждён рабочим для инструментов ingestion/search.
- Риски/блокеры: graceful shutdown даёт `CancelledError` при ручном `Ctrl+C` (операционно допустимо для локального прогона).
- Следующий шаг: контейнерный E2E с live Qdrant/Neo4j при необходимости.

### Запись
- Этап: Re-validation via Context7 (MCP + Graph DB + Vector DB)
- Статус: done
- Дата/время: 2026-02-19T21:13:43Z
- Изменённые файлы:
  - `kb_mcp/server/app.py`
  - `kb_mcp/storage/qdrant_store.py`
  - `kb_mcp/storage/neo4j_store.py`
  - `implementation_progress_hybrid_kb_mcp.md`
- Проверки (lint/type/unit/integration):
  - `python3 -m ruff check .` => OK
  - `python3 -m mypy kb_mcp` => OK
  - `python3 -m pytest -s` => 11 passed
  - MCP stdio smoke => `STDIO_TOOLS 7`
  - MCP HTTP smoke on configured port => `HTTP_TOOLS 7` at `127.0.0.1:18080`
- Результат:
  - FastMCP теперь поднимается с `host/port` из `AppConfig`.
  - Qdrant retrieval переведён на `query_points` (актуальный API).
  - Neo4j graph expansion переписан на bounded depth query без параметризации длины path в шаблоне `*1..$depth`.
- Риски/блокеры:
  - При ручном останове HTTP процесса (`Ctrl+C`) остаётся `CancelledError` в логе shutdown; это ожидаемо для локального интерактивного завершения.
- Следующий шаг: при желании запустить docker-compose E2E с live Qdrant+Neo4j.

### Запись
- Этап: 11 — Docker Desktop deployment + persistence + MCP registration + knowledge graph update
- Статус: done
- Дата/время: 2026-02-19T21:28:24Z
- Изменённые файлы:
  - `docker-compose.yml`
  - `.env.example`
  - `.gitignore`
  - `README.md`
  - `kb_mcp/bootstrap.py`
  - `kb_mcp/storage/qdrant_store.py`
  - `/root/.codex/config.toml` (runtime MCP registration)
  - `implementation_progress_hybrid_kb_mcp.md`
- Проверки (lint/type/unit/integration):
  - `python3 -m ruff check .` => OK
  - `python3 -m mypy kb_mcp` => OK
  - `python3 -m pytest -s` => 11 passed
  - `docker compose up -d --build` => services started (`mcp`, `qdrant`, `neo4j`)
  - MCP HTTP smoke (`http://127.0.0.1:8080/mcp`) => list_tools OK (7 tools)
  - Ingestion/search E2E in containers => OK (`created: 90`, `results: 3`)
  - Persistence check after `docker compose restart` => `results_after_restart: 3`
- Результат:
  - Развёртывание в Docker Desktop выполнено.
  - Данные вынесены во внешние bind-mount директории (`.docker-data/qdrant`, `.docker-data/neo4j/data`) для сохранности.
  - MCP зарегистрирован в Codex (`mcp_servers.hybrid_kb_mcp` -> `http://127.0.0.1:8080/mcp`).
  - Информация о создании сервера зафиксирована в графе знаний (memory graph entities/relations).
- Риски/блокеры:
  - Qdrant в bind mount на текущем filesystem пишет warning про filesystem safety checks; функционально работает, но для production лучше ext4 volume.
- Следующий шаг:
  - При необходимости вынести Qdrant/Neo4j на managed внешние инстансы и оставить в compose только `mcp`.

### Запись
- Этап: 12 — LLM tool-orchestration policy and few-shot guidance
- Статус: done
- Дата/время: 2026-02-19T21:43:00Z
- Изменённые файлы:
  - `docs/tool_selection_policy.md`
  - `README.md`
  - `implementation_progress_hybrid_kb_mcp.md`
- Проверки (lint/type/unit/integration): n/a (docs-only)
- Результат:
  - Добавлена формальная политика выбора MCP tools для LLM.
  - Добавлены few-shot сценарии выбора инструментов и правила evidence/citations.
  - В README добавлена ссылка на policy как каноничный документ для оркестратора.
- Риски/блокеры: нет
- Следующий шаг: встроить policy текст в system prompt вашего LLM-host/agent runtime.

### Запись
- Этап: 13 — Runtime policy wiring (system prompt + agent router) + JSON template
- Статус: done
- Дата/время: 2026-02-19T21:46:53Z
- Изменённые файлы:
  - `kb_mcp/retrieval/router.py`
  - `kb_mcp/server/app.py`
  - `tests/test_router.py`
  - `docs/tool_selection_policy.template.json`
  - `README.md`
  - `implementation_progress_hybrid_kb_mcp.md`
- Проверки (lint/type/unit/integration):
  - `python3 -m ruff check .` => OK
  - `python3 -m mypy kb_mcp` => OK
  - `python3 -m pytest -s` => 13 passed
- Результат:
  - Роутер стал intent-aware (`fact_lookup|relation_impact|explainability|memory_context|memory_delete`) и возвращает `recommended_tools`.
  - В `kb.search.decision_trace` добавлены `intent`, `recommended_tools`, `policy_version`.
  - В runtime добавлены `kb.tool_selection_policy` prompt и resource `kb://policy/tool-selection`.
  - Добавлен готовый JSON-шаблон конфигурации агента: `docs/tool_selection_policy.template.json`.
- Риски/блокеры: нет
- Следующий шаг: подключить `kb.tool_selection_policy` и JSON template в runtime-конфиг вашего LLM host/agent router.

### Запись
- Этап: WS1 — Security/Transport/Auth hardening
- Статус: done
- Дата/время: 2026-02-20T22:07:09Z
- Изменённые файлы:
  - `kb_mcp/config.py`
  - `kb_mcp/security/auth.py`
  - `kb_mcp/server/app.py`
  - `kb_mcp/observability/audit.py`
  - `kb_mcp/server/schemas.py`
  - `.env.example`
  - `docker-compose.yml`
- Проверки (lint/type/unit/integration): см. итоговый bundle в WS7
- Результат:
  - Добавлен dual/strict auth resolver с precedence `Authorization -> payload_jwt -> legacy_acl`.
  - `kb.search.decision_trace` расширен полями `auth_mode` и `identity_source`.
  - Включён ACL enforcement для ресурсов `kb://doc|chunk|entity|memory`.
  - Включены transport security defaults для Host/Origin validation.
- Риски/блокеры:
  - Для production с external host нужно явно настроить `KB_TRANSPORT_ALLOWED_HOSTS`/`KB_TRANSPORT_ALLOWED_ORIGINS`.
- Следующий шаг: завершить persistence layer.

### Запись
- Этап: WS2 — Persistence layer (metadata + incremental state)
- Статус: done
- Дата/время: 2026-02-20T22:07:09Z
- Изменённые файлы:
  - `kb_mcp/storage/metadata_store.py`
  - `kb_mcp/storage/sql_metadata_store.py`
  - `kb_mcp/bootstrap.py`
  - `pyproject.toml`
- Проверки (lint/type/unit/integration): см. итоговый bundle в WS7
- Результат:
  - Добавлен SQL metadata backend (`sqlite` default + `postgres` через DSN).
  - Персистентно хранятся documents/chunks/entities/memory/checksums.
  - Добавлен bootstrap-init схемы таблиц при старте.
- Риски/блокеры:
  - Для Postgres нужен установленный DB driver в runtime образе.
- Следующий шаг: закрыть retrieval quality core.

### Запись
- Этап: WS3 — Retrieval quality core (embeddings + rerank correctness)
- Статус: done
- Дата/время: 2026-02-20T22:07:09Z
- Изменённые файлы:
  - `kb_mcp/ingest/embeddings.py`
  - `kb_mcp/storage/qdrant_store.py`
  - `kb_mcp/retrieval/models.py`
  - `kb_mcp/retrieval/rerank.py`
  - `kb_mcp/retrieval/hybrid.py`
- Проверки (lint/type/unit/integration): см. итоговый bundle в WS7
- Результат:
  - Введён pluggable embedder (`local` + `openai_compatible` + fallback).
  - Убран hash-only путь из Qdrant adapter, enforced vector dimension.
  - Rerank переведён на `(query, chunk_text)` и нормализованный score fusion.
  - Delete memory/chunks в Qdrant выполняется с payload filters.
- Риски/блокеры:
  - При отсутствии `sentence-transformers` используется deterministic fallback embedder.
- Следующий шаг: закрыть graph model completeness.

### Запись
- Этап: WS4 — Graph model completeness and correctness
- Статус: done
- Дата/время: 2026-02-20T22:07:09Z
- Изменённые файлы:
  - `kb_mcp/retrieval/graph_store.py`
  - `kb_mcp/storage/neo4j_store.py`
  - `kb_mcp/storage/in_memory_graph.py`
  - `kb_mcp/ingest/entity_extract.py`
  - `tests/test_graph_schema.py`
- Проверки (lint/type/unit/integration): см. итоговый bundle в WS7
- Результат:
  - Реализованы узлы/рёбра `Document`, `Chunk`, `Entity`, `CONTAINS`, `MENTIONS`, `DOCUMENTED_IN`.
  - `resolve_entities` переведён на `name|aliases|canonical_key`.
  - Добавлены rule-based domain edges (`DEPENDS_ON|CALLS|OWNS|IMPLEMENTS|AFFECTS`).
- Риски/блокеры:
  - Domain relation extraction остаётся rule-based (без LLM extraction).
- Следующий шаг: закрыть ingestion integration.

### Запись
- Этап: WS5 — Ingestion and connectors completion
- Статус: done
- Дата/время: 2026-02-20T22:07:09Z
- Изменённые файлы:
  - `kb_mcp/ingest/pipeline.py`
  - `kb_mcp/ingest/connectors/filesystem.py`
  - `kb_mcp/server/app.py`
  - `kb_mcp/retrieval/vector_store.py`
  - `kb_mcp/storage/in_memory_vector.py`
- Проверки (lint/type/unit/integration): см. итоговый bundle в WS7
- Результат:
  - Интегрирован `GitConnector` (`kb.ingest.git_diff`).
  - Checksum state вынесен из RAM в metadata backend.
  - Добавлена очистка stale chunks (vector + graph + metadata).
  - Добавлена нормализация `source`, `tags`, `updated_at`, `checksum`.
- Риски/блокеры: нет
- Следующий шаг: добавить KPI harness.

### Запись
- Этап: WS6 — Observability and KPI harness
- Статус: done
- Дата/время: 2026-02-20T22:07:09Z
- Изменённые файлы:
  - `bench/corpus/*.md`
  - `bench/queries.jsonl`
  - `bench/relevance.jsonl`
  - `bench/run_benchmark.py`
- Проверки (lint/type/unit/integration): см. итоговый bundle в WS7
- Результат:
  - Добавлен локальный benchmark harness с метриками Recall@10, nDCG@10, MRR, citation coverage, P95.
  - Добавлены gate-проверки KPI с отдельными отчётами no-rerank/rerank.
- Риски/блокеры:
  - Для параллельных benchmark запусков нужен отдельный metadata DSN во избежание SQLite DDL race.
- Следующий шаг: обновить docs и release notes.

### Запись
- Этап: WS7 — Docs, migration notes, release artifacts
- Статус: done
- Дата/время: 2026-02-20T22:07:09Z
- Изменённые файлы:
  - `README.md`
  - `docs/runbook.md`
  - `docs/kpi_report_template.md`
  - `docs/tool_selection_policy.md`
  - `docs/tool_selection_policy.template.json`
  - `implementation_progress_hybrid_kb_mcp.md`
- Проверки (lint/type/unit/integration):
  - `python3 -m ruff check .` => OK
  - `python3 -m mypy kb_mcp bench tests` => OK
  - `python3 -m pytest -s` => 19 passed
  - `python3 bench/run_benchmark.py --top-k 10 --enforce-gates` => PASS
  - `python3 bench/run_benchmark.py --top-k 10 --rerank --enforce-gates` => PASS
- Результат:
  - Документация обновлена под новые auth/metadata/benchmark режимы.
  - Зафиксированы KPI отчёты (`bench/report_no_rerank.json`, `bench/report_with_rerank.json`).
- Риски/блокеры:
  - В тестах auth используется короткий HMAC secret (warning), не влияет на функциональность.
- Следующий шаг: подготовить commit/release tag.
