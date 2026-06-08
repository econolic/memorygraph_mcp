from __future__ import annotations

from kb_mcp.server.tools.search import register_search_tools
from kb_mcp.server.tools.memory import register_memory_tools
from kb_mcp.server.tools.ingest import register_ingest_tools
from kb_mcp.server.tools.system import register_system_tools

__all__ = [
    "register_search_tools",
    "register_memory_tools",
    "register_ingest_tools",
    "register_system_tools",
]
