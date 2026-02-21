# Оценка реализации econolic/memorygraph_mcp относительно PRD Hybrid Retrieval MCP для KB

## Executive summary

**Enabled connectors:** github.

Репозиторий `econolic/memorygraph_mcp` (default branch: `main`, видимость: private) реализует “сквозной” MVP/v1‑каркас **Hybrid Retrieval MCP‑сервера**: ingestion (filesystem + git diff), hybrid retrieval (vector + graph + rerank + деградация), ресурсы `kb://*` с server‑side ACL проверкой, два транспорта (stdio + Streamable HTTP), базовая observability (JSON‑логи, audit, in‑proc метрики), тесты, docker‑compose окружение (Qdrant + Neo4j + MCP). Это в целом хорошо совпадает с написанным PRD по архитектуре и набору контрактов.

Ключевые сильные стороны реализации:
- Реализован MCP‑сервер на базе FastMCP с **tools/resources/prompts** и Streamable HTTP endpoint `/mcp`, плюс transport‑защиты (DNS rebinding / Origin / allowlists) через настройки SDK, что соответствует требованиям MCP про безопасность транспорта. citeturn3search0  
- Есть полноценный ingestion с **инкрементальными апдейтами по checksum**, включая удаление устаревших чанков из vector + graph + metadata.  
- Реализован quality harness: `bench/run_benchmark.py` считает Recall@10 и nDCG@10 и может “гейтить” релиз, что прямо соответствует KPI в PRD.  

Основные расхождения с PRD (наиболее нагрузочные):
- Фильтры `tags/sources/updated_after` формально присутствуют в schema, но **не применяются** в vector/graph retrieval (фактически работают только `workspace_id` и `acl_subject`). Это снижает управляемость retrieval/сегментацию KB.
- Graph retrieval в текущем виде фильтруется по `workspace_id`, но **не учитывает `acl_allow` на уровне графа**: `kb.graph_expand` потенциально может раскрывать структуру/связи внутри workspace даже для объектов, которые не должны быть видны субъекту (если в пределах workspace планируется object‑level ACL).
- Chunking — простой char‑based splitter; он функционален, но качество retrieval может проигрывать sentence/token‑aware chunking (это подтверждают учебные материалы по chunking‑стратегиям). citeturn4search6  

Отдельно: репозиторий приватный, поэтому внешние web‑инструменты не могут открывать исходники по URL. Все ссылки на код и фрагменты кода приведены по данным из GitHub‑коннектора; внешние нормативные утверждения подтверждены официальными веб‑источниками (MCP spec, docs Qdrant/Neo4j/SBERT).

## Область, источники и ограничения

**Какой PRD сравнивался:** `prd_hybrid_retrieval_mcp_knowledge_base.md` в этом же репозитории (default branch `main`). В PRD заданы цели, KPI, онтология (Document/Chunk/Entity), инструменты MCP (`kb.search`, `kb.graph_expand`, `kb.explain`), ресурсы `kb://doc|chunk|entity`, требования по ACL, аудит, observability и offline‑оценка качества.

**Внешние источники (официальные/первичные):**
- MCP Streamable HTTP transport + security warning (Origin validation, localhost binding, auth). citeturn3search0turn3search1  
- MCP Authorization (OAuth‑2.1‑совместимая модель для HTTP‑транспортов). citeturn3search2turn3search6  
- MCP Tools и Resources (контракты discovery и security considerations). citeturn3search11turn3search7turn3search3  
- Qdrant: neural search tutorial (384 dims, модель all‑MiniLM‑L6‑v2), query_points API, payload indexing и strict mode. citeturn4search1turn4search9turn4search0turn4search3  
- Neo4j: variable-length patterns + рекомендации по производительности и ограничениям, а также предупреждение “read routing ≠ access control”. citeturn5search1turn5search0  
- Sentence‑Transformers: cross‑encoder reranker требует пары текстов (query, passage) + практики rerank top‑k. citeturn7search0turn7search2turn7search12  
- GraphRAG позиционирование (vector RAG + graph traversal), как обоснование hybrid retrieval. citeturn6search1  
- (Опционально, для альтернативного vector backend) entity["organization","pgvector","postgres vector extension"]: базовые конструкции `CREATE EXTENSION vector`, nearest neighbor operators, hybrid search идеи. citeturn6search0  

**Ограничение по ссылкам на исходники:** репозиторий приватный, поэтому ссылки на файлы и строки приведены GitHub‑перmalink’ами (в код‑блоках); внешние web‑цитаты применимы только к спецификациям и документации.

## Архитектура проекта и целевая PRD‑архитектура

Фактическая runtime‑архитектура (на уровне модулей) соответствует PRD “Router → VectorRetriever → EntityResolver/GraphRetriever → Fusion → Rerank → EvidenceBuilder”, плюс добавлены memory‑операции и ingestion Tools.

```mermaid
flowchart LR
  A[LLM Host / Agent] --> B[MCP Client]
  B -->|stdio or Streamable HTTP| S[FastMCP server /mcp]

  subgraph S[hybrid-kb-mcp]
    T1[kb.search] --> R[QueryRouter]
    R --> HR[HybridRetriever]
    HR --> VS[VectorStore]
    HR --> GS[GraphStore]
    HR --> F[Fusion + lexical blend]
    F --> RR[Reranker (CrossEncoder)]
    RR --> EB[EvidenceBuilder]
    EB --> OUT[Evidence results + citations]

    T2[kb.graph_expand] --> GS
    T3[kb.explain] --> GS

    M1[kb.memory.*] --> VS
    M1 --> GS
    M1 --> META[Metadata backend]
    ING[kb.ingest.*] --> VS
    ING --> GS
    ING --> META
  end

  VS --> Q[(Qdrant)]
  GS --> N[(Neo4j)]
  META --> SQL[(SQLite/Postgres)]
```

Последовательность MCP‑взаимодействий с LLM‑оркестратором (соответствует policy в репо):

```mermaid
sequenceDiagram
  participant U as User
  participant L as LLM Orchestrator
  participant M as MCP Server

  U->>L: Вопрос
  alt include_memory or memory_context
    L->>M: tools/call kb.memory.search
    M-->>L: memory_hits
  end
  L->>M: tools/call kb.search
  M-->>L: results + citations + decision_trace + debug

  alt relation_impact intent
    L->>M: tools/call kb.graph_expand
    M-->>L: nodes/edges/paths
  end

  alt explainability intent
    L->>M: tools/call kb.explain
    M-->>L: reasons
  end

  L->>M: resources/read kb://chunk/...
  M-->>L: chunk text with ACL check
  L->>U: Ответ с цитатами
```

С точки зрения MCP transport security требования MCP к Streamable HTTP включают обязательную Origin‑валидацию и рекомендации по localhost bind + auth; это должно быть реализовано при поднятии HTTP‑сервера. citeturn3search0turn3search1

## Соответствие PRD по разделам

### Матрица “PRD → реализация”

Статусы:
- **Реализовано**: покрыто и работает end‑to‑end в текущем коде
- **Частично**: есть базовая реализация, но отсутствуют ключевые элементы PRD/есть ограничения
- **Отсутствует**: не реализовано (или указано, но фактически не действует)

| Раздел PRD | Статус в repo | Основные точки кода |
|---|---|---|
| Онтология/схема графа | Частично→почти реализовано | Neo4jGraphStore: Document/Chunk/Entity + CONTAINS/MENTIONS/DOCUMENTED_IN + доменные rel’ы; но ACL в graph не выражен |
| Ingestion | Реализовано (MVP/v1) | IngestionPipeline: filesystem + git diff + checksum + cleanup stale chunks |
| Chunking | Частично | char‑based `max_chars/overlap`; нет token/sentence boundary |
| Embeddings | Частично | LocalSentenceTransformerEmbedder + OpenAI‑compatible + fallback; нет батчинга/кэша/мульти‑векторов |
| Entity extraction | Частично | regex + простая canonicalization; доменные связи rule‑based (очень грубо) |
| Vector store | Частично→реализовано | QdrantVectorStore + in‑memory; фильтры tags/sources/updated_after не применяются; payload indexes не создаются |
| Graph store | Частично | Neo4jGraphStore + in‑memory; graph_expand не учитывает object‑level ACL |
| Fusion/rerank | Реализовано (простое) | Линейная fusion (vector/graph/memory) + lexical blend + CrossEncoder rerank; нет BM25/RRF/learned ranker |
| MCP tools/resources/prompts | Реализовано | kb.search / kb.graph_expand / kb.explain / kb.memory.* / kb.ingest.* + resources kb://* + prompts |
| Транспорт | Реализовано | FastMCP transports: stdio + streamable-http path `/mcp` |
| Auth/ACL | Частично | JWT (dual/strict) + deny-by-default ACL + resource ACL; не OAuth; graph не ACL‑aware |
| Observability | Частично | JSON logs, audit logger, metrics registry, request_id; нет экспорта метрик/OTel |
| Тесты | Реализовано (unit + harness) | pytest unit tests + `bench/run_benchmark.py` gates |

Ниже — “разбор по разделам” с указанием артефактов и коротких цитат.

### Разбор по разделам с привязкой к коду

> Формат ссылок на код: GitHub permalink (private repo) — откроется при наличии доступа.

**Онтология/схема графа** — *частично→почти реализовано*  
Имплементировано: `Document`, `Chunk`, `Entity`, рёбра `CONTAINS`, `MENTIONS`, `DOCUMENTED_IN`, плюс `DEPENDS_ON|CALLS|OWNS|IMPLEMENTS|AFFECTS`.  
Ключевой код: `kb_mcp/storage/neo4j_store.py` (методы `upsert_mentions`, `upsert_entity_relations`, `resolve_entities`, `expand`).  
Короткая цитата (создание нужных узлов/рёбер):
```python
"MERGE (d:Document {uri: $doc_uri, workspace_id: $workspace_id}) "
"MERGE (c:Chunk {uri: $chunk_uri, workspace_id: $workspace_id}) "
"MERGE (d)-[:CONTAINS]->(c) "
"MERGE (c)-[:MENTIONS]->(e) "
"MERGE (e)-[:DOCUMENTED_IN]->(d)"
```
Ссылка:
```text
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/storage/neo4j_store.py
```
Основной разрыв с PRD: object‑level ACL (на документ/чанк) в графовых узлах не записан и, соответственно, не фильтруется при `expand`. PRD требует server‑side ACL фильтрацию.  

**Ingestion** — *реализовано*  
Есть два инструмента ingestion (tools): `kb.ingest.filesystem` и `kb.ingest.git_diff` в MCP‑сервере. Внутри — инкрементальный pipeline на checksum, плюс удаление устаревших чанков из vector/graph/metadata.  
Код: `kb_mcp/ingest/pipeline.py`, `kb_mcp/server/app.py`, `kb_mcp/ingest/connectors/{filesystem,git}.py`.  
Цитата (checksum и пропуск без изменения):
```python
checksum = self._checksum(text)
prev = self._metadata.get_checksum(workspace_id=workspace_id, source_path=source_path)
if prev == checksum:
    continue
```
Ссылки:
```text
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/ingest/pipeline.py
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/server/app.py
```

**Chunking** — *частично*  
Реализован простой sliding window по символам с overlap.  
Код: `kb_mcp/ingest/chunking.py`.  
Цитата:
```python
def chunk_text(text: str, *, max_chars: int = 800, overlap: int = 120) -> list[dict[str, object]]:
```
Ссылка:
```text
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/ingest/chunking.py
```
Риски качества: char‑based chunking может резать предложения/смысловые блоки; практики chunking обычно включают sentence/token‑aware стратегии. citeturn4search6  

**Embeddings** — *частично*  
Есть embedder abstraction и два реалистичных режима: локальный sentence‑transformers и OpenAI‑совместимый HTTP `/embeddings`, плюс детерминированный fallback.  
Код: `kb_mcp/ingest/embeddings.py`, загрузка через `kb_mcp/bootstrap.py`.  
Цитата (локальный ST и нормализация):
```python
vectors = self._model.encode(texts, normalize_embeddings=True)
return [[float(v) for v in vec] for vec in vectors]
```
Ссылки:
```text
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/ingest/embeddings.py
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/bootstrap.py
```
Соответствие PRD: PRD подразумевает embeddings pipeline; реализовано. Но отсутствуют прод‑моменты: батч‑параметры/кэш/контроль модели/версии, а также мульти‑векторные схемы (например dense+sparse hybrid на стороне vector DB).

**Entity extraction** — *частично*  
Реализован regex‑extractor для таблиц вида `schema.table`, “символов” и кириллических терминов + rule‑based извлечение доменных рёбер на базе маркеров (“depends on/calls/…”).  
Код: `kb_mcp/ingest/entity_extract.py`.  
Цитата:
```python
_TABLE_RE = re.compile(r"\b([a-z_]+\.[a-z_]+)\b", re.IGNORECASE)
...
def extract_entity_relations(text: str, entity_uris: list[str]) -> list[dict[str, str]]:
```
Ссылка:
```text
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/ingest/entity_extract.py
```
Главные ограничения vs PRD: нет дедупликации/alias‑сети beyond trivial, нет human‑in‑the‑loop, а `extract_entity_relations` связывает “первые две сущности” и может создавать шум в графе (в PRD этот риск отдельно отмечен).

**Vector store** — *частично→реализовано*  
Есть полноценный backend для Qdrant и in‑memory backend; используется `query_points` с фильтрацией по `workspace_id` и `acl_allow`. Векторный размер проверяется на совпадение с embedder.dimensions.  
Код: `kb_mcp/storage/qdrant_store.py`.  
Цитата (query_points + filter):
```python
response = self._client.query_points(
    collection_name=collection_name,
    query=self._embedder.embed_query(query),
    query_filter=self._build_filter(filters),
    limit=top_k,
    with_payload=True,
)
```
Ссылка:
```text
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/storage/qdrant_store.py
```
С точки зрения native API Qdrant, `query_points` и фильтры — стандартная конструкция. citeturn4search9turn4search7  
Открытая дыра к PRD: `SearchFilters` включает `tags/sources/updated_after`, но `_build_filter` их не использует; также нет создания payload‑индексов, хотя Qdrant подчёркивает важность индексирования фильтруемых полей (и strict mode может запрещать фильтрацию по неиндексированным полям). citeturn4search0turn4search3turn4search2  

**Graph store** — *частично*  
Есть backend для Neo4j и in‑memory backend. В Neo4j используется `execute_query(... database_=..., routing_=READ)`; это корректно с точки зрения драйвера, но само по себе не является механизмом access control (Neo4j прямо предупреждает не использовать “read mode” как security). citeturn5search0  
Код: `kb_mcp/storage/neo4j_store.py`.  
Цитата (expand по переменной длине пути):
```python
node_query = (
  f"MATCH p=(a)-[*1..{bounded_depth}]-(b) "
  "WHERE a.uri IN $seed_uris ..."
)
```
Ссылка:
```text
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/storage/neo4j_store.py
```
Риск масштабирования: variable-length паттерны могут резко раздувать число путей/кандидатов; Neo4j рекомендует делать такие паттерны максимально специфичными/ограниченными для производительности. citeturn5search1  
ACL‑дырка: фильтр по `acl_allow` отсутствует на уровне графа (только workspace); если в рамках workspace требуется object‑level разграничение, `kb.graph_expand` способен раскрывать структуру связи.

**Fusion/rerank** — *реализовано (простое)*  
Fusion: линейное взвешивание (vector/graph/memory) + доп. lexical blend; затем rerank cross‑encoder (или fallback).  
Код: `kb_mcp/retrieval/fusion.py`, `kb_mcp/retrieval/hybrid.py`, `kb_mcp/retrieval/rerank.py`.  
Цитата (fusion weights):
```python
class FusionWeights:
    w_vector: float = 0.70
    w_graph: float = 0.20
    w_memory: float = 0.10
```
Цитата (rerank через пары (query, passage)):
```python
pairs = [(query, item.text or item.uri) for item in items]
raw_scores = self._model.predict(pairs)
```
Ссылки:
```text
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/retrieval/hybrid.py
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/retrieval/rerank.py
```
Это соответствует базовой best practice: cross‑encoder принимает **ровно два текста** (query, text) и применяется для rerank top‑k. citeturn7search0turn7search2  
Замечание: код дополнительно применяет sigmoid к тому, что возвращает `predict()`. У SentenceTransformers по умолчанию activation может уже быть sigmoid для num_labels=1; повторный sigmoid монотонен (ранжирование сохранит порядок), но “склеит” разницы. citeturn7search0turn7search12  

**MCP tools/resources/prompts** — *реализовано*  
MCP сервер объявляет:
- tools: `kb.search`, `kb.graph_expand`, `kb.explain`, `kb.memory.upsert/search/delete`, `kb.ingest.filesystem`, `kb.ingest.git_diff`
- resources: `kb://doc/{doc_id}`, `kb://chunk/{chunk_id}`, `kb://entity/{entity_id}`, `kb://memory/{memory_id}`, `kb://policy/tool-selection`
- prompts: `kb.answer_with_citations`, `kb.tool_selection_policy`, `kb.incident_triage`, `kb.memory_grounded_reply`  
Код: `kb_mcp/server/app.py`.  
Цитата (endpoint `/mcp` и Streamable HTTP):
```python
mcp = FastMCP(..., streamable_http_path="/mcp", ...)
```
Ссылка:
```text
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/server/app.py
```
С точки зрения MCP spec, корректно использовать tools discovery (`tools/list`) и tool invocation (`tools/call`). citeturn3search11  
Resources должны быть безопасны: URIs валидируются, права проверяются, чувствительные ресурсы защищаются. citeturn3search3turn3search7  
В этом репо ресурсы действительно перед выдачей проверяют ACL (`_resource_allowed`).  

**Транспорт** — *реализовано*  
Запуск: `kb_mcp/server/transport_http.py` и `kb_mcp/server/transport_stdio.py`.  
Код реализует Streamable HTTP (stateless) и stdio режим. Требования MCP к stdio — не писать ничего кроме MCP сообщений в stdout — обеспечиваются SDK‑уровнем, но это важно помнить при расширениях. citeturn3search0  
Ссылки:
```text
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/server/transport_http.py
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/server/transport_stdio.py
```

**Auth/ACL** — *частично*  
JWT‑auth с режимами `dual` и `strict` + server‑side ACL (deny‑by‑default).  
Код: `kb_mcp/security/auth.py`, `kb_mcp/security/acl.py`, enforcement в `kb_mcp/server/app.py` и в vector retrieval filter.  
Цитата (bearer token parsing):
```python
auth_value = headers.get("authorization")
if auth_value.lower().startswith("bearer "):
    token = auth_value[len(prefix):].strip()
```
Ссылка:
```text
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/security/auth.py
```
Официальная рекомендация MCP для HTTP‑authorization — OAuth‑2.1‑совместимая модель и обязательный `Authorization: Bearer ...` header на каждый запрос. citeturn3search2turn3search6  
Здесь OAuth не реализован (используется локальный JWT секрет), поэтому соответствие MCP authorization spec — **частичное** (есть bearer header, но нет OAuth flows/metadata/dynamic registration).

**Observability** — *частично*  
Есть:
- request id (contextvar) `ensure_request_id`
- audit logger с `params_hash`, latency, identity source
- in‑proc метрики (counters + p95 по таймерам)  
Код: `kb_mcp/observability/{audit,metrics,tracing}.py`, включение в `server/app.py`.  
Ссылки:
```text
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/observability/audit.py
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/observability/metrics.py
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/observability/tracing.py
```
Но нет: Prometheus endpoint, OpenTelemetry traces, распределённые корреляции с внешним LLM host.

**Тесты и KPI‑метрики** — *реализовано (unit + offline harness)*  
Есть unit tests на ACL/router/fallback/rerank/ingestion/persistence; есть benchmark harness, считающий Recall@10/nDCG@10/MRR и P95 latency gates (встроенные пороги совпадают с PRD).  
Код: `tests/*`, `bench/run_benchmark.py`.  
Ссылки:
```text
https://github.com/econolic/memorygraph_mcp/blob/main/bench/run_benchmark.py
https://github.com/econolic/memorygraph_mcp/blob/main/tests/test_hybrid_fallback.py
```

## Сильные стороны, слабые стороны и риски

### Сильные стороны

**Сильная интеграция с MCP primitives (tools/resources/prompts) + transport security.**  
Проект явно учитывает транспортные угрозы (DNS rebinding/Origin/allowlists) и поднимает `/mcp` как Streamable HTTP endpoint. Это соответствует явным предупреждениям MCP о том, что без Origin validation и auth локальные MCP‑сервера могут быть атакованы через DNS rebinding. citeturn3search0turn3search1  
Плюс — наличие policy‑ресурса `kb://policy/tool-selection` и prompt‑шаблонов, что заметно упрощает подключение LLM‑оркестратора.

**Правильный “shape” hybrid retrieval и корректный rerank API‑паттерн.**  
Cross‑encoder применяется на парах `(query, item.text)` (как и должен), и используется как reranker top‑N, что соответствует рекомендациям SentenceTransformers: cross‑encoder точнее, но дорогой, поэтому используется на top‑k кандидатов. citeturn7search2turn7search0  

**Инкрементальная ingestion и cleanup stale data.**  
Pipeline не только добавляет/обновляет, но и удаляет “stale” чанки во всех слоях. Это существенно снижает проблему “мусорного KB”, характерную для многих MVP.

**Наличие качественного benchmark harness с метриками PRD.**  
`bench/run_benchmark.py` измеряет Recall@10, nDCG@10, MRR и latency p95; сценарий gating на порогах PRD формализует миграцию от “работает” к “работает и держит качество”.

### Слабые стороны и потенциальные баги

**ACL‑консистентность между vector/metadata и graph — неполная.**  
Vector store фильтруется по `acl_allow`, resources/read тоже проверяют `acl_allow`. Но graph traversal фильтруется только `workspace_id`. Если внутри workspace допускаются разные ACL‑домены, `kb.graph_expand` может раскрывать факт существования документов/чанков/сущностей и их связи (пусть даже без текста). PRD требовал server‑side ACL везде.

**Фильтры `tags`, `sources`, `updated_after` в schema не реализованы в фактическом поиске.**  
Это ухудшает управляемость retrieval (нет “search scope”), мешает сегментации, мешает расследованиям инцидентов, и может приводить к ненужному расширению candidate set.

**Neo4j variable-length traversal потенциально дорог.**  
`MATCH p=(a)-[*1..depth]-(b)` даже при глубине ≤4 может взрываться на графах с высокой степенью, особенно если в одном workspace много документов и сущностей. Neo4j рекомендует делать такие запросы более специфичными (например, ограничивать типы отношений или добавлять pruning). citeturn5search1  

**Qdrant: нет создания payload indexes для фильтров.**  
Код активно использует фильтры по `workspace_id` и `acl_allow`. Qdrant подчёркивает, что payload поля не индексируются по умолчанию и что индексы следует создавать заранее; иначе фильтрация существенно ухудшает производительность, а strict mode может запрещать неиндексированную фильтрацию. citeturn4search0turn4search3turn4search2  

**Reranker: двойной sigmoid (вероятно) и отсутствие провайдера `llm`.**  
`RerankConfig.provider` присутствует (`cross_encoder|llm`), но фактическая реализация — всегда CrossEncoder (или fallback). Кроме того, `CrossEncoder.predict()` может уже возвращать sigmoid‑скоры для num_labels=1; повторная sigmoid‑трансформация может ухудшить калибровку (хотя порядок сохраняется). citeturn7search0turn7search12  

**Chunking может ухудшить качество evidence/snippet.**  
Текущий chunking — фиксированный по символам; для кода/SQL/markdown это часто приемлемо, но для текстовой документации качество часто лучше при sentence‑aware или semantic chunking (в примерах Qdrant учебных материалов это прямо сравнивается). citeturn4search6  

## Рекомендации и приоритетный roadmap

### Таблица roadmap

| Приоритет | Рекомендация | Ожидаемый эффект | Изменяемые файлы |
|---|---|---|---|
| P0 | Добавить object‑level ACL в граф (Document/Chunk/Entity) и фильтровать в `expand`/`resolve_entities`/`explain_uri` | Закрывает ключевой риск утечки через graph_expand | `kb_mcp/storage/neo4j_store.py`, `kb_mcp/storage/in_memory_graph.py`, `kb_mcp/ingest/pipeline.py`, `kb_mcp/server/app.py` |
| P0 | Реализовать filters `tags/sources/updated_after` end‑to‑end (ingestion → payload → vector/metadata → query_filter) | Управляемость retrieval, фильтрация по источникам/свежести | `kb_mcp/server/schemas.py`, `kb_mcp/ingest/pipeline.py`, `kb_mcp/storage/qdrant_store.py`, metadata store |
| P1 | Создавать payload indexes в Qdrant для `workspace_id`, `acl_allow`, `source`, `updated_at` (и др.) на старте | Производительность и совместимость со strict mode | `kb_mcp/storage/qdrant_store.py`, bootstrap init |
| P1 | Переписать graph expansion query: ограничить типы ребер по умолчанию, уйти от “полностью неориентированного” шаблона | Снижение cost/latency p95, меньше “шума” в граф бонусе | `kb_mcp/storage/neo4j_store.py` |
| P1 | Улучшить entity extraction: нормализация, stoplist, dedup, canonical_key стратегия по доменам (таблицы/сервисы/символы) | Меньше мусора в графе и в evidence.entities | `kb_mcp/ingest/entity_extract.py` |
| P2 | Добавить RRF как альтернативу линейной fusion, плюс опциональный BM25/sparse (Qdrant text search/BM25) | Рост recall без тяжёлого ML ranker | `kb_mcp/retrieval/hybrid.py`, новые модули `rrf.py` |
| P2 | Export метрик (Prometheus) + traces (OpenTelemetry) | Прод-эксплуатация, SLO, RCA | `kb_mcp/observability/*`, добавить новый tool/resource |
| P2 | OAuth‑совместимый auth для HTTP‑транспорта (как в MCP authorization spec) | Соответствие MCP best practice; SSO/Scoping | `kb_mcp/security/auth.py`, transport middleware |

### Конкретные файлы, которые почти наверняка будут правиться (ссылки)

```text
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/storage/neo4j_store.py
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/storage/qdrant_store.py
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/ingest/pipeline.py
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/retrieval/hybrid.py
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/server/app.py
https://github.com/econolic/memorygraph_mcp/blob/main/kb_mcp/server/schemas.py
```

### План тестов и метрик качества

Что уже есть:
- Recall@10, nDCG@10, MRR, P95 latency и “faithfulness proxy” через citation coverage в bench harness.

Что добавить (чтобы действительно удерживать качество на реальных данных):
- **Regression suite** на фиксированном “mini‑corpus” (20–50 документов) с ожидаемыми источниками.
- **Δ‑метрики по изменениям ingestion**: сколько чанков/сущностей добавилось/удалилось; рост графа.
- **Monitoring**: error rate graph backend, fallback ratio (`debug.fallback_mode`), latency per stage (vector/graph/rerank) уже есть в payload — нужно экспортировать.

Примеры тест‑кейсов (pytest, концептуальные):
- `test_graph_expand_enforces_acl_allow`: ingest 2 docs в одном workspace с разными `acl_allow`; убедиться, что graph_expand не возвращает узлы/ребра “чужого” документа.
- `test_updated_after_filter`: ingest doc с `updated_at=t1`, затем запрос с `updated_after=t2>t1` должен вернуть 0 результатов.
- `test_qdrant_payload_indexes_present`: при init коллекции создать/проверить payload index на `workspace_id` и `acl_allow` (настоящий integration test).

## MCP‑контракт, payload‑примеры, LLM‑flow и code skeletons

### Соответствие MCP spec и предложения по контракту

**Tools/list и tools/call.**  
MCP определяет механизмы discovery и вызова инструментов через JSON‑RPC методы `tools/list` и `tools/call`. citeturn3search11  

**Resources/read.**  
Resources должны иметь валидируемые URI, содержать content (text/blob) и учитывать security considerations (проверка прав доступа). citeturn3search3turn3search7  

**Streamable HTTP transport и безопасность.**  
MCP требует Origin validation (MUST) и рекомендует localhost bind (SHOULD) + auth. citeturn3search0turn3search1  
В repo добавлены allowlists hosts/origins и включена DNS rebinding защита через transport_security settings.

**Auth.**  
MCP authorization spec описывает OAuth‑2.1‑совместимый transport‑уровень; в repo — JWT‑auth (local secret). Для production‑совместимости с экосистемой MCP целесообразно либо строго документировать “локальный JWT режим”, либо добавить OAuth flow. citeturn3search2turn3search6  

### Примеры JSON‑RPC payloads

**Streamable HTTP: tools/list**
```http
POST /mcp HTTP/1.1
Accept: application/json, text/event-stream
Content-Type: application/json
Authorization: Bearer <jwt>

{"jsonrpc":"2.0","id":"1","method":"tools/list","params":{}}
```

**tools/call: kb.search (упрощённо под текущие schemas)**
```json
{
  "jsonrpc": "2.0",
  "id": "2",
  "method": "tools/call",
  "params": {
    "name": "kb.search",
    "arguments": {
      "payload": {
        "query": "Где документирован контракт API Z?",
        "mode": "hybrid",
        "top_k": 10,
        "workspace_id": "w1",
        "session_id": "s1",
        "include_memory": true,
        "filters": {
          "tags": [],
          "sources": [],
          "updated_after": null,
          "acl": { "subject": "u1", "roles": ["reader"], "workspace_id": "w1", "jwt_bearer": null }
        },
        "graph": { "expand_depth": 2, "edge_types": ["DEPENDS_ON", "DOCUMENTED_IN", "MENTIONS"], "max_nodes": 200 },
        "rerank": { "enabled": true, "provider": "cross_encoder", "top_n": 10 }
      }
    }
  }
}
```

**stdio transport** — тот же JSON‑RPC, но newline‑delimited. Важно: stdout сервера должен содержать только MCP‑сообщения. citeturn3search0  

### Рекомендуемый prompt template для LLM‑оркестратора

(Смысл совпадает с `docs/tool_selection_policy.md` и runtime prompt в `server/app.py`.)

```text
SYSTEM:
Ты работаешь через MCP KB.
1) Если вопрос проверяемый — сначала вызывай tools.
2) Приоритет: kb.memory.search -> kb.search -> kb.graph_expand (если связи) -> kb.explain (если нужно объяснение).
3) Каждое утверждение в ответе должно иметь citation на kb://chunk/... (и span).
4) Если evidence отсутствует — явно сообщи "evidence не найдено".
5) Если граф недоступен — ответ только по vector evidence и отмечай ограничение.
6) Не сохраняй память без citations и confidence >= threshold.
```

### Skeletons кода для доработок

Ниже — “скелеты” именно под зоны роста (ACL‑graph, filters, RRF, tool handlers). Они совместимы с текущей архитектурой проекта.

#### Ingestion worker с очередью (для масштабирования)

```python
from __future__ import annotations

from dataclasses import dataclass
from queue import Queue
from threading import Thread
from typing import Callable, Optional


@dataclass(frozen=True)
class IngestTask:
    root: str
    workspace_id: str
    acl_allow: list[str]
    changed_files: Optional[list[str]] = None


class IngestWorker:
    def __init__(
        self,
        *,
        queue: Queue[IngestTask],
        handler: Callable[[IngestTask], dict[str, int]],
        num_threads: int = 2,
    ) -> None:
        self._q = queue
        self._handler = handler
        self._threads = [Thread(target=self._run, daemon=True) for _ in range(num_threads)]

    def start(self) -> None:
        for t in self._threads:
            t.start()

    def _run(self) -> None:
        while True:
            task = self._q.get()
            try:
                self._handler(task)
            finally:
                self._q.task_done()
```

#### Интерфейсы retriever’ов (как contracts для тестирования)

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Candidate:
    uri: str
    text: str
    score: float
    meta: dict[str, object]


class VectorRetriever(Protocol):
    def retrieve(self, *, query: str, k: int, filters: dict[str, object]) -> list[Candidate]:
        raise NotImplementedError


class GraphRetriever(Protocol):
    def seed_entities(self, *, query: str, filters: dict[str, object]) -> list[str]:
        raise NotImplementedError

    def expand(self, *, seeds: list[str], depth: int, filters: dict[str, object]) -> dict[str, float]:
        """Return bonus/prior over URIs (chunk/entity)."""
        raise NotImplementedError
```

#### Fusion: добавить RRF как альтернативу линейной модели

RRF полезен тем, что не требует калибровки score‑шкал (работает по рангу). Применяется во многих hybrid‑системах. citeturn7search11turn7search14  

```python
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class RankedList:
    uris: list[str]


def rrf_fuse(*lists: RankedList, k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = defaultdict(float)
    for lst in lists:
        for rank, uri in enumerate(lst.uris, start=1):
            scores[uri] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)
```

#### Исправление object‑level ACL в graph store (идея)

```python
# Псевдо-Cypher подход:
# 1) записывать acl_allow в Document и Chunk
# 2) в expand добавлять:
#    AND any(sub IN coalesce(n.acl_allow, []) WHERE sub IN $subjects)

def build_acl_predicate() -> str:
    return "any(sub IN coalesce(n.acl_allow, []) WHERE sub IN $subjects)"
```

#### MCP tool handler: нормализовать filters и запрещать “мертвые” фильтры

```python
def normalize_filters(filters: dict[str, object]) -> dict[str, object]:
    # Fail-fast: если schema объявляет фильтр, но backend не умеет — лучше явная ошибка/лог.
    supported_keys = {"workspace_id", "acl_subject", "tags", "sources", "updated_after"}
    unknown = set(filters) - supported_keys
    if unknown:
        raise ValueError(f"unsupported_filters: {sorted(unknown)}")
    return filters
```

#### Клиент‑пример вызова MCP tools (HTTP)

```python
from __future__ import annotations

from typing import Any
import httpx


def tools_call(
    *,
    base_url: str,
    token: str,
    name: str,
    arguments: dict[str, Any],
    rpc_id: str = "1",
) -> dict[str, Any]:
    payload = {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    r = httpx.post(f"{base_url}/mcp", json=payload, headers=headers, timeout=30.0)
    r.raise_for_status()
    return r.json()
```

### Security checklist и пример ACL policy

Transport‑уровень (HTTP):
- Origin validation (обязательно). citeturn3search0  
- localhost bind по умолчанию для локального режима (рекомендация). citeturn3search0  
- аутентификация на каждом HTTP запросе через bearer header. citeturn3search6  

Data‑уровень:
- server‑side ACL enforcement для tools и resources (в PRD это must).  
- единая ACL‑логика для vector/graph/metadata (сейчас не полностью выполнено).  

Пример policy (deny‑by‑default):
```yaml
policy_version: "2026-02-21"
default: deny
workspaces:
  w1:
    subjects:
      u1:
        roles: ["reader"]
      u2:
        roles: ["admin"]
    roles:
      reader:
        allow_tools: ["kb.search", "kb.memory.search", "kb.graph_expand", "kb.explain"]
      admin:
        allow_tools: ["kb.search", "kb.graph_expand", "kb.explain", "kb.ingest.filesystem", "kb.ingest.git_diff",
                      "kb.memory.upsert", "kb.memory.delete"]
```

### CI/CD и deployment

**docker-compose** уже есть в репо (Qdrant + Neo4j + MCP). Для Qdrant важно помнить про фильтруемые поля и payload indexing (иначе latency под фильтрами деградирует). citeturn4search0turn4search3  

Kubernetes skeleton (минимальный):
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: hybrid-kb-mcp
spec:
  replicas: 2
  selector:
    matchLabels:
      app: hybrid-kb-mcp
  template:
    metadata:
      labels:
        app: hybrid-kb-mcp
    spec:
      containers:
        - name: mcp
          image: your-registry/hybrid-kb-mcp:0.1.0
          ports:
            - containerPort: 8080
          env:
            - name: KB_AUTH_MODE
              value: "strict"
            - name: KB_HTTP_HOST
              value: "0.0.0.0"
            - name: KB_HTTP_PORT
              value: "8080"
            # секреты (jwt secret, neo4j password, qdrant api key) через Secret refs
---
apiVersion: v1
kind: Service
metadata:
  name: hybrid-kb-mcp
spec:
  selector:
    app: hybrid-kb-mcp
  ports:
    - port: 80
      targetPort: 8080
```

**Наблюдаемость (metrics/traces/logs)**: сейчас есть JSON‑логи и audit‑логгер; для production обычно добавляют Prometheus endpoint и OpenTelemetry traces. Это облегчит SLO и RCA, особенно при деградации graph‑backend (fallback). Также стоит учитывать, что переменные‑длины graph traversal могут стать главным источником tail latency, и это нужно мониторить отдельно. citeturn5search1turn5search4

