from __future__ import annotations

from kb_mcp.security.acl import AccessContext, AclService


def test_acl_deny_by_default() -> None:
    acl = AclService(deny_by_default=True)
    ctx = AccessContext(subject="u1", roles=(), workspace_id="w1")
    assert acl.can_read(ctx=ctx, acl_allow=None) is False


def test_acl_subject_allowed() -> None:
    acl = AclService(deny_by_default=True)
    ctx = AccessContext(subject="u1", roles=(), workspace_id="w1")
    assert acl.can_read(ctx=ctx, acl_allow=["u1"]) is True


def test_acl_role_allowed() -> None:
    acl = AclService(deny_by_default=True)
    ctx = AccessContext(subject="u1", roles=("admin",), workspace_id="w1")
    assert acl.can_read(ctx=ctx, acl_allow=["role:admin"]) is True
