"""Trace IDs and request IDs for Clearbuy (P3, records)."""

from opentelemetry import trace
from opentelemetry.context import Context
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.textmap import (
    CarrierT,
    Getter,
    Setter,
    TextMapPropagator,
    default_getter,
    default_setter,
)
from opentelemetry.sdk.trace import TracerProvider

REQUEST_ID_PREFIX = "req-"


class _IgnoreIncomingTraces(TextMapPropagator):
    """A propagator that reads and writes no trace headers."""

    def extract(
        self,
        carrier: CarrierT,
        context: Context | None = None,
        getter: Getter[CarrierT] = default_getter,
    ) -> Context:
        """Return the given context, or a fresh empty one: never an outside trace."""
        return context if context is not None else Context()

    def inject(
        self,
        carrier: CarrierT,
        context: Context | None = None,
        setter: Setter[CarrierT] = default_setter,
    ) -> None:
        """Write no trace headers."""

    @property
    def fields(self) -> set[str]:
        """Name no headers."""
        return set()


def setup_tracing() -> None:
    """Install the SDK once, and ignore trace headers sent from outside.

    Every request then starts a fresh, random trace, as Appendix F requires
    of the request ID (made by L1, random).
    """
    if not isinstance(trace.get_tracer_provider(), TracerProvider):
        trace.set_tracer_provider(TracerProvider())
    set_global_textmap(_IgnoreIncomingTraces())


def format_trace_id(trace_id: int) -> str:
    """Return a trace ID as its 32 lowercase hex characters."""
    return trace.format_trace_id(trace_id)


def request_id_for(trace_id: int) -> str:
    """Return the request ID: "req-" and the first 16 characters of the trace ID."""
    return REQUEST_ID_PREFIX + format_trace_id(trace_id)[:16]


def current_trace_id() -> int:
    """Return the current span's trace ID; fail if no span is active."""
    span_context = trace.get_current_span().get_span_context()
    if not span_context.is_valid:
        raise RuntimeError("No active span: start one before asking for the request ID")
    return span_context.trace_id
