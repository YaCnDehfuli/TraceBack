"""Incidents, runs and run events: storage and background execution (P1-4).

Rules:
- The run document is saved BEFORE any LLM or tool call starts.
- Every event is written to run_events as it happens (the UI polls GET /runs/{id}/events?after=).
- Every run ends with a run_finished event, even if the agent crashes, so the UI always stops cleanly.
- Runs and events are scoped: a team only ever sees its own.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from agent.budgets import Budget
from agent.events import EventSink
from agent.loop import run_investigation
from contracts.interfaces import MemoryStore, Runner
from contracts.models import (
    CaseManifest,
    ErrorPayload,
    MemoryMode,
    Principal,
    RunEvent,
    RunFinishedPayload,
    RunView,
)
from core.clock import new_id, utc_now

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "cases"


def load_case(case_id: str) -> CaseManifest | None:
    path = CASES / case_id / "manifest.json"
    if not case_id.replace("_", "").isalnum() or not path.exists():
        return None
    return CaseManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def case_title(case_id: str) -> str | None:
    path = CASES / case_id / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8")).get("title") if path.exists() else None


# =========================================================================== storage


class RunRepo(Protocol):
    def insert_incident(self, doc: dict[str, Any]) -> None: ...
    def get_incident(self, tenant_id: str, incident_id: str) -> dict[str, Any] | None: ...
    def insert_run(self, doc: dict[str, Any]) -> None: ...
    def find_run_by_key(self, tenant_id: str, key: str) -> dict[str, Any] | None: ...
    def update_run(self, run_id: str, fields: dict[str, Any]) -> None: ...
    def get_run(self, run_id: str) -> dict[str, Any] | None: ...
    def append_event(self, event: RunEvent) -> None: ...
    def events_after(self, run_id: str, after: int) -> list[dict[str, Any]]: ...


class MongoRunRepo:
    def __init__(self, db=None):
        from core.db import Collections, get_db

        db = db if db is not None else get_db()
        self.incidents = db[Collections.INCIDENTS]
        self.runs = db[Collections.RUNS]
        self.events = db[Collections.RUN_EVENTS]

    def insert_incident(self, doc):
        self.incidents.insert_one(doc)

    def get_incident(self, tenant_id, incident_id):
        return self.incidents.find_one({"_id": incident_id, "tenantId": tenant_id})

    def insert_run(self, doc):
        self.runs.insert_one(doc)

    def find_run_by_key(self, tenant_id, key):
        return self.runs.find_one({"tenantId": tenant_id, "idempotencyKey": key})

    def update_run(self, run_id, fields):
        self.runs.update_one({"_id": run_id}, {"$set": fields})

    def get_run(self, run_id):
        return self.runs.find_one({"_id": run_id})

    def append_event(self, event):
        self.events.insert_one(event.model_dump(by_alias=True))

    def events_after(self, run_id, after):
        return list(self.events.find({"runId": run_id, "seq": {"$gt": after}}, {"_id": 0}).sort("seq", 1))


class MemoryRunRepo:
    """In-memory RunRepo for tests and for running the API without Atlas."""

    def __init__(self):
        self.incidents: dict[str, dict] = {}
        self.runs: dict[str, dict] = {}
        self.events: dict[str, list[dict]] = {}
        self.lock = threading.Lock()

    def insert_incident(self, doc):
        self.incidents[doc["_id"]] = doc

    def get_incident(self, tenant_id, incident_id):
        doc = self.incidents.get(incident_id)
        return doc if doc and doc["tenantId"] == tenant_id else None

    def insert_run(self, doc):
        self.runs[doc["_id"]] = doc

    def find_run_by_key(self, tenant_id, key):
        return next(
            (r for r in self.runs.values() if r["tenantId"] == tenant_id and r.get("idempotencyKey") == key), None
        )

    def update_run(self, run_id, fields):
        with self.lock:
            self.runs[run_id].update(fields)

    def get_run(self, run_id):
        return self.runs.get(run_id)

    def append_event(self, event):
        with self.lock:
            self.events.setdefault(event.run_id, []).append(event.model_dump(by_alias=True))

    def events_after(self, run_id, after):
        return [e for e in self.events.get(run_id, []) if e["seq"] > after]


# =========================================================================== execution


@dataclass
class AgentDeps:
    runner: Runner
    memory: MemoryStore
    llm: Any
    revision: str = "unknown"
    synchronous: bool = False  # tests run the agent inline instead of in a thread
    promote: bool = True  # AGENT_PROMOTE=false on experiment servers
    runner_name: str | None = None  # what actually runs, recorded on every run (fakes are never silent)
    store_name: str | None = None


def visible_to(doc: dict[str, Any] | None, principal: Principal) -> bool:
    return bool(doc) and doc["tenantId"] == principal.tenant_id and doc["teamId"] == principal.team_id


def start_run(
    repo: RunRepo,
    deps: AgentDeps,
    principal: Principal,
    incident: dict[str, Any],
    case: CaseManifest,
    memory_mode: MemoryMode,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    if idempotency_key:
        existing = repo.find_run_by_key(principal.tenant_id, idempotency_key)
        if existing:
            return existing

    run_id = new_id("run")
    limits = Budget.from_settings()  # AGENT_MAX_TOOL_CALLS / AGENT_MAX_PATCH_ATTEMPTS / AGENT_DEADLINE_SECONDS
    doc = {
        "_id": run_id,
        "runId": run_id,
        "incidentId": incident["_id"],
        "caseId": case.case_id,
        "tenantId": principal.tenant_id,
        "teamId": principal.team_id,
        "status": "queued",
        "memoryMode": memory_mode,
        "budget": limits.usage().model_dump(by_alias=True),
        "agent": {
            "runner": deps.runner_name or type(deps.runner).__name__,
            "store": deps.store_name or type(deps.memory).__name__,
            "model": getattr(deps.llm, "model", None),
            "revision": deps.revision,
            "promote": deps.promote,
        },
        "createdAt": utc_now(),
    }
    if idempotency_key:
        doc["idempotencyKey"] = idempotency_key
    repo.insert_run(doc)  # saved BEFORE any work starts

    def execute() -> None:
        def on_event(event: RunEvent) -> None:
            repo.append_event(event)
            if event.seq == 1:
                repo.update_run(run_id, {"status": "running", "startedAt": utc_now()})

        sink = EventSink(run_id, on_event=on_event)
        try:
            view = run_investigation(
                principal,
                case,
                deps.memory,
                deps.runner,
                deps.llm,
                memory_mode=memory_mode,
                # the clock starts when the run starts, not while it waited in the queue
                budget=Budget(limits.max_tool_calls, limits.max_patch_attempts, limits.deadline_seconds),
                sink=sink,
                promote=deps.promote,
                incident_id=incident["_id"],
                revision=deps.revision,
            )
            fields = view.model_dump(by_alias=True, mode="json")
            fields.update(status="finished", finishedAt=utc_now())
            repo.update_run(run_id, fields)
        except Exception as e:  # noqa: BLE001 - the run must still end with run_finished
            sink.emit("error", ErrorPayload(message=f"The run stopped: {type(e).__name__}: {str(e)[:200]}"))
            sink.emit(
                "run_finished",
                RunFinishedPayload(
                    outcome="unresolved", seen_before=False, summary="The run stopped because of an internal error."
                ),
            )
            repo.update_run(run_id, {"status": "error", "outcome": "unresolved", "finishedAt": utc_now()})

    if deps.synchronous:
        execute()
    else:
        threading.Thread(target=execute, name=f"run-{run_id}", daemon=True).start()
    return doc


def run_view(doc: dict[str, Any]) -> RunView:
    data = {k: v for k, v in doc.items() if k != "_id"}
    data.setdefault("budget", Budget.from_settings().usage().model_dump(by_alias=True))
    return RunView.model_validate(data)
