from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch

from kb_mcp.config import AppConfig
from kb_mcp.ingest.auto_ingest import AutoIngestService


class FakeIngestion:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def ingest_filesystem(self, *, root: str, workspace_id: str, acl_allow: list[str]) -> dict[str, int]:
        self.calls.append({"root": root, "workspace_id": workspace_id, "acl_allow": list(acl_allow)})
        return {"created": 1, "updated": 2}


def test_auto_ingest_run_once_processes_existing_roots(tmp_path: Path) -> None:
    root = tmp_path / "content"
    root.mkdir()
    fake = FakeIngestion()
    cfg = AppConfig(
        auto_ingest_enabled=True,
        auto_ingest_roots=(str(root), str(root)),
        auto_ingest_workspace_id="w1",
        auto_ingest_acl_subject="u1",
    )
    deps = SimpleNamespace(config=cfg, ingestion=fake)
    service = AutoIngestService(deps)

    summary = service.run_once(reason="test")

    assert summary["created"] == 1
    assert summary["updated"] == 2
    assert summary["processed_roots"] == 1
    assert summary["failed_roots"] == 0
    assert len(fake.calls) == 1
    assert fake.calls[0]["workspace_id"] == "w1"
    assert fake.calls[0]["acl_allow"] == ["u1"]


def test_auto_ingest_run_once_skips_missing_root(tmp_path: Path) -> None:
    fake = FakeIngestion()
    missing = tmp_path / "missing"
    cfg = AppConfig(
        auto_ingest_enabled=True,
        auto_ingest_roots=(str(missing),),
    )
    deps = SimpleNamespace(config=cfg, ingestion=fake)
    service = AutoIngestService(deps)

    summary = service.run_once(reason="test")

    assert summary["created"] == 0
    assert summary["updated"] == 0
    assert summary["processed_roots"] == 0
    assert summary["skipped_roots"] == 1
    assert len(fake.calls) == 0


def test_app_config_parses_auto_ingest_env(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setenv("KB_AUTO_INGEST_ENABLED", "false")
    monkeypatch.setenv("KB_AUTO_INGEST_ROOTS", " /x , /y ")
    monkeypatch.setenv("KB_AUTO_INGEST_WORKSPACE_ID", "w_env")
    monkeypatch.setenv("KB_AUTO_INGEST_ACL_SUBJECT", "u_env")
    monkeypatch.setenv("KB_AUTO_INGEST_INTERVAL_S", "42")
    monkeypatch.setenv("KB_AUTO_INGEST_RUN_ON_START", "false")

    cfg = AppConfig.from_env()

    assert cfg.auto_ingest_enabled is False
    assert cfg.auto_ingest_roots == ("/x", "/y")
    assert cfg.auto_ingest_workspace_id == "w_env"
    assert cfg.auto_ingest_acl_subject == "u_env"
    assert cfg.auto_ingest_interval_s == 42
    assert cfg.auto_ingest_run_on_start is False
