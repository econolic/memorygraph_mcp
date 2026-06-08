from __future__ import annotations

import math
from kb_mcp.ingest.embeddings import Embedder
from kb_mcp.storage.metadata_store import MetadataRepository

class QueryExpander:
    """Expand query with semantically similar terms using embeddings.

    Strategy:
    1. Embed the original query
    2. Find top-N similar terms from entity index
    3. Append unique expansion terms to query
    4. Return expanded query for vector search
    """

    def __init__(self, embedder: Embedder, metadata: MetadataRepository) -> None:
        self._embedder = embedder
        self._metadata = metadata

    def _cosine_similarity(self, vec1: list[float], vec2: list[float]) -> float:
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm_a = math.sqrt(sum(a * a for a in vec1))
        norm_b = math.sqrt(sum(b * b for b in vec2))
        if norm_a == 0.0 or norm_b == 0.0:
            return 0.0
        return dot_product / (norm_a * norm_b)

    def expand(self, query: str, workspace_id: str, *, max_expansions: int = 3) -> str:
        """Return query + expansion terms (e.g., "зависимости сервиса AuthService login_module")"""
        if max_expansions <= 0 or not query.strip():
            return query

        try:
            entities = self._metadata.list_entities(workspace_id=workspace_id)
            if not entities:
                return query

            # Embed query
            query_vec = self._embedder.embed_query(query)

            # Extract names & aliases, and embed them
            entity_terms: list[str] = []
            for ent in entities:
                name = ent.get("name")
                if name and name not in entity_terms:
                    entity_terms.append(name)
                for alias in ent.get("aliases", []):
                    if alias and alias not in entity_terms:
                        entity_terms.append(alias)

            if not entity_terms:
                return query

            # Embed all candidate terms
            term_vectors = self._embedder.embed_texts(entity_terms)

            # Compute similarities
            scored_terms: list[tuple[str, float]] = []
            for term, term_vec in zip(entity_terms, term_vectors):
                sim = self._cosine_similarity(query_vec, term_vec)
                scored_terms.append((term, sim))

            # Sort by similarity descending
            scored_terms.sort(key=lambda x: x[1], reverse=True)

            # Take top N expansions that are NOT already in the query
            expansions: list[str] = []
            query_lower = query.lower()
            for term, score in scored_terms:
                if len(expansions) >= max_expansions:
                    break
                if term.lower() not in query_lower and score > 0.4:
                    expansions.append(term)

            if expansions:
                return f"{query} {' '.join(expansions)}"
            return query
        except Exception:
            return query
