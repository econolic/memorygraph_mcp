from __future__ import annotations

from uuid import UUID, NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient
from qdrant_client.http import models

from kb_mcp.ingest.embeddings import Embedder
from kb_mcp.retrieval.models import VectorHit


class QdrantVectorStore:
    def __init__(
        self,
        *,
        url: str,
        chunks_collection: str,
        memory_collection: str,
        embedder: Embedder,
    ) -> None:
        self._client = QdrantClient(url=url)
        self._chunks = chunks_collection
        self._memory = memory_collection
        self._embedder = embedder
        self._ensure_collection(self._chunks)
        self._ensure_collection(self._memory)

    def _ensure_collection(self, collection: str) -> None:
        try:
            info = self._client.get_collection(collection_name=collection)
            if info.config is not None and info.config.params is not None:
                vectors_cfg = info.config.params.vectors
                if isinstance(vectors_cfg, models.VectorParams):
                    if vectors_cfg.size != self._embedder.dimensions:
                        raise RuntimeError(
                            f"Collection {collection} has vector size {vectors_cfg.size}, "
                            f"expected {self._embedder.dimensions}"
                        )
            return
        except RuntimeError:
            raise
        except Exception:
            self._client.create_collection(
                collection_name=collection,
                vectors_config=models.VectorParams(
                    size=self._embedder.dimensions,
                    distance=models.Distance.COSINE,
                ),
            )

    def _point_id(self, raw_id: str) -> UUID:
        return uuid5(NAMESPACE_URL, f"hybrid-kb-mcp:{raw_id}")

    def _build_filter(
        self,
        filters: dict[str, object],
        *,
        id_key: str | None = None,
        ids: list[str] | None = None,
    ) -> models.Filter | None:
        conditions: list[models.Condition] = []
        workspace_id = filters.get("workspace_id")
        acl_subject = filters.get("acl_subject")
        if workspace_id:
            conditions.append(
                models.FieldCondition(key="workspace_id", match=models.MatchValue(value=str(workspace_id)))
            )
        if acl_subject:
            conditions.append(
                models.FieldCondition(key="acl_allow", match=models.MatchAny(any=[str(acl_subject)]))
            )
        if id_key and ids:
            conditions.append(
                models.FieldCondition(key=id_key, match=models.MatchAny(any=[str(value) for value in ids]))
            )
        if not conditions:
            return None
        return models.Filter(must=conditions)

    def _search(
        self,
        *,
        collection_name: str,
        query: str,
        top_k: int,
        filters: dict[str, object],
    ) -> list[VectorHit]:
        response = self._client.query_points(
            collection_name=collection_name,
            query=self._embedder.embed_query(query),
            query_filter=self._build_filter(filters),
            limit=top_k,
            with_payload=True,
            with_vectors=False,
        )
        out: list[VectorHit] = []
        for point in response.points:
            payload = point.payload if isinstance(point.payload, dict) else {}
            item_id = payload.get("_item_id")
            raw_item_id = str(item_id) if isinstance(item_id, str) else str(point.id)
            out.append(
                VectorHit(
                    item_id=raw_item_id,
                    score=float(point.score),
                    payload=payload,
                )
            )
        return out

    def search_chunks(self, *, query: str, top_k: int, filters: dict[str, object]) -> list[VectorHit]:
        return self._search(collection_name=self._chunks, query=query, top_k=top_k, filters=filters)

    def search_memory(self, *, query: str, top_k: int, filters: dict[str, object]) -> list[VectorHit]:
        return self._search(collection_name=self._memory, query=query, top_k=top_k, filters=filters)

    def upsert_chunk(self, *, chunk_id: str, text: str, payload: dict[str, object]) -> None:
        payload_with_id = dict(payload)
        payload_with_id["_item_id"] = chunk_id
        payload_with_id["text"] = text
        self._client.upsert(
            collection_name=self._chunks,
            points=[
                models.PointStruct(
                    id=self._point_id(chunk_id),
                    vector=self._embedder.embed_query(text),
                    payload=payload_with_id,
                )
            ],
        )

    def upsert_memory(self, *, memory_id: str, text: str, payload: dict[str, object]) -> None:
        payload_with_id = dict(payload)
        payload_with_id["_item_id"] = memory_id
        payload_with_id["text"] = text
        self._client.upsert(
            collection_name=self._memory,
            points=[
                models.PointStruct(
                    id=self._point_id(memory_id),
                    vector=self._embedder.embed_query(text),
                    payload=payload_with_id,
                )
            ],
        )

    def delete_memory(self, *, memory_ids: list[str], filters: dict[str, object]) -> int:
        if not memory_ids:
            return 0
        selector_filter = self._build_filter(filters, id_key="_item_id", ids=memory_ids)
        if selector_filter is None:
            return 0
        self._client.delete(
            collection_name=self._memory,
            points_selector=models.FilterSelector(filter=selector_filter),
        )
        return len(memory_ids)

    def delete_chunks(self, *, chunk_ids: list[str], filters: dict[str, object]) -> int:
        if not chunk_ids:
            return 0
        selector_filter = self._build_filter(filters, id_key="_item_id", ids=chunk_ids)
        if selector_filter is None:
            return 0
        self._client.delete(
            collection_name=self._chunks,
            points_selector=models.FilterSelector(filter=selector_filter),
        )
        return len(chunk_ids)
