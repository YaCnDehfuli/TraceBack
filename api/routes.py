"""Incident and run endpoints (P1-4). The logic lives in api/runs.py (RunService).

Rule: the run document is saved BEFORE any LLM or tool call starts; the work runs in the background.
Scope: every call is checked against the caller's tenant, team and authorized repositories.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.runs import RunError, RunService, get_service
from contracts.models import IncidentCreate, IncidentCreated, MemoryMode, RunEvent, RunStarted, RunView
from core.auth import CurrentPrincipal

router = APIRouter(tags=["incidents and runs"])

Service = Annotated[RunService, Depends(get_service)]


def _http(e: RunError) -> HTTPException:
    return HTTPException(e.status_code, e.message)


@router.post("/incidents", response_model=IncidentCreated, status_code=status.HTTP_201_CREATED)
def create_incident(body: IncidentCreate, principal: CurrentPrincipal, service: Service) -> IncidentCreated:
    """With `caseId`, the logs and request come from cases/<caseId>/manifest.json."""
    try:
        return IncidentCreated(incident_id=service.create_incident(principal, body))
    except RunError as e:
        raise _http(e) from None


@router.post("/incidents/{incident_id}/runs", response_model=RunStarted, status_code=status.HTTP_202_ACCEPTED)
def start_run(
    incident_id: str,
    principal: CurrentPrincipal,
    service: Service,
    memory: Annotated[MemoryMode, Query(description="Experiment switch: real | off | placebo")] = "real",
) -> RunStarted:
    try:
        return RunStarted(run_id=service.start_run(principal, incident_id, memory), status="queued")
    except RunError as e:
        raise _http(e) from None


@router.get("/runs/{run_id}", response_model=RunView)
def get_run(run_id: str, principal: CurrentPrincipal, service: Service) -> RunView:
    try:
        return service.get_run(principal, run_id)
    except RunError as e:
        raise _http(e) from None


@router.get("/runs/{run_id}/events", response_model=list[RunEvent])
def get_run_events(run_id: str, principal: CurrentPrincipal, service: Service, after: int = 0) -> list[RunEvent]:
    """Events with seq > `after`, in order. The UI polls this every second or two."""
    try:
        return service.events(principal, run_id, after)
    except RunError as e:
        raise _http(e) from None
