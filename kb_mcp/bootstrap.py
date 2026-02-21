from __future__ import annotations

from dataclasses import dataclass

from kb_mcp.config import AppConfig
from kb_mcp.ingest.embeddings import (
    DeterministicFallbackEmbedder,
    Embedder,
    LocalSentenceTransformerEmbedder,
    OpenAICompatibleEmbedder,
)
from kb_mcp.ingest.connectors.filesystem import FilesystemConnector
from kb_mcp.ingest.connectors.git import GitConnector
from kb_mcp.ingest.entity_extract import EntityExtractionConfig
from kb_mcp.ingest.pipeline import IngestionPipeline
from kb_mcp.memory.service import MemoryService
from kb_mcp.memory.validator import MemoryFactValidator
from kb_mcp.observability.audit import AuditLogger
from kb_mcp.observability.metrics import MetricsRegistry
from kb_mcp.observability.tracing import setup_tracing
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
from kb_mcp.storage.metadata_store import MetadataRepository, MetadataStore
from kb_mcp.storage.neo4j_store import Neo4jGraphStore
from kb_mcp.storage.qdrant_store import QdrantVectorStore
from kb_mcp.storage.sql_metadata_store import SQLMetadataStore


@dataclass(frozen=True)
class AppDeps:
    config: AppConfig
    vector_store: VectorStore
    graph_store: GraphStore
    metadata: MetadataRepository
    retriever: HybridRetriever
    evidence: EvidenceBuilder
    acl: AclService
    auth: JwtAuthService
    redact: RedactionService
    memory: MemoryService
    ingestion: IngestionPipeline
    metrics: MetricsRegistry
    audit: AuditLogger


def _create_embedder(cfg: AppConfig) -> Embedder:
    fallback = DeterministicFallbackEmbedder(dimensions=cfg.embedding_dimensions)
    if cfg.embedding_provider == "local":
        return LocalSentenceTransformerEmbedder(
            model_name=cfg.embedding_model,
            model_revision=cfg.embedding_model_revision,
            batch_size=cfg.embedding_batch_size,
            cache_enabled=cfg.embedding_cache_enabled,
            cache_max_items=cfg.embedding_cache_max_items,
            fallback=fallback,
        )
    if cfg.embedding_provider == "openai_compatible":
        return OpenAICompatibleEmbedder(
            base_url=cfg.embedding_base_url,
            api_key=cfg.embedding_api_key,
            model=cfg.embedding_model,
            dimensions=cfg.embedding_dimensions,
            batch_size=cfg.embedding_batch_size,
            cache_enabled=cfg.embedding_cache_enabled,
            cache_max_items=cfg.embedding_cache_max_items,
            fallback=fallback,
        )
    return fallback


def _create_vector_store(cfg: AppConfig, embedder: Embedder) -> VectorStore:
    if cfg.vector_backend == "qdrant":
        return QdrantVectorStore(
            url=cfg.qdrant_url,
            chunks_collection=cfg.qdrant_collection_chunks,
            memory_collection=cfg.qdrant_collection_memory,
            embedder=embedder,
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


def _create_metadata_store(cfg: AppConfig) -> MetadataRepository:
    if cfg.metadata_backend == "memory":
        return MetadataStore()
    if cfg.metadata_backend in {"sqlite", "postgres"}:
        return SQLMetadataStore(dsn=cfg.metadata_dsn)
    raise ValueError(f"Unsupported metadata backend: {cfg.metadata_backend}")


def build_deps(cfg: AppConfig | None = None) -> AppDeps:
    cfg = cfg or AppConfig.from_env()
    setup_tracing(cfg)

    embedder = _create_embedder(cfg)
    metadata = _create_metadata_store(cfg)
    vector_store = _create_vector_store(cfg, embedder)
    graph_store = _create_graph_store(cfg)

    retriever = HybridRetriever(
        vector_store=vector_store,
        graph_store=graph_store,
        reranker=CrossEncoderReranker(),
        fusion_mode=cfg.fusion_mode,
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
        git=GitConnector(),
        chunking_mode=cfg.chunking_mode,
        entity_config=EntityExtractionConfig(
            min_symbol_len=cfg.entity_extraction_min_symbol_len,
            min_term_len=cfg.entity_extraction_min_term_len,
            symbol_allow_pattern=cfg.entity_symbol_allow_pattern,
            table_allow_pattern=cfg.entity_table_allow_pattern,
            term_allow_pattern=cfg.entity_term_allow_pattern,
            stopwords=cfg.entity_extraction_stopwords,
        ),
        embedding_model_info={
            "provider": cfg.embedding_provider,
            "model": cfg.embedding_model,
            "revision": cfg.embedding_model_revision,
        },
    )
    metrics = MetricsRegistry(prometheus_enabled=cfg.prometheus_enabled)
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
