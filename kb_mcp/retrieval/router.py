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


@dataclass(frozen=True)
class IntentStrategy:
    intent: Intent
    markers: tuple[str, ...]
    recommended_tools: tuple[str, ...]

    def matches(self, query: str, include_memory: bool = False) -> bool:
        if self.intent == "memory_context" and include_memory:
            return True
        q = query.lower()
        return any(marker in q for marker in self.markers)


INTENT_STRATEGIES: list[IntentStrategy] = [
    IntentStrategy(
        intent="memory_delete",
        markers=(
            "удали память",
            "forget everything",
            "delete memory",
            "remove memory",
            "удали все что помнишь",
            "forget what you know",
        ),
        recommended_tools=("kb_memory_delete",),
    ),
    IntentStrategy(
        intent="explainability",
        markers=(
            "почему так ответил",
            "почему релевант",
            "explain relevance",
            "why this result",
            "объясни ответ",
        ),
        recommended_tools=("kb_search", "kb_explain"),
    ),
    IntentStrategy(
        intent="relation_impact",
        markers=(
            "завис",
            "dependency",
            "кто использует",
            "цепоч",
            "impact",
            "влия",
            "связ",
            "path",
        ),
        recommended_tools=("kb_search", "kb_graph_expand"),
    ),
    IntentStrategy(
        intent="memory_context",
        markers=(
            "прошл",
            "раньше",
            "what did we decide",
            "my context",
            "remember",
            "что мы решили",
            "мой контекст",
        ),
        recommended_tools=("kb_memory_search", "kb_search"),
    ),
    IntentStrategy(
        intent="fact_lookup",
        markers=(),
        recommended_tools=("kb_search",),
    ),
]


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
        for strategy in INTENT_STRATEGIES:
            if strategy.intent == "fact_lookup":
                continue
            if strategy.matches(query, include_memory):
                return strategy.intent
        return "fact_lookup"

    def _recommended_tools(self, intent: Intent) -> tuple[str, ...]:
        for strategy in INTENT_STRATEGIES:
            if strategy.intent == intent:
                return strategy.recommended_tools
        return ("kb_search",)
