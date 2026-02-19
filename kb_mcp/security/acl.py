from __future__ import annotations

from dataclasses import dataclass


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
        out["workspace_id"] = ctx.workspace_id
        out["acl_subject"] = ctx.subject
        out["acl_roles"] = list(ctx.roles)
        return out
