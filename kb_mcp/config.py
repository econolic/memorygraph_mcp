from __future__ import annotations

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class AppConfig:
    service_name: str = "hybrid-kb-mcp"

    http_host: str = "127.0.0.1"
    http_port: int = 8080
    auth_mode: str = "dual"
    transport_security_enabled: bool = True
    transport_allowed_hosts: tuple[str, ...] = ()
    transport_allowed_origins: tuple[str, ...] = ()

    vector_backend: str = "qdrant"
    graph_backend: str = "neo4j"
    metadata_backend: str = "sqlite"
    metadata_dsn: str = "sqlite:///./.kb_mcp/metadata.db"

    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection_chunks: str = "kb_chunks"
    qdrant_collection_memory: str = "kb_memory"

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4jpass"
    neo4j_database: str = "neo4j"

    jwt_secret: str = "change-me"
    jwt_algorithms: tuple[str, ...] = ("HS256",)

    embedding_provider: str = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_dimensions: int = 384
    fusion_mode: str = "linear"
    chunking_mode: str = "char"
    graph_enforce_object_acl: bool = True
    auto_ingest_enabled: bool = True
    auto_ingest_roots: tuple[str, ...] = ("/app/.kb_mcp/project_sync", "./kb_mcp")
    auto_ingest_workspace_id: str = "w1"
    auto_ingest_acl_subject: str = "u1"
    auto_ingest_interval_s: int = 900
    auto_ingest_run_on_start: bool = True

    vector_timeout_s: float = 1.0
    graph_timeout_s: float = 1.0
    rerank_timeout_s: float = 2.0

    default_top_k: int = 20
    max_top_k: int = 100
    default_expand_depth: int = 2
    max_expand_depth: int = 3

    deny_by_default: bool = True
    memory_confidence_threshold: float = 0.75
    memory_retention_days: int = 0

    @staticmethod
    def from_env() -> "AppConfig":
        return AppConfig(
            service_name=getenv("KB_SERVICE_NAME", "hybrid-kb-mcp"),
            http_host=getenv("KB_HTTP_HOST", "127.0.0.1"),
            http_port=int(getenv("KB_HTTP_PORT", "8080")),
            auth_mode=getenv("KB_AUTH_MODE", "dual"),
            transport_security_enabled=getenv("KB_TRANSPORT_SECURITY_ENABLED", "true").lower() == "true",
            transport_allowed_hosts=tuple(
                item.strip()
                for item in getenv("KB_TRANSPORT_ALLOWED_HOSTS", "").split(",")
                if item.strip()
            ),
            transport_allowed_origins=tuple(
                item.strip()
                for item in getenv("KB_TRANSPORT_ALLOWED_ORIGINS", "").split(",")
                if item.strip()
            ),
            vector_backend=getenv("KB_VECTOR_BACKEND", "qdrant"),
            graph_backend=getenv("KB_GRAPH_BACKEND", "neo4j"),
            metadata_backend=getenv("KB_METADATA_BACKEND", "sqlite"),
            metadata_dsn=getenv("KB_METADATA_DSN", "sqlite:///./.kb_mcp/metadata.db"),
            qdrant_url=getenv("KB_QDRANT_URL", "http://qdrant:6333"),
            qdrant_collection_chunks=getenv("KB_QDRANT_COLLECTION_CHUNKS", "kb_chunks"),
            qdrant_collection_memory=getenv("KB_QDRANT_COLLECTION_MEMORY", "kb_memory"),
            neo4j_uri=getenv("KB_NEO4J_URI", "bolt://neo4j:7687"),
            neo4j_user=getenv("KB_NEO4J_USER", "neo4j"),
            neo4j_password=getenv("KB_NEO4J_PASSWORD", "neo4jpass"),
            neo4j_database=getenv("KB_NEO4J_DATABASE", "neo4j"),
            jwt_secret=getenv("KB_JWT_SECRET", "change-me"),
            jwt_algorithms=(getenv("KB_JWT_ALGORITHM", "HS256"),),
            embedding_provider=getenv("KB_EMBEDDING_PROVIDER", "local"),
            embedding_model=getenv("KB_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            embedding_base_url=getenv("KB_EMBEDDING_BASE_URL", ""),
            embedding_api_key=getenv("KB_EMBEDDING_API_KEY", ""),
            embedding_dimensions=int(getenv("KB_EMBEDDING_DIMENSIONS", "384")),
            fusion_mode=getenv("KB_FUSION_MODE", "linear"),
            chunking_mode=getenv("KB_CHUNKING_MODE", "char"),
            graph_enforce_object_acl=getenv("KB_GRAPH_ENFORCE_OBJECT_ACL", "true").lower() == "true",
            auto_ingest_enabled=getenv("KB_AUTO_INGEST_ENABLED", "true").lower() == "true",
            auto_ingest_roots=tuple(
                item.strip()
                for item in getenv("KB_AUTO_INGEST_ROOTS", "/app/.kb_mcp/project_sync,./kb_mcp").split(",")
                if item.strip()
            ),
            auto_ingest_workspace_id=getenv("KB_AUTO_INGEST_WORKSPACE_ID", "w1"),
            auto_ingest_acl_subject=getenv("KB_AUTO_INGEST_ACL_SUBJECT", "u1"),
            auto_ingest_interval_s=int(getenv("KB_AUTO_INGEST_INTERVAL_S", "900")),
            auto_ingest_run_on_start=getenv("KB_AUTO_INGEST_RUN_ON_START", "true").lower() == "true",
            vector_timeout_s=float(getenv("KB_VECTOR_TIMEOUT_S", "1.0")),
            graph_timeout_s=float(getenv("KB_GRAPH_TIMEOUT_S", "1.0")),
            rerank_timeout_s=float(getenv("KB_RERANK_TIMEOUT_S", "2.0")),
            default_top_k=int(getenv("KB_DEFAULT_TOP_K", "20")),
            max_top_k=int(getenv("KB_MAX_TOP_K", "100")),
            default_expand_depth=int(getenv("KB_DEFAULT_EXPAND_DEPTH", "2")),
            max_expand_depth=int(getenv("KB_MAX_EXPAND_DEPTH", "3")),
            deny_by_default=getenv("KB_DENY_BY_DEFAULT", "true").lower() == "true",
            memory_confidence_threshold=float(getenv("KB_MEMORY_CONFIDENCE_THRESHOLD", "0.75")),
            memory_retention_days=int(getenv("KB_MEMORY_RETENTION_DAYS", "0")),
        )
