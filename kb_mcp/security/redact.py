from __future__ import annotations

import re


_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)([A-Za-z0-9_\-]{8,})"),
    re.compile(r"(?i)(secret\s*[:=]\s*)([A-Za-z0-9_\-]{8,})"),
    re.compile(r"(?i)(password\s*[:=]\s*)([^\s]{4,})"),
]

_PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\+?\d[\d\-\s]{7,}\d"),
]


class RedactionService:
    def redact(self, text: str) -> str:
        result = text
        for pattern in _SECRET_PATTERNS:
            result = pattern.sub(r"\1***", result)
        for pattern in _PII_PATTERNS:
            result = pattern.sub("***", result)
        return result
