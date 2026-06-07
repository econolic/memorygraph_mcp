from __future__ import annotations

import logging
import threading
from time import perf_counter, sleep
from pathlib import Path
from typing import Protocol

from kb_mcp.config import AppConfig
from kb_mcp.ingest.pipeline import IngestionPipeline

logger = logging.getLogger(__name__)


def _result_counter(result: dict[str, object], key: str) -> int:
    value = result.get(key, 0)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


class AutoIngestDeps(Protocol):
    @property
    def config(self) -> AppConfig: ...

    @property
    def ingestion(self) -> IngestionPipeline: ...

    @property
    def metrics(self) -> object: ...


class AutoIngestService:
    def __init__(self, deps: AutoIngestDeps) -> None:
        self._deps = deps
        self._cfg = deps.config
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._cycle_index = 0

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
        t0 = perf_counter()
        summary = {
            "created": 0,
            "updated": 0,
            "processed_roots": 0,
            "skipped_roots": 0,
            "failed_roots": 0,
            "git_diff_roots": 0,
            "full_roots": 0,
            "retried_roots": 0,
        }
        if not self._cfg.auto_ingest_enabled:
            metrics = getattr(self._deps, "metrics", None)
            if metrics is not None:
                metrics.inc("auto_ingest.cycle", labels={"reason": reason, "status": "disabled"})
                metrics.observe("auto_ingest.cycle.latency_ms", (perf_counter() - t0) * 1000.0)
            return summary

        self._cycle_index += 1
        full_interval = max(1, int(self._cfg.auto_ingest_full_interval_cycles))
        force_full = reason == "startup" or self._cycle_index % full_interval == 0

        for root in self._roots():
            if not root.exists() or not root.is_dir():
                summary["skipped_roots"] += 1
                continue
            method = "filesystem" if force_full else "git_diff"
            try:
                result, attempts = self._ingest_root(
                    root=root,
                    method=method,
                    reason=reason,
                )
                summary["created"] += _result_counter(result, "created")
                summary["updated"] += _result_counter(result, "updated")
                summary["processed_roots"] += 1
                if method == "git_diff":
                    summary["git_diff_roots"] += 1
                else:
                    summary["full_roots"] += 1
                if attempts > 1:
                    summary["retried_roots"] += 1
            except Exception:
                summary["failed_roots"] += 1
                logger.exception(
                    "auto_ingest_root_failed",
                    extra={"extra": {"root": str(root), "reason": reason, "method": method}},
                )

        logger.info("auto_ingest_cycle", extra={"extra": {"reason": reason, **summary}})
        metrics = getattr(self._deps, "metrics", None)
        if metrics is not None:
            status = "failed" if summary["failed_roots"] > 0 else "ok"
            metrics.inc("auto_ingest.cycle", labels={"reason": reason, "status": status})
            if summary["failed_roots"] > 0:
                metrics.inc("auto_ingest.failed_roots", n=int(summary["failed_roots"]))
            if summary["retried_roots"] > 0:
                metrics.inc("auto_ingest.retried_roots", n=int(summary["retried_roots"]))
            metrics.observe("auto_ingest.cycle.latency_ms", (perf_counter() - t0) * 1000.0)
        return summary

    def _ingest_root(self, *, root: Path, method: str, reason: str) -> tuple[dict[str, object], int]:
        max_attempts = max(1, int(self._cfg.auto_ingest_retry_attempts))
        base_backoff = max(0.1, float(self._cfg.auto_ingest_retry_backoff_s))
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                if method == "git_diff":
                    return (
                        self._deps.ingestion.ingest_git_diff(
                            root=str(root),
                            workspace_id=self._cfg.auto_ingest_workspace_id,
                            acl_allow=[self._cfg.auto_ingest_acl_subject],
                            since_ref=self._cfg.auto_ingest_git_since_ref,
                        ),
                        attempt,
                    )
                return (
                    self._deps.ingestion.ingest_filesystem(
                        root=str(root),
                        workspace_id=self._cfg.auto_ingest_workspace_id,
                        acl_allow=[self._cfg.auto_ingest_acl_subject],
                    ),
                    attempt,
                )
            except Exception as exc:
                last_error = exc
                metrics = getattr(self._deps, "metrics", None)
                if metrics is not None:
                    metrics.inc(
                        "auto_ingest.root_failure",
                        labels={
                            "reason": reason,
                            "method": method,
                            "error_kind": exc.__class__.__name__,
                        },
                    )
                if attempt >= max_attempts:
                    break
                backoff_s = base_backoff * (2 ** (attempt - 1))
                logger.warning(
                    "auto_ingest_retry",
                    extra={
                        "extra": {
                            "root": str(root),
                            "reason": reason,
                            "method": method,
                            "attempt": attempt,
                            "max_attempts": max_attempts,
                            "backoff_s": backoff_s,
                            "error_kind": exc.__class__.__name__,
                        }
                    },
                )
                sleep(backoff_s)
        if last_error is not None:
            raise last_error
        raise RuntimeError("auto_ingest_unknown_failure")

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
