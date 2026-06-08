from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ErrorCode = Literal[
    "VALIDATION_ERROR",
    "NOT_FOUND",
    "PERMISSION_DENIED",
    "RATE_LIMITED",
    "TIMEOUT",
    "UPSTREAM_UNAVAILABLE",
    "BUSINESS_RULE_VIOLATION",
    "CONFLICT",
    "UNKNOWN_ERROR",
]


class ContractFields(BaseModel):
    ok: bool = True
    error_code: ErrorCode | None = None
    error_detail: str | None = None
    recoverable: bool | None = None
    next_action: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class AclSubject(BaseModel):
    subject: str = "anonymous"
    roles: list[str] = Field(default_factory=list)
    workspace_id: str = "default"
    jwt_bearer: str | None = None


class SearchFilters(BaseModel):
    tags: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    updated_after: datetime | None = None
    acl: AclSubject = Field(default_factory=AclSubject)


class GraphParams(BaseModel):
    expand_depth: int = 2
    edge_types: list[str] = Field(default_factory=list)
    max_nodes: int = 200


class RerankParams(BaseModel):
    enabled: bool = True
    provider: Literal["cross_encoder", "llm"] = "cross_encoder"
    top_n: int = 10


class KbSearchInput(BaseModel):
    query: str
    mode: Literal["vector", "graph", "hybrid"] = "hybrid"
    top_k: int = 20
    workspace_id: str
    session_id: str
    include_memory: bool = True
    filters: SearchFilters
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


class MemoryHit(BaseModel):
    uri: str
    score: float
    text: str
    citations: list[dict[str, Any]] = Field(default_factory=list)


class KbSearchOutput(ContractFields):
    query_id: str
    results: list[SearchResult]
    memory_hits: list[MemoryHit] = Field(default_factory=list)
    decision_trace: dict[str, Any] = Field(default_factory=dict)
    debug: dict[str, Any] = Field(default_factory=dict)


class KbGraphExpandInput(BaseModel):
    seed_entities: list[str]
    depth: int = 2
    edge_types: list[str] = Field(default_factory=list)
    max_nodes: int = 200
    workspace_id: str
    subject: str = ""


class KbGraphExpandOutput(ContractFields):
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, str]] = Field(default_factory=list)
    paths: list[list[str]] = Field(default_factory=list)


class KbExplainInput(BaseModel):
    uris: list[str]
    workspace_id: str
    subject: str = ""


class KbExplainOutput(ContractFields):
    explanations: list[dict[str, Any]] = Field(default_factory=list)


class MemoryUpsertItem(BaseModel):
    type: Literal["summary", "fact", "decision", "preference"]
    text: str
    citations: list[dict[str, Any]] = Field(default_factory=list)
    confidence: float
    entity_uris: list[str] = Field(default_factory=list)


class KbMemoryUpsertInput(BaseModel):
    workspace_id: str
    subject: str = ""
    session_id: str
    items: list[MemoryUpsertItem]
    idempotency_key: str | None = None


class KbMemoryUpsertOutput(ContractFields):
    stored_ids: list[str]
    validation_report: dict[str, list[str]] = Field(default_factory=dict)


class KbMemorySearchInput(BaseModel):
    query: str
    workspace_id: str
    subject: str = ""
    session_id: str
    top_k: int = 10


class KbMemorySearchOutput(ContractFields):
    results: list[MemoryHit]


class KbMemoryDeleteInput(BaseModel):
    workspace_id: str
    subject: str = ""
    ids: list[str] = Field(default_factory=list)
    all_for_subject: bool = False
    confirmation_token: str | None = None


class KbMemoryDeleteOutput(ContractFields):
    deleted_count: int


class KbRouteInput(BaseModel):
    query: str
    requested_mode: Literal["vector", "graph", "hybrid"] = "hybrid"
    include_memory: bool = True


class KbRoutePlanStep(BaseModel):
    tool: str
    purpose: str
    when: str = "always"
    required: bool = True


class KbRouteOutput(ContractFields):
    policy_version: str
    intent: Literal["fact_lookup", "relation_impact", "explainability", "memory_context", "memory_delete"]
    mode: Literal["vector", "graph", "hybrid"]
    route_reason: str
    recommended_tools: list[str] = Field(default_factory=list)
    execution_plan: list[KbRoutePlanStep] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)


class KbIngestOutput(ContractFields):
    created: int = 0
    updated: int = 0
    skipped: int = 0
    dry_run: bool = False


class KbHealthOutput(ContractFields):
    service_name: str
    transport: Literal["mcp"]
    auth_mode: str
    backends: dict[str, str]
    tools: list[str]
    resources: list[str]
    prompts: list[str]
    config: dict[str, Any] = Field(default_factory=dict)
    embedding_info: dict[str, Any] = Field(default_factory=dict)
