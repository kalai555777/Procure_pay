"""Clearbuy's one error format (AD-065): reason code, safe message, request ID."""

import logging
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from procure_pay import tracing

logger = logging.getLogger(__name__)

INTERNAL_ERROR_MESSAGE = "Something went wrong. Quote the request ID if you report it."
FRAMEWORK_ERROR_CODES = {404: "not_found", 405: "method_not_allowed"}


class ClearbuyError(Exception):
    """A refusal Clearbuy expects: a reason code, a safe message, an HTTP status."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        """Keep the reason code, the safe message, and the HTTP status."""
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def current_request_id() -> str | None:
    """Return the current request's ID, or None outside any span."""
    try:
        return tracing.request_id_for(tracing.current_trace_id())
    except RuntimeError:
        return None


def error_response(
    code: str,
    message: str,
    status_code: int,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build a reply in the shared error format, with any headers to pass on."""
    body = {
        "error": {"code": code, "message": message, "request_id": current_request_id()}
    }
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def safe_validation_message(errors: Sequence[Any]) -> str:
    """Describe what failed using field names only, never submitted values."""
    names = sorted(
        {
            str(error["loc"][-1])
            for error in errors
            if error.get("type") != "extra_forbidden"
        }
    )
    parts = [f"check {', '.join(names)}"] if names else []
    if any(error.get("type") == "extra_forbidden" for error in errors):
        parts.append("other fields are not allowed")
    return (
        f"The request is not valid: {'; '.join(parts)}."
        if parts
        else "The request is not valid."
    )


def _handle_clearbuy_error(request: Request, exc: Exception) -> JSONResponse:
    error = (
        exc
        if isinstance(exc, ClearbuyError)
        else ClearbuyError("internal_error", INTERNAL_ERROR_MESSAGE, 500)
    )
    return error_response(error.code, error.message, error.status_code)


def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    errors = exc.errors() if isinstance(exc, RequestValidationError) else []
    return error_response("request_invalid", safe_validation_message(errors), 422)


def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unexpected error: %s", type(exc).__name__)
    return error_response("internal_error", INTERNAL_ERROR_MESSAGE, 500)


def _handle_framework_error(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, StarletteHTTPException):
        code = FRAMEWORK_ERROR_CODES.get(exc.status_code, "http_error")
        phrase = HTTPStatus(exc.status_code).phrase
        return error_response(code, phrase, exc.status_code, headers=exc.headers)
    return _handle_unexpected_error(request, exc)


def install_error_handlers(app: FastAPI) -> None:
    """Send every refusal through the shared error format."""
    app.add_exception_handler(ClearbuyError, _handle_clearbuy_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_framework_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)
