from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Protocol

from kb_mcp.config import AppConfig
from kb_mcp.ingest.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)


class AutoIngestDeps(Protocol):
    @property
    def config(self) -> AppConfig: ...

    @property
    def ingestion(self) -> IngestionPipeline: ...


class AutoIngestService:
    def __init__(self, deps: AutoIngestDeps) -> None:
        self._deps = deps
        self._cfg = deps.config
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _roots(self) -> list[Path]:
        roots: list[Path] = []
        seen: set[str] = set()
        for root in self._cfg.auto_ingest_roots:
            normalized = root.strip()
            if not normalized:
                continue
            path = Path(normalized).expanduser().resolve()
            key = str(path)
            if key in seen:
                continue
            seen.add(key)
            roots.append(path)
        return roots

    def run_once(self, *, reason: str) -> dict[str, int]:
        summary = {
            "created": 0,
            "updated": 0,
            "processed_roots": 0,
            "skipped_roots": 0,
            "failed_roots": 0,
        }
        if not self._cfg.auto_ingest_enabled:
            return summary

        for root in self._roots():
            if not root.exists() or not root.is_dir():
                summary["skipped_roots"] += 1
                continue
            try:
                result = self._deps.ingestion.ingest_filesystem(
                    root=str(root),
                    workspace_id=self._cfg.auto_ingest_workspace_id,
                    acl_allow=[self._cfg.auto_ingest_acl_subject],
                )
                summary["created"] += int(result.get("created", 0))
                summary["updated"] += int(result.get("updated", 0))
                summary["processed_roots"] += 1
            except Exception:
                summary["failed_roots"] += 1
                logger.exception(
                    "auto_ingest_root_failed",
                    extra={"extra": {"root": str(root), "reason": reason}},
                )

        logger.info("auto_ingest_cycle", extra={"extra": {"reason": reason, **summary}})
        return summary

    def _run_loop(self) -> None:
        if self._cfg.auto_ingest_run_on_start:
            self.run_once(reason="startup")

        interval_s = max(5, int(self._cfg.auto_ingest_interval_s))
        while not self._stop.wait(interval_s):
            self.run_once(reason="interval")

    def start(self) -> None:
        if not self._cfg.auto_ingest_enabled:
            logger.info("auto_ingest_disabled")
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, name="kb-auto-ingest", daemon=True)
        self._thread.start()
        logger.info(
            "auto_ingest_started",
            extra={
                "extra": {
                    "roots": [str(path) for path in self._roots()],
                    "workspace_id": self._cfg.auto_ingest_workspace_id,
                    "subject": self._cfg.auto_ingest_acl_subject,
                    "interval_s": self._cfg.auto_ingest_interval_s,
                    "run_on_start": self._cfg.auto_ingest_run_on_start,
                }
            },
        )

    def stop(self, timeout_s: float = 3.0) -> None:
        self._stop.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=timeout_s)
