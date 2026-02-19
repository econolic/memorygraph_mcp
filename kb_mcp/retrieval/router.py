from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


Mode = Literal["vector", "graph", "hybrid"]


@dataclass(frozen=True)
class RoutedQuery:
    mode: Mode
    reason: str


class QueryRouter:
    def route(self, query: str, requested: Mode) -> RoutedQuery:
        if requested != "hybrid":
            return RoutedQuery(mode=requested, reason="requested_mode")

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
            return RoutedQuery(mode="hybrid", reason="structural_query")

        return RoutedQuery(mode="hybrid", reason="default_hybrid")
