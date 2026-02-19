from __future__ import annotations

from dataclasses import dataclass

from kb_mcp.config import AppConfig
from kb_mcp.ingest.connectors.filesystem import FilesystemConnector
from kb_mcp.ingest.pipeline import IngestionPipeline
from kb_mcp.memory.service import MemoryService
from kb_mcp.memory.validator import MemoryFactValidator
from kb_mcp.observability.audit import AuditLogger
from kb_mcp.observability.metrics import MetricsRegistry
from kb_mcp.retrieval.evidence import EvidenceBuilder
from kb_mcp.retrieval.graph_store import GraphStore
from kb_mcp.retrieval.hybrid import HybridRetriever
from kb_mcp.retrieval.rerank import CrossEncoderReranker
from kb_mcp.retrieval.vector_store import VectorStore
from kb_mcp.security.acl import AclService
from kb_mcp.security.auth import JwtAuthService
from kb_mcp.security.redact import RedactionService
from kb_mcp.storage.in_memory_graph import InMemoryGraphStore
from kb_mcp.storage.in_memory_vector import InMemoryVectorStore
from kb_mcp.storage.metadata_store import MetadataStore
from kb_mcp.storage.neo4j_store import Neo4jGraphStore
from kb_mcp.storage.qdrant_store import QdrantVectorStore


@dataclass(frozen=True)
class AppDeps:
    config: AppConfig
    vector_store: VectorStore
    graph_store: GraphStore
    metadata: MetadataStore
    retriever: HybridRetriever
    evidence: EvidenceBuilder
    acl: AclService
    auth: JwtAuthService
    redact: RedactionService
    memory: MemoryService
    ingestion: IngestionPipeline
    metrics: MetricsRegistry
    audit: AuditLogger


def _create_vector_store(cfg: AppConfig) -> VectorStore:
    if cfg.vector_backend == "qdrant":
        return QdrantVectorStore(
            url=cfg.qdrant_url,
            chunks_collection=cfg.qdrant_collection_chunks,
            memory_collection=cfg.qdrant_collection_memory,
        )
    if cfg.vector_backend == "memory":
        return InMemoryVectorStore()
    raise ValueError(f"Unsupported vector backend: {cfg.vector_backend}")


def _create_graph_store(cfg: AppConfig) -> GraphStore:
    if cfg.graph_backend == "neo4j":
        return Neo4jGraphStore(
            uri=cfg.neo4j_uri,
            user=cfg.neo4j_user,
            password=cfg.neo4j_password,
            database=cfg.neo4j_database,
        )
    if cfg.graph_backend == "memory":
        return InMemoryGraphStore()
    raise ValueError(f"Unsupported graph backend: {cfg.graph_backend}")


def build_deps(cfg: AppConfig | None = None) -> AppDeps:
    cfg = cfg or AppConfig.from_env()

    metadata = MetadataStore()
    vector_store = _create_vector_store(cfg)
    graph_store = _create_graph_store(cfg)

    retriever = HybridRetriever(
        vector_store=vector_store,
        graph_store=graph_store,
        reranker=CrossEncoderReranker(),
    )
    evidence = EvidenceBuilder(metadata)

    acl = AclService(deny_by_default=cfg.deny_by_default)
    auth = JwtAuthService(cfg)
    redact = RedactionService()
    validator = MemoryFactValidator(confidence_threshold=cfg.memory_confidence_threshold)
    memory = MemoryService(
        vector_store=vector_store,
        graph_store=graph_store,
        metadata=metadata,
        validator=validator,
    )

    ingestion = IngestionPipeline(
        vector_store=vector_store,
        graph_store=graph_store,
        metadata=metadata,
        filesystem=FilesystemConnector(),
    )
    metrics = MetricsRegistry()
    audit = AuditLogger()

    return AppDeps(
        config=cfg,
        vector_store=vector_store,
        graph_store=graph_store,
        metadata=metadata,
        retriever=retriever,
        evidence=evidence,
        acl=acl,
        auth=auth,
        redact=redact,
        memory=memory,
        ingestion=ingestion,
        metrics=metrics,
        audit=audit,
    )
