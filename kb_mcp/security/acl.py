from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class AccessContext:
    subject: str
    roles: tuple[str, ...]
    workspace_id: str


class AclService:
    def __init__(self, deny_by_default: bool = True) -> None:
        self._deny = deny_by_default

    def can_read(self, *, ctx: AccessContext, acl_allow: list[str] | None) -> bool:
        if not acl_allow:
            return not self._deny

        allowed = set(acl_allow)
        if ctx.subject in allowed:
            return True

        for role in ctx.roles:
            if f"role:{role}" in allowed:
                return True
        return False

    def apply_filters(self, *, ctx: AccessContext, filters: dict[str, object]) -> dict[str, object]:
        out = dict(filters)
        tags = out.get("tags", [])
        if isinstance(tags, list):
            out["tags"] = [str(tag).strip() for tag in tags if str(tag).strip()]
        sources = out.get("sources", [])
        if isinstance(sources, list):
            out["sources"] = [str(source).strip() for source in sources if str(source).strip()]

        updated_after = out.get("updated_after")
        if isinstance(updated_after, datetime):
            dt = updated_after
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            out["updated_after"] = dt.astimezone(timezone.utc).isoformat()
        elif isinstance(updated_after, str):
            raw = updated_after.strip()
            if raw.endswith("Z"):
                raw = f"{raw[:-1]}+00:00"
            try:
                dt = datetime.fromisoformat(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                out["updated_after"] = dt.astimezone(timezone.utc).isoformat()
            except ValueError:
                out["updated_after"] = None

        out["workspace_id"] = ctx.workspace_id
        out["acl_subject"] = ctx.subject
        out["acl_roles"] = list(ctx.roles)
        return out
