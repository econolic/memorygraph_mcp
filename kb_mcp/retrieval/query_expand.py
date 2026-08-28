from __future__ import annotations

from kb_mcp.retrieval.vector_store import VectorStore


class QueryExpander:
    """Expand query with semantically similar terms using embeddings.

    Strategy:
    1. Embed the original query
    2. Find top-N similar terms from entity index
    3. Append unique expansion terms to query
    4. Return expanded query for vector search
    """

    def __init__(
        self,
        vector_store: VectorStore,
        *,
        max_expansions: int = 3,
        min_score: float = 0.4,
    ) -> None:
        self._vector = vector_store
        self._max_expansions = max(0, max_expansions)
        self._min_score = min_score

    def expand(
        self,
        query: str,
        filters: dict[str, object],
        *,
        max_expansions: int | None = None,
    ) -> str:
        """Return query + expansion terms (e.g., "зависимости сервиса AuthService login_module")"""
        expansion_limit = self._max_expansions if max_expansions is None else max(0, max_expansions)
        if expansion_limit <= 0 or not query.strip() or not str(filters.get("workspace_id", "")):
            return query

        try:
            hits = self._vector.search_entities(
                query=query,
                top_k=max(10, expansion_limit * 4),
                filters=filters,
            )
            expansions: list[str] = []
            query_lower = query.lower()
            seen = {query_lower}
            for hit in hits:
                if hit.score < self._min_score:
                    continue
                raw_terms = [hit.payload.get("name"), *(hit.payload.get("aliases", []) or [])]
                for raw_term in raw_terms:
                    term = str(raw_term or "").strip()
                    normalized = term.lower()
                    if not term or normalized in seen or normalized in query_lower:
                        continue
                    expansions.append(term)
                    seen.add(normalized)
                    if len(expansions) >= expansion_limit:
                        break
                if len(expansions) >= expansion_limit:
                    break

            if expansions:
                return f"{query} {' '.join(expansions)}"
            return query
        except Exception:
            return query
