"""Incident and run endpoints.

    POST /incidents                     {repositoryId, caseId}            -> {incidentId}
    POST /incidents/{id}/runs?memory=   (Idempotency-Key header optional)  -> {runId, status}  202
    GET  /runs/{id}                                                        -> RunView
    GET  /runs/{id}/events?after=N                                         -> [RunEvent], seq > N

A team only sees its own incidents and runs (others get 404, never 403, so nothing leaks).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from api.deps import get_agent_deps, get_repo
from api.runs import AgentDeps, RunRepo, case_title, load_case, run_view, start_run, visible_to
from contracts.models import (
    IncidentCreate,
    IncidentCreated,
    MemoryMode,
    RunEvent,
    RunStarted,
    RunView,
)
from core.auth import CurrentPrincipal
from core.clock import new_id, utc_now

router = APIRouter(tags=["incidents and runs"])
Repo = Annotated[RunRepo, Depends(get_repo)]
Deps = Annotated[AgentDeps, Depends(get_agent_deps)]


def _not_found(what: str) -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, f"No such {what} for your team.")


@router.post("/incidents", response_model=IncidentCreated, status_code=status.HTTP_201_CREATED)
def create_incident(body: IncidentCreate, principal: CurrentPrincipal, repo: Repo) -> IncidentCreated:
    case = load_case(body.case_id or "")
    if case is None:
        raise HTTPException(422, "caseId must name a case in cases/.")
    if case.repository_id not in principal.authorized_repos or body.repository_id != case.repository_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Your team may not work on {body.repository_id}.")
    incident_id = new_id("inc")
    repo.insert_incident(
        {
            "_id": incident_id,
            "tenantId": principal.tenant_id,
            "teamId": principal.team_id,
            "caseId": case.case_id,
            "repositoryId": case.repository_id,
            "title": case_title(case.case_id),
            "createdAt": utc_now(),
        }
    )
    return IncidentCreated(incident_id=incident_id)


@router.post("/incidents/{incident_id}/runs", response_model=RunStarted, status_code=status.HTTP_202_ACCEPTED)
def start_incident_run(
    incident_id: str,
    principal: CurrentPrincipal,
    repo: Repo,
    deps: Deps,
    memory: Annotated[MemoryMode, Query(description="Experiment switch: real | off | placebo")] = "real",
    idempotency_key: Annotated[str | None, Header()] = None,
) -> RunStarted:
    incident = repo.get_incident(principal.tenant_id, incident_id)
    if not visible_to(incident, principal):
        raise _not_found("incident")
    case = load_case(incident["caseId"])
    if case is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "This incident's case no longer exists.")
    doc = start_run(repo, deps, principal, incident, case, memory, idempotency_key)
    return RunStarted(run_id=doc["runId"], status=doc["status"])


@router.get("/runs/{run_id}", response_model=RunView)
def get_run(run_id: str, principal: CurrentPrincipal, repo: Repo) -> RunView:
    doc = repo.get_run(run_id)
    if not visible_to(doc, principal):
        raise _not_found("run")
    return run_view(doc)


@router.get("/runs/{run_id}/events", response_model=list[RunEvent])
def get_run_events(run_id: str, principal: CurrentPrincipal, repo: Repo, after: int = 0) -> list[RunEvent]:
    """Events with seq > `after`, in order. The UI polls this every second or two."""
    if not visible_to(repo.get_run(run_id), principal):
        raise _not_found("run")
    return [RunEvent.model_validate(e) for e in repo.events_after(run_id, after)]
