from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reasons: list[str]


class MemoryFactValidator:
    def __init__(self, *, confidence_threshold: float) -> None:
        self._threshold = confidence_threshold

    def validate(
        self,
        *,
        memory_type: str,
        text: str,
        citations: list[dict[str, object]],
        confidence: float,
    ) -> ValidationResult:
        reasons: list[str] = []

        if not text.strip():
            reasons.append("empty_text")

        allowed_types = {"summary", "fact", "decision", "preference"}
        if memory_type not in allowed_types:
            reasons.append("invalid_type")

        if not citations:
            reasons.append("missing_citations")

        if confidence < self._threshold:
            reasons.append("low_confidence")

        # Minimal schema-style checks for facts.
        if memory_type == "fact":
            if len(text.split()) < 3:
                reasons.append("fact_too_short")
            if ":" not in text and "=" not in text:
                reasons.append("fact_schema_mismatch")

        return ValidationResult(ok=not reasons, reasons=reasons)
