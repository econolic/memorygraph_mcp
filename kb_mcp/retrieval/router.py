from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Mode = Literal["vector", "graph", "hybrid"]
Intent = Literal["fact_lookup", "relation_impact", "explainability", "memory_context", "memory_delete"]

POLICY_VERSION = "2026-02-19"


@dataclass(frozen=True)
class RoutedQuery:
    mode: Mode
    reason: str
    intent: Intent
    recommended_tools: tuple[str, ...]


class QueryRouter:
    def route(self, query: str, requested: Mode, include_memory: bool = False) -> RoutedQuery:
        intent = self._detect_intent(query=query, include_memory=include_memory)
        recommended_tools = self._recommended_tools(intent)

        if requested != "hybrid":
            return RoutedQuery(
                mode=requested,
                reason="requested_mode",
                intent=intent,
                recommended_tools=recommended_tools,
            )

        structural_markers = (
            "завис",
            "dependency",
            "кто использует",
            "связ",
            "влия",
            "path",
            "impact",
        )
        if any(marker in query.lower() for marker in structural_markers):
            return RoutedQuery(
                mode="hybrid",
                reason="structural_query",
                intent=intent,
                recommended_tools=recommended_tools,
            )

        return RoutedQuery(
            mode="hybrid",
            reason="default_hybrid",
            intent=intent,
            recommended_tools=recommended_tools,
        )

    def _detect_intent(self, query: str, include_memory: bool) -> Intent:
        q = query.lower()

        memory_delete_markers = (
            "удали память",
            "forget everything",
            "delete memory",
            "remove memory",
            "удали все что помнишь",
            "forget what you know",
        )
        if any(marker in q for marker in memory_delete_markers):
            return "memory_delete"

        explain_markers = (
            "почему так ответил",
            "почему релевант",
            "explain relevance",
            "why this result",
            "объясни ответ",
        )
        if any(marker in q for marker in explain_markers):
            return "explainability"

        relation_markers = (
            "завис",
            "dependency",
            "кто использует",
            "цепоч",
            "impact",
            "влия",
            "связ",
            "path",
        )
        if any(marker in q for marker in relation_markers):
            return "relation_impact"

        memory_context_markers = (
            "прошл",
            "раньше",
            "what did we decide",
            "my context",
            "remember",
            "что мы решили",
            "мой контекст",
        )
        if include_memory or any(marker in q for marker in memory_context_markers):
            return "memory_context"

        return "fact_lookup"

    def _recommended_tools(self, intent: Intent) -> tuple[str, ...]:
        if intent == "memory_delete":
            return ("kb.memory.delete",)
        if intent == "memory_context":
            return ("kb.memory.search", "kb.search")
        if intent == "relation_impact":
            return ("kb.search", "kb.graph_expand")
        if intent == "explainability":
            return ("kb.search", "kb.explain")
        return ("kb.search",)
