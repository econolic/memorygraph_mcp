from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any


class AuditLogger:
    def __init__(self) -> None:
        self._log = logging.getLogger("kb_mcp.audit")

    def log_call(
        self,
        *,
        subject: str,
        workspace_id: str,
        tool: str,
        params: dict[str, Any],
        result_count: int,
        latency_ms: int,
    ) -> None:
        params_hash = hashlib.sha256(json.dumps(params, sort_keys=True).encode("utf-8")).hexdigest()
        self._log.info(
            "audit",
            extra={
                "extra": {
                    "subject": subject,
                    "workspace_id": workspace_id,
                    "tool": tool,
                    "params_hash": params_hash,
                    "result_count": result_count,
                    "latency_ms": latency_ms,
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                }
            },
        )
