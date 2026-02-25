from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator, Mapping, Sequence
from typing import TYPE_CHECKING, Any
import uuid

if TYPE_CHECKING:
    from kb_mcp.config import AppConfig


request_id_var: ContextVar[str] = ContextVar("request_id", default="")
SpanAttributeValue = (
    str | bool | int | float | Sequence[str] | Sequence[bool] | Sequence[int] | Sequence[float]
)

_tracing_enabled = False
_tracer: Any | None = None
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
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter as OTLPGrpcSpanExporter
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter as OTLPHttpSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:
        _tracing_enabled = False
        return False

    endpoint = cfg.otel_exporter_otlp_endpoint.strip()
    protocol = cfg.otel_exporter_otlp_protocol.strip().lower()
    resource = Resource.create({"service.name": cfg.service_name})
    provider = TracerProvider(resource=resource)

    exporter: Any
    try:
        if protocol == "grpc":
            if endpoint:
                exporter = OTLPGrpcSpanExporter(
                    endpoint=endpoint,
                    insecure=endpoint.startswith("http://"),
                )
            else:
                exporter = OTLPGrpcSpanExporter()
        else:
            if endpoint:
                exporter = OTLPHttpSpanExporter(endpoint=endpoint)
            else:
                exporter = OTLPHttpSpanExporter()
    except Exception:
        _tracing_enabled = False
        return False

    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(cfg.service_name)
    _tracing_enabled = True
    return True


@contextmanager
def start_span(
    name: str,
    *,
    attributes: Mapping[str, SpanAttributeValue] | None = None,
) -> Iterator[object | None]:
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
