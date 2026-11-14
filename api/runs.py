"""Incidents, runs and run events behind the API (P1-4 glue). No agent logic lives here.

    RunService.create_incident  -> incident document (scope-checked; caseId loads cases/<id>/manifest.json)
    RunService.start_run        -> run document saved as "queued" BEFORE any work, then run in the background
    RunService.get_run / events -> scope-checked reads; events come back ordered by seq

The work itself is an `Investigate` callable: `investigate(job, on_event) -> RunView | None`. It reports
each step through `on_event`; the service owns `runId` and `seq` (1, 2, 3, ... with no gaps) and saves
every event as it arrives, so the UI can follow a live run. The default, `agent_loop`, binds to P1's
`agent.loop.run_investigation` and `agent.events.EventSink` when they land; until then a run ends with
an `error` event and status "error", never a fake success.

Storage: Atlas through core.db (incidents / runs / run_events) when MONGODB_URI is set, otherwise an
in-process store so tests and offline dev work.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import threading
from collections.abc import Callable
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol, get_args

from pydantic import BaseModel

from contracts.models import (
    BudgetUsage,
    CaseManifest,
    ErrorPayload,
    IncidentCreate,
    MemoryMode,
    Principal,
    RunEvent,
    RunEventType,
    RunView,
)
from core.clock import new_id, utc_now
from core.config import get_settings
from core.db import Collections, get_db

log = logging.getLogger("traceback.runs")

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "cases"
_CASE_ID = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
FINAL_EVENTS = {"run_finished", "error"}
_EVENT_TYPES = set(get_args(RunEventType))


# =========================================================================== errors (mapped to HTTP in routes)


class RunError(Exception):
    status_code = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(RunError):
    status_code = 404


class Forbidden(RunError):
    status_code = 403


class Invalid(RunError):
    status_code = 422


class LoopUnavailable(RuntimeError):
    """The agent loop isn't on this build yet (missing module or still a NotImplementedError stub)."""


# =========================================================================== the work


@dataclass(frozen=True)
class RunJob:
    """Everything one investigation needs. `principal` comes from the API key, never from a body."""

    run_id: str
    incident_id: str
    principal: Principal
    case: CaseManifest
    memory_mode: MemoryMode


# What the investigation reports: a RunEvent (P1's EventSink), its dict form, or a (type, payload) pair.
EventLike = RunEvent | dict[str, Any] | tuple[str, BaseModel | dict[str, Any]]
OnEvent = Callable[[EventLike], None]
Investigate = Callable[[RunJob, OnEvent], RunView | None]


@lru_cache(maxsize=1)
def _revision() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def agent_loop(job: RunJob, on_event: OnEvent) -> RunView | None:
    """Default Investigate: P1's loop, imported lazily so this module works before it lands.

    Signature confirmed by P1 (#31):
        run_investigation(principal, case, memory, runner, llm, *, memory_mode="real", budget=None,
                          sink=None, promote=True, incident_id=None, revision="unknown") -> RunView
    with `sink=EventSink(run_id, on_event=...)`. The run is persisted before this is called.
    """
    try:  # agent.events lands with P1's agent loop
        from agent.events import EventSink

        from agent.llm import get_llm
        from agent.loop import run_investigation
    except ImportError as e:
        raise LoopUnavailable(f"agent loop not installed ({e.name})") from e

    from memory.store import AtlasMemoryStore
    from runner.sandbox import LocalRunner

    try:
        return run_investigation(
            job.principal, job.case, AtlasMemoryStore(), LocalRunner(), get_llm(),
            memory_mode=job.memory_mode,
            sink=EventSink(job.run_id, on_event=on_event),
            promote=job.memory_mode == "real",  # off / placebo runs never write memory (experiment)
            incident_id=job.incident_id,
            revision=_revision(),
        )
    except NotImplementedError as e:
        raise LoopUnavailable(str(e) or "agent.loop.run_investigation is not implemented") from e


# =========================================================================== storage


class RunStore(Protocol):
    def save_incident(self, doc: dict) -> None: ...
    def get_incident(self, incident_id: str) -> dict | None: ...
    def save_run(self, doc: dict) -> None: ...
    def update_run(self, run_id: str, fields: dict) -> None: ...
    def get_run(self, run_id: str) -> dict | None: ...
    def add_event(self, event: RunEvent) -> None: ...
    def events_after(self, run_id: str, after: int) -> list[RunEvent]: ...


class MemoryRunStore:
    """In-process store: tests and offline dev. Same behaviour as the Atlas one."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.incidents: dict[str, dict] = {}
        self.runs: dict[str, dict] = {}
        self.events: dict[str, list[RunEvent]] = {}

    def save_incident(self, doc: dict) -> None:
        with self._lock:
            self.incidents[doc["_id"]] = dict(doc)

    def get_incident(self, incident_id: str) -> dict | None:
        with self._lock:
            doc = self.incidents.get(incident_id)
            return dict(doc) if doc else None

    def save_run(self, doc: dict) -> None:
        with self._lock:
            self.runs[doc["_id"]] = dict(doc)

    def update_run(self, run_id: str, fields: dict) -> None:
        with self._lock:
            self.runs[run_id].update(fields)

    def get_run(self, run_id: str) -> dict | None:
        with self._lock:
            doc = self.runs.get(run_id)
            return dict(doc) if doc else None

    def add_event(self, event: RunEvent) -> None:
        with self._lock:
            self.events.setdefault(event.run_id, []).append(event)

    def events_after(self, run_id: str, after: int) -> list[RunEvent]:
        with self._lock:
            return sorted((e for e in self.events.get(run_id, []) if e.seq > after), key=lambda e: e.seq)


class MongoRunStore:
    """Atlas: incidents, runs and run_events (core.db.Collections). Event _id is "<runId>:<seq>", so a
    sequence number can never be written twice. Indexes (e.g. run_events.run_seq) are created by
    scripts/atlas_setup.py from memory/schema.py, not here."""

    def __init__(self, db=None) -> None:
        self.db = db if db is not None else get_db()
        self.incidents = self.db[Collections.INCIDENTS]
        self.runs = self.db[Collections.RUNS]
        self.run_events = self.db[Collections.RUN_EVENTS]

    def save_incident(self, doc: dict) -> None:
        self.incidents.insert_one(doc)

    def get_incident(self, incident_id: str) -> dict | None:
        return self.incidents.find_one({"_id": incident_id})

    def save_run(self, doc: dict) -> None:
        self.runs.insert_one(doc)

    def update_run(self, run_id: str, fields: dict) -> None:
        self.runs.update_one({"_id": run_id}, {"$set": fields})

    def get_run(self, run_id: str) -> dict | None:
        return self.runs.find_one({"_id": run_id})

    def add_event(self, event: RunEvent) -> None:
        doc = event.model_dump(by_alias=True)
        self.run_events.insert_one({"_id": f"{event.run_id}:{event.seq}", **doc})

    def events_after(self, run_id: str, after: int) -> list[RunEvent]:
        cursor = self.run_events.find({"runId": run_id, "seq": {"$gt": after}}, {"_id": 0}).sort("seq", 1)
        return [RunEvent.model_validate(d) for d in cursor]


# =========================================================================== the service


def load_case(case_id: str) -> CaseManifest:
    if not _CASE_ID.match(case_id):
        raise Invalid(f"Invalid caseId: {case_id!r}.")
    path = CASES / case_id / "manifest.json"
    if not path.is_file():
        raise NotFound(f"No case {case_id}.")
    return CaseManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _check_scope(principal: Principal, doc: dict, what: str) -> None:
    """Same tenant, same team, and a repository the principal is authorized for."""
    if (
        doc.get("tenantId") != principal.tenant_id
        or doc.get("teamId") != principal.team_id
        or doc.get("repositoryId") not in principal.authorized_repos
    ):
        raise Forbidden(f"This {what} belongs to another team.")


class RunService:
    def __init__(self, store: RunStore, investigate: Investigate = agent_loop, executor: Executor | None = None):
        self.store = store
        self.investigate = investigate
        self.executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="traceback-run")

    # ------------------------------------------------------------------ incidents

    def create_incident(self, principal: Principal, body: IncidentCreate) -> str:
        if body.repository_id not in principal.authorized_repos:
            raise Forbidden(f"You are not authorized for repository {body.repository_id}.")
        logs, request = body.logs, body.request
        if body.case_id is not None:
            case = load_case(body.case_id)
            if case.repository_id != body.repository_id:
                raise Invalid(f"Case {case.case_id} is for repository {case.repository_id}, "
                              f"not {body.repository_id}.")
            logs, request = case.logs, case.request
        incident_id = new_id("inc")
        self.store.save_incident({
            "_id": incident_id,
            "tenantId": principal.tenant_id,
            "teamId": principal.team_id,
            "repositoryId": body.repository_id,
            "caseId": body.case_id,
            "logs": logs,
            "request": request,
            "revision": body.revision,
            "createdBy": f"{principal.role}@{principal.team_id}",
            "createdAt": utc_now(),
        })
        return incident_id

    # ------------------------------------------------------------------ runs

    def start_run(self, principal: Principal, incident_id: str, memory_mode: MemoryMode) -> str:
        incident = self.store.get_incident(incident_id)
        if incident is None:
            raise NotFound(f"No incident {incident_id}.")
        _check_scope(principal, incident, "incident")
        if not incident.get("caseId"):
            raise Invalid("This incident has no caseId: a run needs a case so the runner can verify the fix.")
        case = load_case(incident["caseId"]).model_copy(
            update={"logs": incident["logs"], "request": incident["request"]})

        run_id = new_id("run")
        s = get_settings()
        view = RunView(
            run_id=run_id, incident_id=incident_id, case_id=case.case_id, team_id=principal.team_id,
            status="queued", memory_mode=memory_mode, model=s.llm_model or None,
            budget=BudgetUsage(max_tool_calls=s.agent_max_tool_calls, max_patch_attempts=s.agent_max_patch_attempts,
                               deadline_seconds=s.agent_deadline_seconds),
        )
        now = utc_now()
        # Saved BEFORE any work starts (plan P1-4): a crash still leaves a run to look at.
        self.store.save_run({
            "_id": run_id,
            **view.model_dump(by_alias=True, mode="json"),
            "tenantId": principal.tenant_id,
            "repositoryId": incident["repositoryId"],
            "principal": principal.model_dump(by_alias=True),
            "createdAt": now,
            "updatedAt": now,
        })
        job = RunJob(run_id, incident_id, principal, case, memory_mode)
        self.executor.submit(self._execute, job)
        return run_id

    def get_run(self, principal: Principal, run_id: str) -> RunView:
        return RunView.model_validate(self._readable_run(principal, run_id))

    def events(self, principal: Principal, run_id: str, after: int = 0) -> list[RunEvent]:
        self._readable_run(principal, run_id)
        return self.store.events_after(run_id, max(after, 0))

    def _readable_run(self, principal: Principal, run_id: str) -> dict:
        doc = self.store.get_run(run_id)
        if doc is None:
            raise NotFound(f"No run {run_id}.")
        _check_scope(principal, doc, "run")
        return doc

    # ------------------------------------------------------------------ background work

    def _execute(self, job: RunJob) -> None:
        recorder = _Recorder(self.store, job.run_id)
        self.store.update_run(job.run_id, {"status": "running", "updatedAt": utc_now()})
        try:
            view = self.investigate(job, recorder.on_event)
        except LoopUnavailable as e:
            log.warning("run %s: agent loop unavailable: %s", job.run_id, e)
            self._fail(recorder, "The agent loop isn't available on this build yet, so this run did not start. "
                                 "Nothing was changed.")
            return
        except Exception:  # noqa: BLE001 - a run must always end with a final event
            log.exception("run %s failed", job.run_id)
            self._fail(recorder, "The run stopped because of an internal error. Nothing was promoted.")
            return

        if recorder.last_type not in FINAL_EVENTS:
            self._fail(recorder, "The run ended without a result.")
            return
        if recorder.last_type == "error":
            self.store.update_run(job.run_id, {"status": "error", "updatedAt": utc_now()})
            return
        self.store.update_run(job.run_id, {**_result_fields(view, recorder.finished), "status": "finished",
                                           "updatedAt": utc_now()})

    def _fail(self, recorder: _Recorder, message: str) -> None:
        recorder.on_event(("error", ErrorPayload(message=message)))
        self.store.update_run(recorder.run_id, {"status": "error", "updatedAt": utc_now()})


_RESULT_KEYS = ("outcome", "attempt", "seenBefore", "testsPassed", "testsTotal", "memoryUsed",
                "budget", "memoryInfluence", "model", "promptVersion")


def _result_fields(view: RunView | None, finished: dict | None) -> dict:
    """Run-document fields from the loop's RunView, else from the run_finished payload."""
    if isinstance(view, RunView):
        dumped = view.model_dump(by_alias=True, mode="json")
        return {k: dumped[k] for k in _RESULT_KEYS if dumped.get(k) is not None}
    f = finished or {}
    return {k: f[k] for k in ("outcome", "attempt", "seenBefore", "testsPassed", "testsTotal", "memoryUsed") if k in f}


class _Recorder:
    """Turns whatever the investigation reports into stored RunEvents with our runId and the next seq."""

    def __init__(self, store: RunStore, run_id: str):
        self.store = store
        self.run_id = run_id
        self.seq = 0
        self.last_type: str | None = None
        self.finished: dict | None = None
        self._lock = threading.Lock()

    def on_event(self, event: EventLike) -> None:
        etype, payload, at = _unpack(event)
        with self._lock:
            if self.last_type in FINAL_EVENTS:
                log.warning("run %s: ignoring %s after the final event", self.run_id, etype)
                return
            self.seq += 1
            stored = RunEvent(run_id=self.run_id, seq=self.seq, type=etype, payload=payload, at=at or utc_now())
            self.store.add_event(stored)
            self.last_type = etype
            if etype == "run_finished":
                self.finished = payload


def _unpack(event: EventLike) -> tuple[RunEventType, dict, Any]:
    if isinstance(event, tuple):
        etype, payload = event
        at = None
    else:
        if isinstance(event, BaseModel):
            event = event.model_dump(by_alias=True)
        etype, payload, at = event["type"], event.get("payload") or {}, event.get("at")
    if isinstance(payload, BaseModel):
        payload = payload.model_dump(by_alias=True, mode="json")
    if etype not in _EVENT_TYPES:
        raise ValueError(f"not a run event type: {etype!r}")
    return etype, payload, at


# =========================================================================== wiring


@lru_cache(maxsize=1)
def get_service() -> RunService:
    """The app's RunService: Atlas when MONGODB_URI is set, otherwise in-process."""
    if get_settings().mongodb_uri.get_secret_value():
        return RunService(MongoRunStore())
    log.warning("MONGODB_URI is not set: runs are kept in memory only")
    return RunService(MemoryRunStore())
