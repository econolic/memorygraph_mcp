from __future__ import annotations

import uuid
from contextvars import ContextVar


request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def ensure_request_id() -> str:
    value = request_id_var.get()
    if value:
        return value
    value = str(uuid.uuid4())
    request_id_var.set(value)
    return value
