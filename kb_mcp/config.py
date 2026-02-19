from __future__ import annotations

from dataclasses import dataclass
from os import getenv


@dataclass(frozen=True)
class AppConfig:
    service_name: str = "hybrid-kb-mcp"

    http_host: str = "0.0.0.0"
    http_port: int = 8080

    vector_backend: str = "qdrant"
    graph_backend: str = "neo4j"

    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection_chunks: str = "kb_chunks"
    qdrant_collection_memory: str = "kb_memory"

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4jpass"
    neo4j_database: str = "neo4j"

    jwt_secret: str = "change-me"
    jwt_algorithms: tuple[str, ...] = ("HS256",)

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
            http_host=getenv("KB_HTTP_HOST", "0.0.0.0"),
            http_port=int(getenv("KB_HTTP_PORT", "8080")),
            vector_backend=getenv("KB_VECTOR_BACKEND", "qdrant"),
            graph_backend=getenv("KB_GRAPH_BACKEND", "neo4j"),
            qdrant_url=getenv("KB_QDRANT_URL", "http://qdrant:6333"),
            qdrant_collection_chunks=getenv("KB_QDRANT_COLLECTION_CHUNKS", "kb_chunks"),
            qdrant_collection_memory=getenv("KB_QDRANT_COLLECTION_MEMORY", "kb_memory"),
            neo4j_uri=getenv("KB_NEO4J_URI", "bolt://neo4j:7687"),
            neo4j_user=getenv("KB_NEO4J_USER", "neo4j"),
            neo4j_password=getenv("KB_NEO4J_PASSWORD", "neo4jpass"),
            neo4j_database=getenv("KB_NEO4J_DATABASE", "neo4j"),
            jwt_secret=getenv("KB_JWT_SECRET", "change-me"),
            jwt_algorithms=(getenv("KB_JWT_ALGORITHM", "HS256"),),
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
