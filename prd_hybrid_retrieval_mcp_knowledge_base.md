# PRD — Hybrid Retrieval MCP для базы знаний (Vector + Graph)

**Целевая платформа:** LLM‑host (любой), MCP‑сервер (Python), Vector Store + Graph DB

---

## 1) Контекст и проблема

### 1.1 Что болит
- Знания о системе (доки, код, ADR, runbooks, тикеты, схемы) расползаются по источникам.
- LLM без внешней памяти превращается в генератор «правдоподобных» догадок.
- Обычный RAG (только vector) часто теряет **структурные связи**: зависимости сервисов, владельцы, контракты, влияние изменений.

### 1.2 Почему Hybrid Retrieval
- **Vector retrieval** отвечает на «где это написано».
- **Graph retrieval** отвечает на «что с чем связано».
- Вместе они дают: релевантность + объяснимость (пути в графе) + меньше пропусков.

---

## 2) Цели и KPI

### 2.1 Цели (MVP → v1)
1. Единый MCP‑endpoint для поиска знаний (hybrid retrieval).
2. Возвращать доказательства (evidence) с цитатами и provenance.
3. Поддержать ACL/фильтры доступа и аудит вызовов.
4. Инкрементальный ingestion (обновления по diff).

### 2.2 KPI качества
- **Retrieval:** Recall@10 ≥ 0.85 на тест‑наборе запросов; nDCG@10 ≥ 0.75.
- **Latency:** P95 `kb.search(hybrid)` ≤ 1.5s (без rerank‑LLM), ≤ 3.5s (с rerank).
- **Faithfulness:** ≥ 0.9 доля утверждений с привязкой к evidence (по ручной разметке).
- **Operations:** 0 P0 инцидентов утечки данных (ACL).

---

## 3) Не‑цели
- Полноценный knowledge graph «про всё в мире».
- Автоматическое принятие решений/изменение прод‑систем.
- Запись «фактов» LLM без валидации и контроля (write‑back только ограниченный и позже).

---

## 4) Персоны и сценарии

### 4.1 Персоны
- **Data/BI/DS инженер**: ищет определения метрик, пайплайны, таблицы, SLA.
- **DevOps/SRE**: ищет runbooks, зависимости сервисов, причины падений.
- **Product/BA**: ищет требования, ADR, историю решений.

### 4.2 Топ‑сценарии
1. «Как запускается пайплайн X? Какие зависимости и входные таблицы?»
2. «Почему упал job Y? Где описана типовая процедура?»
3. «Где документирован контракт API Z? Какие сервисы зависят от него?»
4. «Найди все места, где упоминается сущность `lagerid` в план/факт/списания»

---

## 5) Обзор решения

### 5.1 Компоненты
- **MCP Server** (Python):
  - Tools: `kb.search`, `kb.graph_expand`, `kb.explain`
  - Resources: чтение `kb://doc/...`, `kb://chunk/...`, `kb://entity/...`
  - Prompts (опционально): шаблоны «ответ с цитатами», «triage инцидента»
- **Vector Store**: embeddings по чанкам (Qdrant/pgvector/Weaviate).
- **Graph DB**: сущности/связи (Neo4j/Memgraph/Neptune).
- **Ingestion Pipeline**:
  - коннекторы → нормализация → chunking → embeddings → entity extraction → граф
- **(Опционально) Reranker**: cross‑encoder или LLM rerank.

### 5.2 High‑level flow (runtime)
1. Запрос пользователя → `kb.search(mode=hybrid)`.
2. Vector top‑K → кандидаты.
3. Из кандидатов/вопроса → seed entities → graph expansion.
4. Fusion + (опц.) rerank → evidence pack.
5. LLM формирует ответ, привязывая утверждения к evidence.

---

## 6) Данные и модель знаний

### 6.1 Узлы
- `Document`: id, title, source, updated_at, tags[], acl, checksum
- `Chunk`: id, doc_id, text, span{start,end}, embedding_ref, hash
- `Entity`: id, type, name, aliases[], canonical_key

### 6.2 Рёбра
- `(Document)-[:CONTAINS]->(Chunk)`
- `(Chunk)-[:MENTIONS]->(Entity)`
- `(Entity)-[:DEPENDS_ON|CALLS|OWNS|IMPLEMENTS|AFFECTS]->(Entity)`
- `(Entity)-[:DOCUMENTED_IN]->(Document)`

### 6.3 Ключи и дедуп
- `Entity.canonical_key`: например `repo:path:symbol`, `table:schema:name`.
- Дедуп: alias‑словарь + нормализация + fuzzy‑match с ручным «golden id» режимом позже.

---

## 7) MCP контракт (Tools/Resources/Prompts)

> **Примечание:** ниже схема «как должно выглядеть», а не «как это точно названо в любом конкретном SDK». Важна стабильность контракта между LLM‑host и сервером.

### 7.1 Tool: `kb.search`
**Назначение:** Hybrid retrieval (vector + graph + опционально BM25), возвращает evidence.

**Input (JSON):**
```json
{
  "query": "string",
  "mode": "vector|graph|hybrid",
  "top_k": 20,
  "filters": {
    "tags": ["string"],
    "sources": ["string"],
    "updated_after": "2026-01-01T00:00:00Z",
    "acl": {"subject": "user_or_role"}
  },
  "graph": {
    "expand_depth": 2,
    "edge_types": ["DEPENDS_ON", "DOCUMENTED_IN", "MENTIONS"],
    "max_nodes": 200
  },
  "rerank": {
    "enabled": true,
    "provider": "cross_encoder|llm",
    "top_n": 10
  }
}
```

**Output (JSON):**
```json
{
  "query_id": "uuid",
  "results": [
    {
      "uri": "kb://chunk/ch_123",
      "title": "Документ / Раздел",
      "snippet": "...",
      "score": 0.87,
      "score_breakdown": {"vector": 0.81, "graph": 0.12, "bm25": 0.0, "rerank": 0.87},
      "citations": [
        {"uri": "kb://doc/doc_9", "chunk_uri": "kb://chunk/ch_123", "span": {"start": 120, "end": 420}}
      ],
      "entities": [
        {"uri": "kb://entity/en_table_sales", "type": "Table", "name": "sales"}
      ]
    }
  ],
  "debug": {
    "latency_ms": {"vector": 120, "graph": 90, "fusion": 15, "rerank": 220},
    "filters_applied": true
  }
}
```

### 7.2 Tool: `kb.graph_expand`
**Назначение:** вернуть подграф/пути вокруг seed.

**Input:**
```json
{
  "seed_entities": ["kb://entity/..."],
  "depth": 2,
  "edge_types": ["DEPENDS_ON", "CALLS"],
  "filters": {"acl": {"subject": "user_or_role"}}
}
```

**Output:**
```json
{
  "nodes": [{"uri": "kb://entity/...", "type": "Service", "name": "svc"}],
  "edges": [{"src": "kb://entity/a", "rel": "DEPENDS_ON", "dst": "kb://entity/b"}],
  "paths": [["kb://entity/a", "DEPENDS_ON", "kb://entity/b"]]
}
```

### 7.3 Tool: `kb.explain`
**Назначение:** объяснить, почему эти результаты релевантны (score + graph path).

**Input:**
```json
{"uris": ["kb://chunk/ch_123", "kb://entity/en_svc"]}
```

**Output:**
```json
{
  "explanations": [
    {
      "uri": "kb://chunk/ch_123",
      "reasons": [
        {"type": "vector", "detail": "cosine=0.81"},
        {"type": "graph", "detail": "Entity(Service X) -> DOCUMENTED_IN -> Document Y"}
      ]
    }
  ]
}
```

### 7.4 Resources
- `kb://doc/{doc_id}` → полный текст/метаданные
- `kb://chunk/{chunk_id}` → точный фрагмент + span
- `kb://entity/{entity_id}` → карточка сущности + связи

### 7.5 Prompts (опционально)
- `kb.answer_with_citations`
- `kb.incident_triage`

---

## 8) Требования

### 8.1 Functional requirements
1. `kb.search` поддерживает `mode=vector|graph|hybrid`.
2. Возвращает **evidence** с `citations` и `resources`‑URI.
3. Поддержка ACL фильтрации **на стороне сервера**.
4. Логирование всех tool calls (кто, что, когда, latency, сколько результатов).
5. Ingestion: добавление/обновление документов, инкрементальные апдейты.

### 8.2 Non‑functional requirements
- P95 latency см. KPI.
- Надёжность: graceful degradation если граф недоступен (fallback на vector).
- Безопасность: запрет утечки, запрет произвольных запросов в БД без фильтров.

---

## 9) Архитектура (уровень модулей)

### 9.1 Runtime modules
- `Router` → определяет режим поиска.
- `VectorRetriever` → top‑K.
- `EntityResolver` → извлекает/нормализует seed entities.
- `GraphRetriever` → k‑hop expansion.
- `FusionRanker` → комбинирование score.
- `Reranker` → опционально.
- `EvidenceBuilder` → формирует выходные структуры + URI.

### 9.2 Ingestion modules
- `Connectors` → Git/Wiki/Drive/Tickets.
- `Parser` → normalize.
- `Chunker`.
- `Embedder`.
- `EntityExtractor`.
- `GraphWriter` / `VectorWriter`.

---

## 10) Безопасность, ACL, аудит

- **ACL объектно:** `Document.acl` + производная для chunks/entities.
- **Policy:** deny‑by‑default, allow‑list ролей/пользователей.
- **Audit log:** хранить `subject`, `tool`, `params_hash`, `result_count`, `latency`, `timestamp`.
- **Secrets:** никогда не отдавать секреты в resources/read (маскирование).

---

## 11) Наблюдаемость
- Метрики: latency per stage, error rate, top queries, cache hit ratio.
- Трейсинг: request_id коррелирует с query_id.
- Логи: structured JSON.

---

## 12) Оценка качества (offline)
- Набор эталонных запросов: 100–300.
- Метрики retrieval: Recall@K, nDCG@K, MRR.
- Валидация faithfulness: ручная разметка 30–50 ответов на релиз.

---

## 13) Риски
- «Грязная» онтология → граф расширяет мусор.
- Дубликаты сущностей → граф становится неинформативным.
- LLM‑extraction без валидации → выдуманные связи.

---

## 14) Milestones

### MVP (2–4 недели)
- Vector search + простая entity extraction (regex/словарь).
- Graph: базовые узлы/рёбра, expansion depth≤2.
- MCP tools/resources.

### v1 (4–8 недель)
- Rerank (cross‑encoder).
- Инкрементальный ingestion.
- ACL + аудит.

### v2
- Write‑back (ограниченный), версии знаний, human‑in‑the‑loop.

---

# Appendix A — Репозиторий и скелеты кода

## A1) Структура проекта
```text
hybrid-kb-mcp/
  pyproject.toml
  README.md
  kb_mcp/
    __init__.py
    config.py
    logging.py
    server/
      __init__.py
      app.py              # MCP endpoints (tools/resources/prompts)
      transport_http.py   # Streamable HTTP
      transport_stdio.py  # stdio
      schemas.py          # pydantic модели
    retrieval/
      __init__.py
      router.py
      fusion.py
      vector_store.py
      graph_store.py
      hybrid.py
      rerank.py
      evidence.py
    ingest/
      __init__.py
      pipeline.py
      chunking.py
      embeddings.py
      entity_extract.py
      connectors/
        __init__.py
        git.py
        filesystem.py
    security/
      __init__.py
      acl.py
      redact.py
    observability/
      __init__.py
      metrics.py
      tracing.py
  tests/
    test_fusion.py
    test_router.py
    test_acl.py
```

---

## A2) pyproject.toml (скелет)
```toml
[project]
name = "hybrid-kb-mcp"
version = "0.1.0"
description = "Hybrid Retrieval MCP server (vector + graph)"
requires-python = ">=3.11"

dependencies = [
  "pydantic>=2.6",
  "fastapi>=0.110",
  "uvicorn>=0.27",
  "httpx>=0.27",
  "orjson>=3.9",
  "tenacity>=8.2",
  "python-dotenv>=1.0",
]

[project.optional-dependencies]
neo4j = ["neo4j>=5.20"]
qdrant = ["qdrant-client>=1.9"]
pgvector = ["psycopg[binary]>=3.1", "sqlalchemy>=2.0"]

dev = [
  "pytest>=8.0",
  "pytest-cov>=4.1",
  "ruff>=0.3",
  "mypy>=1.8",
]

[tool.ruff]
line-length = 100

[tool.mypy]
python_version = "3.11"
strict = true
```

---

## A3) Конфиг
```python
# kb_mcp/config.py

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    """Runtime configuration for the MCP knowledge base server."""

    service_name: str = "hybrid-kb-mcp"
    http_host: str = "0.0.0.0"
    http_port: int = 8080

    vector_backend: str = "qdrant"  # qdrant|pgvector|weaviate
    graph_backend: str = "neo4j"    # neo4j|memgraph

    # Timeouts
    vector_timeout_s: float = 1.0
    graph_timeout_s: float = 1.0
    rerank_timeout_s: float = 2.0

    # Retrieval defaults
    default_top_k: int = 20
    max_top_k: int = 100
    default_expand_depth: int = 2
    max_expand_depth: int = 3

    # Security
    deny_by_default: bool = True
```

---

## A4) Pydantic схемы для tool inputs/outputs
```python
# kb_mcp/server/schemas.py

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class AclSubject(BaseModel):
    subject: str = Field(..., description="User ID or role name")


class SearchFilters(BaseModel):
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    updated_after: Optional[datetime] = None
    acl: Optional[AclSubject] = None


class GraphParams(BaseModel):
    expand_depth: int = 2
    edge_types: list[str] = Field(default_factory=list)
    max_nodes: int = 200


class RerankParams(BaseModel):
    enabled: bool = False
    provider: Literal["cross_encoder", "llm"] = "cross_encoder"
    top_n: int = 10


class KbSearchInput(BaseModel):
    query: str
    mode: Literal["vector", "graph", "hybrid"] = "hybrid"
    top_k: int = 20
    filters: SearchFilters = Field(default_factory=SearchFilters)
    graph: GraphParams = Field(default_factory=GraphParams)
    rerank: RerankParams = Field(default_factory=RerankParams)


class Span(BaseModel):
    start: int
    end: int


class Citation(BaseModel):
    uri: str
    chunk_uri: str
    span: Span


class EntityRef(BaseModel):
    uri: str
    type: str
    name: str


class SearchResult(BaseModel):
    uri: str
    title: str
    snippet: str
    score: float
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    citations: list[Citation] = Field(default_factory=list)
    entities: list[EntityRef] = Field(default_factory=list)


class KbSearchOutput(BaseModel):
    query_id: str
    results: list[SearchResult]
    debug: dict[str, Any] = Field(default_factory=dict)
```

---

## A5) Интерфейсы хранилищ
```python
# kb_mcp/retrieval/vector_store.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class VectorHit:
    chunk_id: str
    score: float


class VectorStore(Protocol):
    """Abstract interface for vector similarity search."""

    def search(self, query: str, top_k: int, filters: dict[str, object]) -> list[VectorHit]:
        raise NotImplementedError


# kb_mcp/retrieval/graph_store.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GraphNode:
    uri: str
    type: str
    name: str


@dataclass(frozen=True)
class GraphEdge:
    src: str
    rel: str
    dst: str


class GraphStore(Protocol):
    """Abstract interface for graph traversal and entity lookups."""

    def expand(self, seed_uris: list[str], depth: int, edge_types: list[str], filters: dict[str, object]) -> tuple[list[GraphNode], list[GraphEdge]]:
        raise NotImplementedError

    def resolve_entities(self, query: str, filters: dict[str, object]) -> list[str]:
        """Return entity URIs relevant to the query (via FT search, alias match, etc.)."""
        raise NotImplementedError
```

---

## A6) Router + Fusion + Hybrid retrieval
```python
# kb_mcp/retrieval/router.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Mode = Literal["vector", "graph", "hybrid"]


@dataclass(frozen=True)
class RoutedQuery:
    mode: Mode


class QueryRouter:
    """Heuristic router. Replace with a classifier later if needed."""

    def route(self, query: str, requested: Mode) -> RoutedQuery:
        if requested != "hybrid":
            return RoutedQuery(mode=requested)

        structural_markers = ("завис", "dependency", "кто использует", "связ", "влия")
        if any(m in query.lower() for m in structural_markers):
            return RoutedQuery(mode="hybrid")

        return RoutedQuery(mode="hybrid")


# kb_mcp/retrieval/fusion.py

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FusionWeights:
    w_vector: float = 0.75
    w_graph: float = 0.25


def fuse_scores(
    *,
    vector_score: float,
    graph_score: float,
    weights: FusionWeights,
) -> float:
    """Linear fusion. Replace with learned ranker later."""
    return weights.w_vector * vector_score + weights.w_graph * graph_score


# kb_mcp/retrieval/hybrid.py

from __future__ import annotations

import time
from dataclasses import dataclass

from kb_mcp.retrieval.fusion import FusionWeights, fuse_scores
from kb_mcp.retrieval.graph_store import GraphStore
from kb_mcp.retrieval.vector_store import VectorStore


@dataclass(frozen=True)
class HybridDebug:
    vector_ms: int
    graph_ms: int
    fusion_ms: int


class HybridRetriever:
    """Hybrid retrieval: vector top-K + graph expansion + fusion."""

    def __init__(
        self,
        vector_store: VectorStore,
        graph_store: GraphStore,
        weights: FusionWeights | None = None,
    ) -> None:
        self._vector = vector_store
        self._graph = graph_store
        self._weights = weights or FusionWeights()

    def search(
        self,
        query: str,
        top_k: int,
        filters: dict[str, object],
        depth: int,
        edge_types: list[str],
    ) -> tuple[list[dict[str, object]], HybridDebug]:
        t0 = time.perf_counter()
        v_hits = self._vector.search(query=query, top_k=top_k, filters=filters)
        t1 = time.perf_counter()

        seed_entities = self._graph.resolve_entities(query=query, filters=filters)
        nodes, edges = self._graph.expand(seed_uris=seed_entities, depth=depth, edge_types=edge_types, filters=filters)
        t2 = time.perf_counter()

        # Simple graph scoring placeholder: if a chunk/entity is in the expanded graph, add a bonus.
        graph_bonus: dict[str, float] = {n.uri: 1.0 for n in nodes}

        fused: list[dict[str, object]] = []
        for hit in v_hits:
            g = graph_bonus.get(f"kb://chunk/{hit.chunk_id}", 0.0)
            score = fuse_scores(vector_score=hit.score, graph_score=g, weights=self._weights)
            fused.append({"chunk_id": hit.chunk_id, "score": score, "vector": hit.score, "graph": g})

        fused.sort(key=lambda x: float(x["score"]), reverse=True)
        t3 = time.perf_counter()

        debug = HybridDebug(
            vector_ms=int((t1 - t0) * 1000),
            graph_ms=int((t2 - t1) * 1000),
            fusion_ms=int((t3 - t2) * 1000),
        )
        return fused[:top_k], debug
```

---

## A7) Evidence builder (URI + citations)
```python
# kb_mcp/retrieval/evidence.py

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EvidenceItem:
    uri: str
    title: str
    snippet: str
    score: float
    score_breakdown: dict[str, float]


class EvidenceBuilder:
    """Builds final evidence objects from chunk IDs and metadata store."""

    def build(self, *, chunk_id: str, score: float, breakdown: dict[str, float]) -> EvidenceItem:
        # TODO: fetch document title, chunk text, span, entities, citations.
        uri = f"kb://chunk/{chunk_id}"
        title = "TODO: title"
        snippet = "TODO: snippet"
        return EvidenceItem(uri=uri, title=title, snippet=snippet, score=score, score_breakdown=breakdown)
```

---

## A8) ACL (скелет)
```python
# kb_mcp/security/acl.py

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AccessContext:
    subject: str


class AclService:
    """Server-side ACL enforcement. Deny-by-default if configured."""

    def __init__(self, deny_by_default: bool = True) -> None:
        self._deny = deny_by_default

    def can_read_doc(self, ctx: AccessContext, doc_acl: dict[str, object]) -> bool:
        # TODO: implement role/user policy.
        if not doc_acl:
            return not self._deny
        allowed = set(map(str, doc_acl.get("allow", [])))
        return ctx.subject in allowed

    def apply_filters(self, ctx: AccessContext, filters: dict[str, object]) -> dict[str, object]:
        # Attach subject to filters for downstream stores.
        out = dict(filters)
        out["acl_subject"] = ctx.subject
        return out
```

---

## A9) MCP server (HTTP) — скелет
```python
# kb_mcp/server/app.py

from __future__ import annotations

import uuid
from typing import Any

from fastapi import FastAPI

from kb_mcp.config import AppConfig
from kb_mcp.retrieval.evidence import EvidenceBuilder
from kb_mcp.retrieval.hybrid import HybridRetriever
from kb_mcp.retrieval.router import QueryRouter
from kb_mcp.security.acl import AccessContext, AclService
from kb_mcp.server.schemas import KbSearchInput, KbSearchOutput, SearchResult


def create_app(
    cfg: AppConfig,
    retriever: HybridRetriever,
    evidence_builder: EvidenceBuilder,
    acl: AclService,
) -> FastAPI:
    """Create HTTP app exposing MCP-like endpoints.

    Note: concrete MCP transport framing may differ by host; keep the tool contract stable.
    """

    app = FastAPI(title=cfg.service_name)
    router = QueryRouter()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # ---- Tools (minimalistic) ----

    @app.post("/tools/kb.search")
    def kb_search(payload: KbSearchInput) -> KbSearchOutput:
        # In real deployment: ctx.subject comes from auth token.
        ctx = AccessContext(subject=payload.filters.acl.subject if payload.filters.acl else "anonymous")
        filters = acl.apply_filters(ctx, payload.filters.model_dump())

        routed = router.route(payload.query, payload.mode)

        if routed.mode == "hybrid":
            fused, debug = retriever.search(
                query=payload.query,
                top_k=payload.top_k,
                filters=filters,
                depth=payload.graph.expand_depth,
                edge_types=payload.graph.edge_types,
            )
        else:
            # TODO: implement pure vector or pure graph mode
            fused, debug = [], None

        results: list[SearchResult] = []
        for item in fused:
            ev = evidence_builder.build(
                chunk_id=str(item["chunk_id"]),
                score=float(item["score"]),
                breakdown={
                    "vector": float(item.get("vector", 0.0)),
                    "graph": float(item.get("graph", 0.0)),
                },
            )
            results.append(
                SearchResult(
                    uri=ev.uri,
                    title=ev.title,
                    snippet=ev.snippet,
                    score=ev.score,
                    score_breakdown=ev.score_breakdown,
                )
            )

        return KbSearchOutput(
            query_id=str(uuid.uuid4()),
            results=results,
            debug={"latency_ms": debug.__dict__ if debug else {}, "filters_applied": True},
        )

    return app
```

---

## A10) Запуск HTTP сервера
```python
# kb_mcp/server/transport_http.py

from __future__ import annotations

import uvicorn

from kb_mcp.config import AppConfig
from kb_mcp.server.app import create_app


def run_http(cfg: AppConfig) -> None:
    # TODO: wire real stores here.
    raise NotImplementedError


if __name__ == "__main__":
    cfg = AppConfig()
    uvicorn.run("kb_mcp.server.transport_http:app", host=cfg.http_host, port=cfg.http_port, reload=False)
```

---

## A11) Тесты (пример)
```python
# tests/test_fusion.py

from __future__ import annotations

from kb_mcp.retrieval.fusion import FusionWeights, fuse_scores


def test_fuse_scores_linear() -> None:
    score = fuse_scores(vector_score=0.8, graph_score=0.2, weights=FusionWeights(0.75, 0.25))
    assert abs(score - (0.8 * 0.75 + 0.2 * 0.25)) < 1e-9
```

---

# Appendix B — Пояснения по «как довести до прод» (коротко)

1. Реальный MCP framing: под твой LLM‑host (stdio или HTTP). Контракт tools/resources держи стабильным.
2. ACL и аудит: реализовать до подключения приватных источников.
3. Entity extraction: сначала deterministic (парсеры/словарь), LLM‑extraction позже и только с валидацией.
4. Fusion/rerank: начать с линейного, затем обучить ranker на логах.

