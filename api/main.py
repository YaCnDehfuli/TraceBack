"""FastAPI app: our routes, P2's memory router, and the web UI served from web/.

uv run uvicorn api.main:app --reload --port 8000     ->  http://localhost:8000
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api import routes
from contracts.models import Principal
from core.auth import CurrentPrincipal
from memory.router import router as memory_router

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
SAMPLE_EVENTS = ROOT / "contracts" / "sample_run_events.json"

app = FastAPI(title="Traceback", version="0.1.0", description="Memory with receipts.")


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "traceback"}


@app.get("/whoami", response_model=Principal, tags=["meta"])
def whoami(principal: CurrentPrincipal) -> Principal:
    """Who the current API key acts as. Feeds the identity pill."""
    return principal


@app.get("/dev/sample-run-events", tags=["meta"])
def sample_run_events() -> list[dict]:
    """contracts/sample_run_events.json, so the UI can render a run before the agent exists."""
    return json.loads(SAMPLE_EVENTS.read_text(encoding="utf-8"))


app.include_router(routes.router)
app.include_router(memory_router)

# Must stay last: serves web/index.html at "/" and the JS files next to it.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
