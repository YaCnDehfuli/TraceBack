"""Incident and run endpoints (P1-4). Stubs return 501 until implemented.

Rule: save the run document in Atlas BEFORE any LLM or tool call starts.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from contracts.models import IncidentCreate, IncidentCreated, MemoryMode, RunEvent, RunStarted, RunView
from core.auth import CurrentPrincipal

router = APIRouter(tags=["incidents and runs"])


def _todo(item: str) -> HTTPException:
    return HTTPException(status.HTTP_501_NOT_IMPLEMENTED, f"Not implemented yet ({item}).")


@router.post("/incidents", response_model=IncidentCreated, status_code=status.HTTP_201_CREATED)
def create_incident(body: IncidentCreate, principal: CurrentPrincipal) -> IncidentCreated:
    raise _todo("P1-4")


@router.post("/incidents/{incident_id}/runs", response_model=RunStarted, status_code=status.HTTP_202_ACCEPTED)
def start_run(
    incident_id: str,
    principal: CurrentPrincipal,
    memory: Annotated[MemoryMode, Query(description="Experiment switch: real | off | placebo")] = "real",
) -> RunStarted:
    raise _todo("P1-4")


@router.get("/runs/{run_id}", response_model=RunView)
def get_run(run_id: str, principal: CurrentPrincipal) -> RunView:
    raise _todo("P1-4")


@router.get("/runs/{run_id}/events", response_model=list[RunEvent])
def get_run_events(run_id: str, principal: CurrentPrincipal, after: int = 0) -> list[RunEvent]:
    """Events with seq > `after`, in order. The UI polls this every second or two."""
    raise _todo("P1-4")
