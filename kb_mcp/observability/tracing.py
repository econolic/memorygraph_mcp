from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator
from typing import TYPE_CHECKING
import uuid

if TYPE_CHECKING:
    from kb_mcp.config import AppConfig


request_id_var: ContextVar[str] = ContextVar("request_id", default="")

_tracing_enabled = False
_tracer = None
_tracing_initialized = False


def ensure_request_id() -> str:
    value = request_id_var.get()
    if value:
        return value
    value = str(uuid.uuid4())
    request_id_var.set(value)
    return value


def setup_tracing(cfg: "AppConfig") -> bool:
    global _tracing_enabled, _tracer, _tracing_initialized

    if _tracing_initialized:
        return _tracing_enabled
    _tracing_initialized = True

    if not cfg.otel_enabled:
        _tracing_enabled = False
        return False

    try:
        from opentelemetry import trace  # type: ignore[import-not-found]
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPGrpcSpanExporter  # type: ignore[import-not-found]
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHttpSpanExporter  # type: ignore[import-not-found]
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace import TracerProvider  # type: ignore[import-not-found]
        from opentelemetry.sdk.trace.export import BatchSpanProcessor  # type: ignore[import-not-found]
    except Exception:
        _tracing_enabled = False
        return False

    endpoint = cfg.otel_exporter_otlp_endpoint.strip()
    protocol = cfg.otel_exporter_otlp_protocol.strip().lower()
    resource = Resource.create({"service.name": cfg.service_name})
    provider = TracerProvider(resource=resource)

    exporter = None
    try:
        if protocol == "grpc":
            kwargs: dict[str, object] = {}
            if endpoint:
                kwargs["endpoint"] = endpoint
                kwargs["insecure"] = endpoint.startswith("http://")
            exporter = OTLPGrpcSpanExporter(**kwargs)
        else:
            kwargs = {}
            if endpoint:
                kwargs["endpoint"] = endpoint
            exporter = OTLPHttpSpanExporter(**kwargs)
    except Exception:
        _tracing_enabled = False
        return False

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(cfg.service_name)
    _tracing_enabled = True
    return True


@contextmanager
def start_span(name: str, *, attributes: dict[str, object] | None = None) -> Iterator[object | None]:
    if not _tracing_enabled or _tracer is None:
        yield None
        return
    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for key, value in attributes.items():
                if value is None:
                    continue
                span.set_attribute(key, value)
        yield span
