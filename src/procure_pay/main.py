"""The Clearbuy API: the FastAPI application and its routes."""

from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from procure_pay.errors import install_error_handlers
from procure_pay.purchases import router as purchases_router
from procure_pay.tracing import setup_tracing

setup_tracing()

app = FastAPI(title="Clearbuy")
install_error_handlers(app)
app.include_router(purchases_router)
FastAPIInstrumentor.instrument_app(app)


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the API is running.

    Returns:
        A dictionary with "status" set to "ok".
    """
    return {"status": "ok"}
