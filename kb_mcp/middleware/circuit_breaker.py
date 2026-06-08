from __future__ import annotations

import time
from threading import Lock
from typing import Literal

State = Literal["CLOSED", "OPEN", "HALF_OPEN"]


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state: State = "CLOSED"
        self.failures = 0
        self.last_state_change = time.monotonic()
        self.lock = Lock()

    def record_success(self) -> None:
        with self.lock:
            self.failures = 0
            self.state = "CLOSED"

    def record_failure(self) -> None:
        with self.lock:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.state = "OPEN"
                self.last_state_change = time.monotonic()

    def allow_request(self) -> bool:
        with self.lock:
            now = time.monotonic()
            if self.state == "OPEN":
                if now - self.last_state_change > self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    self.last_state_change = now
                    return True
                return False
            return True
