"""Entry point for the Launchpad FastAPI backend."""

from fastapi import FastAPI

app = FastAPI(title="Launchpad", version="0.1.0")


@app.get("/health", tags=["meta"])
async def health() -> dict:
    """Return service health status. No authentication required."""
    return {"status": "ok", "version": "0.1.0"}
