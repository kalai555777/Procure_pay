"""Tests for trace IDs and request IDs."""

import re

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from procure_pay import tracing

EXAMPLE_TRACE_ID = 0x4BF92F3577B34DA6A3CE929D0E0E4736


def test_request_id_is_req_and_the_first_16_characters() -> None:
    assert (
        tracing.format_trace_id(EXAMPLE_TRACE_ID) == "4bf92f3577b34da6a3ce929d0e0e4736"
    )
    assert tracing.request_id_for(EXAMPLE_TRACE_ID) == "req-4bf92f3577b34da6"


def test_small_trace_ids_keep_their_leading_zeros() -> None:
    assert tracing.format_trace_id(1) == "0" * 31 + "1"
    assert tracing.request_id_for(1) == "req-" + "0" * 16


def test_setup_tracing_is_safe_to_call_twice() -> None:
    tracing.setup_tracing()
    tracing.setup_tracing()
    assert isinstance(trace.get_tracer_provider(), TracerProvider)


def test_current_trace_id_inside_a_span() -> None:
    tracing.setup_tracing()
    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("submit") as span:
        trace_id = tracing.current_trace_id()
        assert trace_id == span.get_span_context().trace_id
        assert re.fullmatch(r"req-[0-9a-f]{16}", tracing.request_id_for(trace_id))


def test_current_trace_id_without_a_span_fails() -> None:
    with pytest.raises(RuntimeError):
        tracing.current_trace_id()
