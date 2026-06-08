from __future__ import annotations

import secrets
import time
from threading import Lock
from typing import Any


class ConfirmationGate:
    def __init__(self, expiry_seconds: float = 300.0) -> None:
        self.expiry_seconds = expiry_seconds
        self.pending: dict[str, tuple[float, dict[str, Any]]] = {}
        self.lock = Lock()

    def generate_token(self, data: dict[str, Any]) -> str:
        token = "token_" + secrets.token_hex(16)
        expiry = time.monotonic() + self.expiry_seconds
        with self.lock:
            self.pending[token] = (expiry, data)
        return token

    def validate_and_invalidate(self, token: str) -> dict[str, Any] | None:
        now = time.monotonic()
        with self.lock:
            # Clean expired
            expired = [t for t, (exp, _) in self.pending.items() if exp < now]
            for t in expired:
                self.pending.pop(t, None)

            if token not in self.pending:
                return None
            expiry, data = self.pending.pop(token)
            if expiry < now:
                return None
            return data
