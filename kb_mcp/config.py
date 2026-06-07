from __future__ import annotations

from dataclasses import dataclass
from os import getenv
from pathlib import Path


def _csv_tuple(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _resolved_roots(roots: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(Path(root).expanduser().resolve()) for root in roots)


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
    oauth_issuer_url: str = ""
    oauth_audience: str = ""
    oauth_jwks_url: str = ""
    oauth_required_scopes: tuple[str, ...] = ()

    embedding_provider: str = "local"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_model_revision: str = ""
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_dimensions: int = 384
    embedding_batch_size: int = 32
    embedding_cache_enabled: bool = True
    embedding_cache_max_items: int = 4096
    entity_extraction_min_symbol_len: int = 3
    entity_extraction_min_term_len: int = 3
    entity_symbol_allow_pattern: str = r"^[A-Za-z_][A-Za-z0-9_]{2,}$"
    entity_table_allow_pattern: str = r"^[a-z_]+\.[a-z_]+$"
    entity_term_allow_pattern: str = r"^[А-Яа-яЁё][А-Яа-яЁё0-9_\-]{2,}$"
    entity_extraction_stopwords: tuple[str, ...] = (
        "the",
        "and",
        "with",
        "from",
        "that",
        "this",
        "for",
        "are",
        "или",
        "как",
        "для",
        "это",
        "что",
        "при",
        "class",
        "def",
        "import",
        "from",
        "return",
        "true",
        "false",
        "none",
    )
    fusion_mode: str = "linear"
    chunking_mode: str = "char"
    graph_enforce_object_acl: bool = True
    auto_ingest_enabled: bool = True
    auto_ingest_roots: tuple[str, ...] = ("/app/.kb_mcp/project_sync", "./kb_mcp")
    auto_ingest_workspace_id: str = "w1"
    auto_ingest_acl_subject: str = "u1"
    auto_ingest_interval_s: int = 900
    auto_ingest_run_on_start: bool = True
    auto_ingest_full_interval_cycles: int = 8
    auto_ingest_git_since_ref: str = "HEAD~1"
    auto_ingest_retry_attempts: int = 3
    auto_ingest_retry_backoff_s: float = 1.5
    ingest_allowed_roots: tuple[str, ...] = ()

    vector_timeout_s: float = 1.0
    graph_timeout_s: float = 1.0
    rerank_timeout_s: float = 2.0
    otel_enabled: bool = False
    otel_exporter_otlp_endpoint: str = ""
    otel_exporter_otlp_protocol: str = "http/protobuf"
    prometheus_enabled: bool = False
    prometheus_port: int = 9464

    default_top_k: int = 20
    max_top_k: int = 100
    default_expand_depth: int = 2
    max_expand_depth: int = 3

    deny_by_default: bool = True
    memory_confidence_threshold: float = 0.75
    memory_retention_days: int = 0

    @staticmethod
    def from_env() -> "AppConfig":
        default_auto_roots = "/app/.kb_mcp/project_sync,./kb_mcp"
        auto_ingest_roots = _csv_tuple(getenv("KB_AUTO_INGEST_ROOTS", default_auto_roots))
        allowed_roots_raw = getenv("KB_INGEST_ALLOWED_ROOTS", "")
        ingest_allowed_roots = _resolved_roots(
            _csv_tuple(allowed_roots_raw) if allowed_roots_raw.strip() else auto_ingest_roots
        )
        return AppConfig(
            service_name=getenv("KB_SERVICE_NAME", "hybrid-kb-mcp"),
            http_host=getenv("KB_HTTP_HOST", "127.0.0.1"),
            http_port=int(getenv("KB_HTTP_PORT", "8080")),
            auth_mode=getenv("KB_AUTH_MODE", "dual"),
            transport_security_enabled=getenv("KB_TRANSPORT_SECURITY_ENABLED", "true").lower() == "true",
            transport_allowed_hosts=_csv_tuple(getenv("KB_TRANSPORT_ALLOWED_HOSTS", "")),
            transport_allowed_origins=_csv_tuple(getenv("KB_TRANSPORT_ALLOWED_ORIGINS", "")),
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
            oauth_issuer_url=getenv("KB_OAUTH_ISSUER_URL", ""),
            oauth_audience=getenv("KB_OAUTH_AUDIENCE", ""),
            oauth_jwks_url=getenv("KB_OAUTH_JWKS_URL", ""),
            oauth_required_scopes=_csv_tuple(getenv("KB_OAUTH_REQUIRED_SCOPES", "")),
            embedding_provider=getenv("KB_EMBEDDING_PROVIDER", "local"),
            embedding_model=getenv("KB_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
            embedding_model_revision=getenv("KB_EMBEDDING_MODEL_REVISION", ""),
            embedding_base_url=getenv("KB_EMBEDDING_BASE_URL", ""),
            embedding_api_key=getenv("KB_EMBEDDING_API_KEY", ""),
            embedding_dimensions=int(getenv("KB_EMBEDDING_DIMENSIONS", "384")),
            embedding_batch_size=int(getenv("KB_EMBEDDING_BATCH_SIZE", "32")),
            embedding_cache_enabled=getenv("KB_EMBEDDING_CACHE_ENABLED", "true").lower() == "true",
            embedding_cache_max_items=int(getenv("KB_EMBEDDING_CACHE_MAX_ITEMS", "4096")),
            entity_extraction_min_symbol_len=int(getenv("KB_ENTITY_EXTRACTION_MIN_SYMBOL_LEN", "3")),
            entity_extraction_min_term_len=int(getenv("KB_ENTITY_EXTRACTION_MIN_TERM_LEN", "3")),
            entity_symbol_allow_pattern=getenv(
                "KB_ENTITY_SYMBOL_ALLOW_PATTERN",
                r"^[A-Za-z_][A-Za-z0-9_]{2,}$",
            ),
            entity_table_allow_pattern=getenv(
                "KB_ENTITY_TABLE_ALLOW_PATTERN",
                r"^[a-z_]+\.[a-z_]+$",
            ),
            entity_term_allow_pattern=getenv(
                "KB_ENTITY_TERM_ALLOW_PATTERN",
                r"^[А-Яа-яЁё][А-Яа-яЁё0-9_\-]{2,}$",
            ),
            entity_extraction_stopwords=tuple(
                token.strip().lower()
                for token in getenv(
                    "KB_ENTITY_EXTRACTION_STOPWORDS",
                    "the,and,with,from,that,this,for,are,или,как,для,это,что,при,class,def,import,return,true,false,none",
                ).split(",")
                if token.strip()
            ),
            fusion_mode=getenv("KB_FUSION_MODE", "linear"),
            chunking_mode=getenv("KB_CHUNKING_MODE", "char"),
            graph_enforce_object_acl=getenv("KB_GRAPH_ENFORCE_OBJECT_ACL", "true").lower() == "true",
            auto_ingest_enabled=getenv("KB_AUTO_INGEST_ENABLED", "true").lower() == "true",
            auto_ingest_roots=auto_ingest_roots,
            auto_ingest_workspace_id=getenv("KB_AUTO_INGEST_WORKSPACE_ID", "w1"),
            auto_ingest_acl_subject=getenv("KB_AUTO_INGEST_ACL_SUBJECT", "u1"),
            auto_ingest_interval_s=int(getenv("KB_AUTO_INGEST_INTERVAL_S", "900")),
            auto_ingest_run_on_start=getenv("KB_AUTO_INGEST_RUN_ON_START", "true").lower() == "true",
            auto_ingest_full_interval_cycles=max(1, int(getenv("KB_AUTO_INGEST_FULL_INTERVAL_CYCLES", "8"))),
            auto_ingest_git_since_ref=getenv("KB_AUTO_INGEST_GIT_SINCE_REF", "HEAD~1"),
            auto_ingest_retry_attempts=max(1, int(getenv("KB_AUTO_INGEST_RETRY_ATTEMPTS", "3"))),
            auto_ingest_retry_backoff_s=max(0.1, float(getenv("KB_AUTO_INGEST_RETRY_BACKOFF_S", "1.5"))),
            ingest_allowed_roots=ingest_allowed_roots,
            vector_timeout_s=float(getenv("KB_VECTOR_TIMEOUT_S", "1.0")),
            graph_timeout_s=float(getenv("KB_GRAPH_TIMEOUT_S", "1.0")),
            rerank_timeout_s=float(getenv("KB_RERANK_TIMEOUT_S", "2.0")),
            otel_enabled=getenv("KB_OTEL_ENABLED", "false").lower() == "true",
            otel_exporter_otlp_endpoint=getenv("KB_OTEL_EXPORTER_OTLP_ENDPOINT", ""),
            otel_exporter_otlp_protocol=getenv("KB_OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf"),
            prometheus_enabled=getenv("KB_PROMETHEUS_ENABLED", "false").lower() == "true",
            prometheus_port=int(getenv("KB_PROMETHEUS_PORT", "9464")),
            default_top_k=int(getenv("KB_DEFAULT_TOP_K", "20")),
            max_top_k=int(getenv("KB_MAX_TOP_K", "100")),
            default_expand_depth=int(getenv("KB_DEFAULT_EXPAND_DEPTH", "2")),
            max_expand_depth=int(getenv("KB_MAX_EXPAND_DEPTH", "3")),
            deny_by_default=getenv("KB_DENY_BY_DEFAULT", "true").lower() == "true",
            memory_confidence_threshold=float(getenv("KB_MEMORY_CONFIDENCE_THRESHOLD", "0.75")),
            memory_retention_days=int(getenv("KB_MEMORY_RETENTION_DAYS", "0")),
        )


_WEAK_SECRET_PLACEHOLDERS = {
    "",
    "change-me",
    "replace-with-strong-32plus-char-secret",
}


def _normalized_bind_host(host: str) -> str:
    normalized = str(host).strip().lower()
    if normalized.startswith("[") and normalized.endswith("]"):
        normalized = normalized[1:-1]
    return normalized


def is_localhost_bind(host: str) -> bool:
    return _normalized_bind_host(host) in {"127.0.0.1", "::1", "localhost"}


def is_weak_jwt_secret(secret: str) -> bool:
    return str(secret).strip() in _WEAK_SECRET_PLACEHOLDERS


def security_validation_summary(cfg: AppConfig, *, transport: str) -> dict[str, object]:
    bind_host = _normalized_bind_host(cfg.http_host)
    return {
        "transport": transport,
        "auth_mode": cfg.auth_mode,
        "http_host": cfg.http_host,
        "bind_scope": "localhost" if is_localhost_bind(bind_host) else "network",
        "transport_security_enabled": cfg.transport_security_enabled,
        "jwt_secret_weak": is_weak_jwt_secret(cfg.jwt_secret),
        "strict_oauth_configured": bool(cfg.oauth_issuer_url and cfg.oauth_jwks_url),
    }


def validate_security_config(cfg: AppConfig, *, transport: str) -> list[str]:
    warnings: list[str] = []
    weak_secret = is_weak_jwt_secret(cfg.jwt_secret)
    network_exposed_http = transport == "http" and not is_localhost_bind(cfg.http_host)

    if cfg.auth_mode == "strict" and weak_secret:
        raise ValueError(
            "KB_AUTH_MODE=strict requires a strong KB_JWT_SECRET; "
            "replace the placeholder secret and restart."
        )

    if cfg.auth_mode == "dual" and network_exposed_http and weak_secret:
        raise ValueError(
            "KB_AUTH_MODE=dual with non-localhost HTTP bind requires a strong KB_JWT_SECRET; "
            "set KB_JWT_SECRET or bind to 127.0.0.1 for local-only dev."
        )

    if cfg.auth_mode == "dual" and weak_secret:
        warnings.append(
            "KB_AUTH_MODE=dual is using a placeholder KB_JWT_SECRET. "
            "This is acceptable only for localhost development."
        )

    if cfg.auth_mode == "strict_oauth":
        if not cfg.oauth_issuer_url or not cfg.oauth_jwks_url:
            raise ValueError(
                "KB_AUTH_MODE=strict_oauth requires KB_OAUTH_ISSUER_URL and KB_OAUTH_JWKS_URL."
            )
        if weak_secret:
            warnings.append(
                "KB_JWT_SECRET is unused in strict_oauth mode, but still set to a placeholder value."
            )

    return warnings
