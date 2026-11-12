"""The Clearbuy API: the FastAPI application and its routes."""

from fastapi import FastAPI

app = FastAPI(title="Clearbuy")


@app.get("/health")
def health() -> dict[str, str]:
    """Report that the API is running.

    Returns:
        A dictionary with "status" set to "ok".
    """
    return {"status": "ok"}
