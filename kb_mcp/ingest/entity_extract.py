from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class EntityExtractionConfig:
    min_symbol_len: int = 3
    min_term_len: int = 3
    symbol_allow_pattern: str = r"^[A-Za-z_][A-Za-z0-9_]{2,}$"
    table_allow_pattern: str = r"^[a-z_]+\.[a-z_]+$"
    term_allow_pattern: str = r"^[А-Яа-яЁё][А-Яа-яЁё0-9_\-]{2,}$"
    stopwords: tuple[str, ...] = (
        "the",
        "and",
        "with",
        "from",
        "that",
        "this",
        "for",
        "are",
        "или",
        "как",
        "для",
        "это",
        "что",
        "при",
        "class",
        "def",
        "import",
        "return",
        "true",
        "false",
        "none",
    )


@dataclass(frozen=True)
class _EntityMatch:
    uri: str
    alias: str
    start: int
    end: int


_TABLE_RE = re.compile(r"\b([a-z_]+\.[a-z_]+)\b", re.IGNORECASE)
_SYMBOL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]{2,})\b")
_CYR_RE = re.compile(r"\b([А-Яа-яЁё][А-Яа-яЁё0-9_\-]{2,})\b")

_RELATION_TRIGGERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bdepends\s+on\b|\bзависит\s+от\b", re.IGNORECASE), "DEPENDS_ON"),
    (re.compile(r"\bcalls\b|\bвызывает\b", re.IGNORECASE), "CALLS"),
    (re.compile(r"\bowns\b|\bвладеет\b", re.IGNORECASE), "OWNS"),
    (re.compile(r"\bimplements\b|\bреализует\b", re.IGNORECASE), "IMPLEMENTS"),
    (re.compile(r"\baffects\b|\bвлияет\s+на\b", re.IGNORECASE), "AFFECTS"),
)


def _entity_uri(prefix: str, value: str) -> str:
    return f"kb://entity/{prefix}:{value}"


def _fullmatch(pattern: str, value: str) -> bool:
    try:
        return re.fullmatch(pattern, value) is not None
    except re.error:
        return True


def _is_stopword(value: str, cfg: EntityExtractionConfig) -> bool:
    return value.strip().lower() in set(cfg.stopwords)


def _normalize_symbol(value: str) -> str:
    return value.strip().lower()


def _normalize_term(value: str) -> str:
    return value.strip().lower()


def _extract_matches(text: str, cfg: EntityExtractionConfig) -> list[_EntityMatch]:
    out: list[_EntityMatch] = []

    for match in _TABLE_RE.finditer(text):
        raw = match.group(1).strip()
        normalized = raw.lower()
        if not normalized or _is_stopword(normalized, cfg):
            continue
        if not _fullmatch(cfg.table_allow_pattern, normalized):
            continue
        out.append(
            _EntityMatch(
                uri=_entity_uri("table", normalized),
                alias=raw,
                start=match.start(1),
                end=match.end(1),
            )
        )

    for match in _SYMBOL_RE.finditer(text):
        raw = match.group(1).strip()
        normalized = _normalize_symbol(raw)
        if len(normalized) < cfg.min_symbol_len or _is_stopword(normalized, cfg):
            continue
        if not _fullmatch(cfg.symbol_allow_pattern, raw):
            continue
        out.append(
            _EntityMatch(
                uri=_entity_uri("symbol", normalized),
                alias=raw,
                start=match.start(1),
                end=match.end(1),
            )
        )

    for match in _CYR_RE.finditer(text):
        raw = match.group(1).strip()
        normalized = _normalize_term(raw)
        if len(normalized) < cfg.min_term_len or _is_stopword(normalized, cfg):
            continue
        if not _fullmatch(cfg.term_allow_pattern, raw):
            continue
        out.append(
            _EntityMatch(
                uri=_entity_uri("term", normalized),
                alias=raw,
                start=match.start(1),
                end=match.end(1),
            )
        )

    out.sort(key=lambda item: (item.start, item.end, item.uri))
    return out


def extract_entities(
    text: str,
    cfg: EntityExtractionConfig | None = None,
) -> list[str]:
    cfg = cfg or EntityExtractionConfig()
    seen: set[str] = set()
    ordered: list[str] = []
    for match in _extract_matches(text, cfg):
        if match.uri in seen:
            continue
        seen.add(match.uri)
        ordered.append(match.uri)
    return ordered


def extract_entity_aliases(
    text: str,
    cfg: EntityExtractionConfig | None = None,
) -> dict[str, list[str]]:
    cfg = cfg or EntityExtractionConfig()
    out: dict[str, list[str]] = {}
    for match in _extract_matches(text, cfg):
        aliases = out.setdefault(match.uri, [])
        alias = match.alias.strip()
        if alias and alias not in aliases:
            aliases.append(alias)
    return out


def entity_display_name(entity_uri: str) -> str:
    suffix = entity_uri.split("kb://entity/")[-1]
    if ":" in suffix:
        return suffix.split(":", 1)[1]
    return suffix


def _nearest_entity(
    matches: list[_EntityMatch],
    *,
    pivot: int,
    side: str,
    max_distance: int = 220,
) -> _EntityMatch | None:
    candidates: list[tuple[int, _EntityMatch]] = []
    for match in matches:
        if side == "left" and match.end <= pivot:
            dist = pivot - match.end
        elif side == "right" and match.start >= pivot:
            dist = match.start - pivot
        else:
            continue
        if dist <= max_distance:
            candidates.append((dist, match))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def _two_nearest_distinct(
    matches: list[_EntityMatch],
    *,
    pivot: int,
    max_distance: int = 240,
) -> tuple[_EntityMatch | None, _EntityMatch | None]:
    ranked = sorted(
        (
            (min(abs(match.start - pivot), abs(match.end - pivot)), idx, match)
            for idx, match in enumerate(matches)
            if min(abs(match.start - pivot), abs(match.end - pivot)) <= max_distance
        ),
        key=lambda item: (item[0], item[1]),
    )
    first: _EntityMatch | None = None
    second: _EntityMatch | None = None
    for _dist, _idx, match in ranked:
        if first is None:
            first = match
            continue
        if match.uri != first.uri:
            second = match
            break
    return first, second


def extract_entity_relations(
    text: str,
    entity_uris: list[str],
    cfg: EntityExtractionConfig | None = None,
) -> list[dict[str, str]]:
    cfg = cfg or EntityExtractionConfig()
    entity_set = set(entity_uris)
    if len(entity_set) < 2:
        return []

    matches = [match for match in _extract_matches(text, cfg) if match.uri in entity_set]
    if len(matches) < 2:
        return []

    relations: list[dict[str, str]] = []
    seen_triplets: set[tuple[str, str, str]] = set()

    for pattern, rel_type in _RELATION_TRIGGERS:
        for trigger in pattern.finditer(text):
            left = _nearest_entity(matches, pivot=trigger.start(), side="left")
            right = _nearest_entity(matches, pivot=trigger.end(), side="right")
            if left is None or right is None or left.uri == right.uri:
                left, right = _two_nearest_distinct(matches, pivot=trigger.start())
            if left is None or right is None or left.uri == right.uri:
                continue
            triplet = (left.uri, rel_type, right.uri)
            if triplet in seen_triplets:
                continue
            seen_triplets.add(triplet)
            relations.append({"src": left.uri, "dst": right.uri, "rel": rel_type})

    return relations
