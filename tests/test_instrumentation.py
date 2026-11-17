"""Tests that every request gets its own fresh trace, seen by def routes."""

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from procure_pay import tracing
from procure_pay.main import app

OUTSIDE_TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"


def _app_reporting_its_request_id() -> FastAPI:
    tracing.setup_tracing()
    test_app = FastAPI()

    @test_app.get("/request-id")
    def request_id() -> dict[str, str]:
        return {"request_id": tracing.request_id_for(tracing.current_trace_id())}

    FastAPIInstrumentor.instrument_app(test_app)
    return test_app


def test_a_def_route_sees_the_request_span() -> None:
    reply = TestClient(_app_reporting_its_request_id()).get("/request-id")
    assert re.fullmatch(r"req-[0-9a-f]{16}", reply.json()["request_id"])


def test_outside_trace_headers_are_ignored() -> None:
    header = {"traceparent": f"00-{OUTSIDE_TRACE_ID}-00f067aa0ba902b7-01"}
    client = TestClient(_app_reporting_its_request_id())
    reply = client.get("/request-id", headers=header)
    assert reply.json()["request_id"] != "req-" + OUTSIDE_TRACE_ID[:16]


def test_two_requests_get_different_request_ids() -> None:
    client = TestClient(_app_reporting_its_request_id())
    first = client.get("/request-id").json()["request_id"]
    second = client.get("/request-id").json()["request_id"]
    assert first != second


def test_the_clearbuy_app_is_instrumented() -> None:
    assert getattr(app, "_is_instrumented_by_opentelemetry", False)
