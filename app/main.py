"""CarChat web service. Routes are added step by step; see README."""

from fastapi import FastAPI

app = FastAPI(title="CarChat", docs_url=None, redoc_url=None)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    """Liveness check for the host. Touches nothing secret."""
    return {"status": "ok"}
