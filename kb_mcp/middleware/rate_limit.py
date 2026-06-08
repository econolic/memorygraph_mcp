from __future__ import annotations

import time
from threading import Lock


class TokenBucket:
    def __init__(self, rps: float, burst: int) -> None:
        self.rps = rps
        self.burst = burst
        self.tokens = float(burst)
        self.last_update = time.monotonic()
        self.lock = Lock()

    def consume(self) -> bool:
        with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_update
            self.last_update = now
            self.tokens = min(float(self.burst), self.tokens + elapsed * self.rps)
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


class RateLimiter:
    def __init__(self, rps: float, burst: int) -> None:
        self.rps = rps
        self.burst = burst
        self.buckets: dict[tuple[str, str, str], TokenBucket] = {}
        self.lock = Lock()

    def is_allowed(self, subject: str, workspace_id: str, tool_name: str) -> bool:
        key = (subject, workspace_id, tool_name)
        with self.lock:
            if key not in self.buckets:
                self.buckets[key] = TokenBucket(self.rps, self.burst)
            bucket = self.buckets[key]
        return bucket.consume()
