from __future__ import annotations

from mcp.server.fastmcp import FastMCP

RUNTIME_TOOL_POLICY_PROMPT = """Ты работаешь с MCP tools базы знаний.
Всегда сначала вызывай kb.route, затем следуй execution_plan и вызывай tools до финального ответа, если факт можно проверить.
Обязательный порядок:
0) kb.route для определения intent и плана;
1) kb.memory.search для user/workspace контекста;
2) kb.search для factual evidence и citations;
3) kb.graph_expand для зависимостей/impact;
4) kb.explain для объяснения релевантности.
Для новых фактов используй kb.memory.upsert только при наличии citations и confidence >= threshold.
Для удаления памяти используй только kb.memory.delete.
Не выдумывай источники: если evidence нет, явно сообщи это.
Если graph недоступен, деградируй на vector evidence и укажи ограничение."""

def register_prompts(mcp: FastMCP) -> None:
    @mcp.prompt(name="kb.answer_with_citations")
    def prompt_answer_with_citations(question: str) -> str:
        return (
            "Ответь на вопрос только на основании evidence. "
            "Для каждого утверждения дай citation на kb://chunk/... и span. "
            f"Вопрос: {question}"
        )

    @mcp.prompt(name="kb.tool_selection_policy")
    def prompt_tool_selection_policy() -> str:
        return RUNTIME_TOOL_POLICY_PROMPT

    @mcp.prompt(name="kb.incident_triage")
    def prompt_incident_triage(incident: str) -> str:
        return (
            "Сделай triage инцидента: симптомы, вероятные причины, зависимости, runbook steps. "
            "Каждый шаг должен ссылаться на evidence. "
            f"Инцидент: {incident}"
        )

    @mcp.prompt(name="kb.memory_grounded_reply")
    def prompt_memory_grounded_reply(question: str) -> str:
        return (
            "Сформируй ответ, сначала опираясь на memory_hits текущего пользователя/workspace, "
            "затем проверь ответ через документальные evidence и приложи citations. "
            f"Вопрос: {question}"
        )
