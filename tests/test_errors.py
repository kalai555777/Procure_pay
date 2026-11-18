"""Tests for the shared error format."""

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from pydantic import BaseModel, ConfigDict, Field

from procure_pay import tracing
from procure_pay.errors import (
    ClearbuyError,
    install_error_handlers,
    safe_validation_message,
)

REQUEST_ID = re.compile(r"req-[0-9a-f]{16}")


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=500)


def _client() -> TestClient:
    tracing.setup_tracing()
    test_app = FastAPI()
    install_error_handlers(test_app)

    @test_app.post("/refuse")
    def refuse() -> None:
        raise ClearbuyError("idempotency_key_missing", "Send an Idempotency-Key.", 400)

    @test_app.post("/check")
    def check(body: _Body) -> dict[str, str]:
        return {"summary": body.summary}

    @test_app.post("/fail")
    def fail() -> None:
        raise RuntimeError("secret detail")

    FastAPIInstrumentor.instrument_app(test_app)
    return TestClient(test_app, raise_server_exceptions=False)


def test_a_refusal_uses_the_shared_format() -> None:
    reply = _client().post("/refuse")
    assert reply.status_code == 400
    error = reply.json()["error"]
    assert error["code"] == "idempotency_key_missing"
    assert REQUEST_ID.fullmatch(error["request_id"])


def test_a_validation_error_never_echoes_what_was_sent() -> None:
    sent = {"summary": "", "secret_field": "secret-value"}
    reply = _client().post("/check", json=sent)
    assert reply.status_code == 422
    error = reply.json()["error"]
    assert error["code"] == "request_invalid"
    assert REQUEST_ID.fullmatch(error["request_id"])
    assert "summary" in error["message"]
    assert "secret-value" not in reply.text
    assert "secret_field" not in reply.text


def test_an_unexpected_error_is_internal_error_with_no_details() -> None:
    reply = _client().post("/fail")
    assert reply.status_code == 500
    assert reply.json()["error"]["code"] == "internal_error"
    assert "secret detail" not in reply.text


def test_a_validation_message_with_no_errors() -> None:
    assert safe_validation_message([]) == "The request is not valid."
