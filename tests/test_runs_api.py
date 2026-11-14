"""Incident and run endpoints (api/routes.py + api/runs.py) with a fake investigation.

The fake replays contracts/sample_run_events.json under the new run id, so these tests check the API
plumbing (persistence, ordering, `after`, scope, failure paths), not the agent.
"""

from __future__ import annotations

import json
import sys
import types
from concurrent.futures import Executor, Future
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import runs as runs_module
from api.main import app
from api.runs import MemoryRunStore, RunJob, RunService, agent_loop, get_service
from contracts import models
from contracts.models import RunEvent
from core.config import get_settings

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = json.loads((ROOT / "contracts" / "sample_run_events.json").read_text(encoding="utf-8"))

PRINCIPALS = {
    "test-payments-eng": {"tenantId": "demo-org", "teamId": "team-payments", "role": "engineer",
                          "authorizedRepos": ["payments-webhooks"]},
    "test-platform-eng": {"tenantId": "demo-org", "teamId": "team-platform", "role": "engineer",
                          "authorizedRepos": ["platform-webhooks"]},
}
PAYMENTS = {"X-API-Key": "test-payments-eng"}
PLATFORM = {"X-API-Key": "test-platform-eng"}

PAYLOADS = {
    "run_started": models.RunStartedPayload,
    "observation": models.ObservationPayload,
    "recall": models.RecallPayload,
    "precondition_check": models.PreconditionPayload,
    "tool_call": models.ToolCallPayload,
    "tool_result": models.ToolResultPayload,
    "patch_proposed": models.PatchPayload,
    "verification": models.VerificationPayload,
    "memory_outcome": models.MemoryOutcomePayload,
    "run_finished": models.RunFinishedPayload,
    "error": models.ErrorPayload,
}


class InlineExecutor(Executor):
    """Runs the job during submit(), so a test sees the finished run right after POST."""

    def submit(self, fn, /, *args, **kwargs):
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as e:  # noqa: BLE001
            future.set_exception(e)
        return future


class HeldExecutor(Executor):
    """Keeps submitted jobs until the test runs them."""

    def __init__(self):
        self.jobs = []

    def submit(self, fn, /, *args, **kwargs):
        self.jobs.append((fn, args, kwargs))
        return Future()

    def run_all(self):
        for fn, args, kwargs in self.jobs:
            fn(*args, **kwargs)
        self.jobs.clear()


def replay_sample(job: RunJob, on_event) -> None:
    """Fake investigation: the sample run, with this run's incident id."""
    for e in SAMPLE:
        payload = dict(e["payload"])
        if e["type"] == "run_started":
            payload.update(incidentId=job.incident_id, caseId=job.case.case_id, teamId=job.principal.team_id,
                           memoryMode=job.memory_mode)
        on_event({"type": e["type"], "payload": payload})


@pytest.fixture(autouse=True)
def _principals(monkeypatch, _test_settings):
    monkeypatch.setenv("DEMO_PRINCIPALS", json.dumps(PRINCIPALS))
    get_settings.cache_clear()


def make_client(service: RunService) -> TestClient:
    app.dependency_overrides[get_service] = lambda: service
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def store() -> MemoryRunStore:
    return MemoryRunStore()


@pytest.fixture
def client(store) -> TestClient:
    return make_client(RunService(store, replay_sample, InlineExecutor()))


def new_incident(client: TestClient, case_id: str = "B", headers=PAYMENTS, repo: str = "payments-webhooks") -> str:
    r = client.post("/incidents", headers=headers, json={"repositoryId": repo, "caseId": case_id, "logs": "",
                                                         "request": {}})
    assert r.status_code == 201, r.text
    return r.json()["incidentId"]


def start(client: TestClient, incident_id: str, headers=PAYMENTS, memory: str | None = None) -> str:
    params = {"memory": memory} if memory else None
    r = client.post(f"/incidents/{incident_id}/runs", headers=headers, params=params)
    assert r.status_code == 202, r.text
    assert r.json()["status"] == "queued"
    return r.json()["runId"]


# --------------------------------------------------------------------------- happy path


def test_create_run_and_follow_events(client, store):
    incident_id = new_incident(client)
    incident = store.get_incident(incident_id)
    manifest = json.loads((ROOT / "cases" / "B" / "manifest.json").read_text(encoding="utf-8"))
    assert incident["logs"] == manifest["logs"] and incident["request"] == manifest["request"]

    run_id = start(client, incident_id, memory="off")
    events = client.get(f"/runs/{run_id}/events", headers=PAYMENTS).json()
    assert [e["seq"] for e in events] == list(range(1, len(SAMPLE) + 1))
    assert [e["type"] for e in events] == [e["type"] for e in SAMPLE]
    assert {e["runId"] for e in events} == {run_id}
    for e in events:
        PAYLOADS[e["type"]].model_validate(e["payload"])
    assert events[0]["payload"]["incidentId"] == incident_id
    assert events[0]["payload"]["memoryMode"] == "off"

    later = client.get(f"/runs/{run_id}/events", headers=PAYMENTS, params={"after": 4}).json()
    assert [e["seq"] for e in later] == list(range(5, len(SAMPLE) + 1))
    assert client.get(f"/runs/{run_id}/events", headers=PAYMENTS, params={"after": len(SAMPLE)}).json() == []

    view = client.get(f"/runs/{run_id}", headers=PAYMENTS).json()
    assert view["status"] == "finished" and view["outcome"] == "verified"
    assert view["attempt"] == 1 and view["seenBefore"] is True and view["testsPassed"] == 7
    assert view["incidentId"] == incident_id and view["caseId"] == "B" and view["memoryMode"] == "off"


def test_run_document_is_saved_before_work_starts(store):
    held = HeldExecutor()
    seen = {}

    def investigate(job, on_event):
        seen["status_at_start"] = store.get_run(job.run_id)["status"]
        replay_sample(job, on_event)

    client = make_client(RunService(store, investigate, held))
    run_id = start(client, new_incident(client))

    assert held.jobs, "the run is handed to the background"
    assert not seen, "no work before the run document exists"
    view = client.get(f"/runs/{run_id}", headers=PAYMENTS).json()
    assert view["status"] == "queued" and view["budget"]["maxPatchAttempts"] >= 1
    assert client.get(f"/runs/{run_id}/events", headers=PAYMENTS).json() == []

    held.run_all()
    assert seen["status_at_start"] == "running"
    assert client.get(f"/runs/{run_id}", headers=PAYMENTS).json()["status"] == "finished"


def test_foreign_events_are_restamped_with_our_run_id_and_seq(store):
    def investigate(job, on_event):  # like P1's EventSink: RunEvent objects with its own ids
        for i, e in enumerate(SAMPLE):
            on_event(RunEvent.model_validate({**e, "runId": "run_other", "seq": 100 + 2 * i}))

    client = make_client(RunService(store, investigate, InlineExecutor()))
    run_id = start(client, new_incident(client))
    events = client.get(f"/runs/{run_id}/events", headers=PAYMENTS).json()
    assert [e["seq"] for e in events] == list(range(1, len(SAMPLE) + 1))
    assert {e["runId"] for e in events} == {run_id}


# --------------------------------------------------------------------------- scope


def test_another_teams_repository_is_refused(client):
    r = client.post("/incidents", headers=PLATFORM, json={"repositoryId": "payments-webhooks", "caseId": "B",
                                                          "logs": "", "request": {}})
    assert r.status_code == 403


def test_another_teams_incident_and_run_are_refused(client):
    incident_id = new_incident(client)
    run_id = start(client, incident_id)
    assert client.post(f"/incidents/{incident_id}/runs", headers=PLATFORM).status_code == 403
    assert client.get(f"/runs/{run_id}", headers=PLATFORM).status_code == 403
    assert client.get(f"/runs/{run_id}/events", headers=PLATFORM).status_code == 403
    assert client.get(f"/runs/{run_id}", headers={"X-API-Key": "nope"}).status_code == 401


def test_platform_runs_its_own_case(client):
    run_id = start(client, new_incident(client, "D", PLATFORM, "platform-webhooks"), PLATFORM)
    assert client.get(f"/runs/{run_id}", headers=PLATFORM).json()["teamId"] == "team-platform"
    assert client.get(f"/runs/{run_id}", headers=PAYMENTS).status_code == 403


# --------------------------------------------------------------------------- not found / invalid


def test_not_found(client):
    assert client.get("/runs/run_missing", headers=PAYMENTS).status_code == 404
    assert client.get("/runs/run_missing/events", headers=PAYMENTS).status_code == 404
    assert client.post("/incidents/inc_missing/runs", headers=PAYMENTS).status_code == 404
    r = client.post("/incidents", headers=PAYMENTS, json={"repositoryId": "payments-webhooks", "caseId": "ZZ",
                                                          "logs": "", "request": {}})
    assert r.status_code == 404


def test_invalid_requests(client):
    def post(body):
        return client.post("/incidents", headers=PAYMENTS, json={"repositoryId": "payments-webhooks", "logs": "",
                                                                 "request": {}, **body})

    assert post({"caseId": "../A"}).status_code == 422  # never a path outside cases/
    assert client.post("/incidents", headers=PLATFORM, json={"repositoryId": "platform-webhooks", "caseId": "B",
                                                             "logs": "", "request": {}}).status_code == 422
    no_case = post({"logs": "E11000 duplicate key error"})
    assert no_case.status_code == 201
    assert client.post(f"/incidents/{no_case.json()['incidentId']}/runs", headers=PAYMENTS).status_code == 422
    incident_id = new_incident(client)
    assert client.post(f"/incidents/{incident_id}/runs", headers=PAYMENTS,
                       params={"memory": "maybe"}).status_code == 422


# --------------------------------------------------------------------------- failure paths


def _error_run(client) -> tuple[list[dict], dict]:
    run_id = start(client, new_incident(client))
    return (client.get(f"/runs/{run_id}/events", headers=PAYMENTS).json(),
            client.get(f"/runs/{run_id}", headers=PAYMENTS).json())


def test_missing_agent_loop_fails_cleanly(store, monkeypatch):
    monkeypatch.setitem(sys.modules, "agent.events", None)  # import agent.events -> ImportError
    events, view = _error_run(make_client(RunService(store, agent_loop, InlineExecutor())))
    assert [e["type"] for e in events] == ["error"] and events[0]["seq"] == 1
    assert "agent loop isn't available" in events[0]["payload"]["message"]
    assert view["status"] == "error" and view["outcome"] is None


def test_stub_agent_loop_fails_cleanly(store, monkeypatch):
    class EventSink:
        def __init__(self, on_event):
            self.on_event = on_event

    def stub(principal, case, memory, runner, budget=None, memory_mode="real"):
        raise NotImplementedError("P1-2: agent loop")

    monkeypatch.setitem(sys.modules, "agent.events", types.SimpleNamespace(EventSink=EventSink))
    monkeypatch.setattr("agent.loop.run_investigation", stub)
    monkeypatch.setattr("memory.store.AtlasMemoryStore", lambda: object())
    monkeypatch.setattr("runner.sandbox.LocalRunner", lambda: object())
    events, view = _error_run(make_client(RunService(store, agent_loop, InlineExecutor())))
    assert [e["type"] for e in events] == ["error"]
    assert view["status"] == "error"


def test_agent_loop_passes_the_sink_and_ids(store, monkeypatch):
    class EventSink:
        def __init__(self, on_event):
            self.on_event = on_event

    def loop(principal, case, memory, runner, budget=None, memory_mode="real", *, events, run_id, incident_id):
        for e in SAMPLE:
            events.on_event({"type": e["type"], "payload": e["payload"]})

    monkeypatch.setitem(sys.modules, "agent.events", types.SimpleNamespace(EventSink=EventSink))
    monkeypatch.setattr("agent.loop.run_investigation", loop)
    monkeypatch.setattr("memory.store.AtlasMemoryStore", lambda: object())
    monkeypatch.setattr("runner.sandbox.LocalRunner", lambda: object())
    events, view = _error_run(make_client(RunService(store, agent_loop, InlineExecutor())))
    assert events[-1]["type"] == "run_finished" and view["status"] == "finished"


def test_crash_mid_run_ends_with_an_error_event(store):
    def investigate(job, on_event):
        for e in SAMPLE[:3]:
            on_event({"type": e["type"], "payload": e["payload"]})
        raise RuntimeError("boom")

    events, view = _error_run(make_client(RunService(store, investigate, InlineExecutor())))
    assert [e["seq"] for e in events] == [1, 2, 3, 4]
    assert events[-1]["type"] == "error" and "boom" not in events[-1]["payload"]["message"]
    assert view["status"] == "error"


def test_run_without_a_final_event_is_an_error(store):
    def investigate(job, on_event):
        on_event({"type": "run_started", "payload": SAMPLE[0]["payload"]})

    events, view = _error_run(make_client(RunService(store, investigate, InlineExecutor())))
    assert [e["type"] for e in events] == ["run_started", "error"]
    assert view["status"] == "error"


def test_default_service_falls_back_to_memory_without_atlas(monkeypatch):
    monkeypatch.setenv("MONGODB_URI", "")
    get_settings.cache_clear()
    runs_module.get_service.cache_clear()
    try:
        assert isinstance(runs_module.get_service().store, MemoryRunStore)
    finally:
        runs_module.get_service.cache_clear()
