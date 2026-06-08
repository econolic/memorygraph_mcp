from __future__ import annotations

from kb_mcp.retrieval.router import Intent
from kb_mcp.server.schemas import KbRoutePlanStep

EXECUTION_PLANS: dict[Intent, list[KbRoutePlanStep]] = {
    "memory_delete": [
        KbRoutePlanStep(
            tool="kb_memory_delete",
            purpose="Delete stored memory for selected IDs or all records for current subject/workspace.",
        )
    ],
    "memory_context": [
        KbRoutePlanStep(
            tool="kb_memory_search",
            purpose="Load prior user/workspace memory relevant to the question.",
        ),
        KbRoutePlanStep(
            tool="kb_search",
            purpose="Validate or enrich the answer with document evidence and citations.",
        ),
    ],
    "relation_impact": [
        KbRoutePlanStep(
            tool="kb_search",
            purpose="Find evidence and candidate entities/URIs for graph expansion.",
        ),
        KbRoutePlanStep(
            tool="kb_graph_expand",
            purpose="Expand dependencies / impact paths from selected seed entities.",
            when="after selecting seed entity URIs from search results",
        ),
    ],
    "explainability": [
        KbRoutePlanStep(
            tool="kb_search",
            purpose="Retrieve relevant results and target URIs to explain.",
        ),
        KbRoutePlanStep(
            tool="kb_explain",
            purpose="Explain why selected results are relevant.",
            when="after selecting URIs from search results",
        ),
    ],
    "fact_lookup": [
        KbRoutePlanStep(
            tool="kb_search",
            purpose="Retrieve factual evidence and citations for the query.",
        )
    ],
}

def build_execution_plan(*, intent: Intent) -> list[KbRoutePlanStep]:
    return EXECUTION_PLANS.get(intent) or EXECUTION_PLANS["fact_lookup"]
