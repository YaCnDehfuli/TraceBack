"""Live runs through the API: incident -> run -> events, scoped to the caller's team.
In-memory storage, FakeRunner, FakeMemoryStore and a scripted LLM; the agent runs inline."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent.llm import ScriptedLLM
from api.deps import get_agent_deps, get_repo
from api.main import app
from api.runs import AgentDeps, MemoryRunRepo
from contracts.fakes import FakeMemoryStore, FakeRunner

ROOT = Path(__file__).resolve().parents[1]
PAY = {"X-API-Key": "test-payments-eng"}
PLAT = {"X-API-Key": "test-platform-eng"}


def fix_b() -> dict:
    content = (ROOT / "cases" / "B" / "reference" / "webhooks.py").read_text()
    return {"path": "app/webhooks.py", "new_content": content, "cause": "replay", "summary": "idempotent"}


@pytest.fixture
def api():
    repo = MemoryRunRepo()
    llm = ScriptedLLM([[("read_file", {"path": "app/webhooks.py"})], [("propose_fix", fix_b())]])
    deps = AgentDeps(runner=FakeRunner(), memory=FakeMemoryStore(), llm=llm, synchronous=True)
    app.dependency_overrides[get_repo] = lambda: repo
    app.dependency_overrides[get_agent_deps] = lambda: deps
    yield TestClient(app), repo
    app.dependency_overrides.clear()


def start(client, case_id="B", repo_id="payments-webhooks", headers=PAY, **params):
    inc = client.post("/incidents", json={"repositoryId": repo_id, "caseId": case_id, "logs": ""}, headers=headers)
    assert inc.status_code == 201, inc.text
    run = client.post(f"/incidents/{inc.json()['incidentId']}/runs", headers=headers, params=params)
    assert run.status_code == 202, run.text
    return inc.json()["incidentId"], run.json()["runId"]


def test_live_run_end_to_end(api):
    client, repo = api
    _, run_id = start(client)
    events = client.get(f"/runs/{run_id}/events", params={"after": 0}, headers=PAY).json()
    assert [e["seq"] for e in events] == list(range(1, len(events) + 1))
    assert events[0]["type"] == "run_started" and events[-1]["type"] == "run_finished"
    assert client.get(f"/runs/{run_id}/events", params={"after": len(events)}, headers=PAY).json() == []
    view = client.get(f"/runs/{run_id}", headers=PAY).json()
    assert view["status"] == "finished" and view["outcome"] == "verified" and view["seenBefore"] is True
    assert view["memoryUsed"]["ownerTeamId"] == "team-payments" and view["testsPassed"] == view["testsTotal"]


def test_runs_are_invisible_to_other_teams(api):
    client, _ = api
    inc_id, run_id = start(client)
    assert client.get(f"/runs/{run_id}", headers=PLAT).status_code == 404
    assert client.get(f"/runs/{run_id}/events", headers=PLAT).status_code == 404
    assert client.post(f"/incidents/{inc_id}/runs", headers=PLAT).status_code == 404


def test_a_team_cannot_open_an_incident_on_another_teams_app(api):
    client, _ = api
    r = client.post("/incidents", json={"repositoryId": "payments-webhooks", "caseId": "B", "logs": ""}, headers=PLAT)
    assert r.status_code == 403
    r = client.post("/incidents", json={"repositoryId": "payments-webhooks", "caseId": "nope", "logs": ""}, headers=PAY)
    assert r.status_code == 422


def test_memory_switch_and_idempotency(api):
    client, repo = api
    inc = client.post(
        "/incidents", json={"repositoryId": "payments-webhooks", "caseId": "B", "logs": ""}, headers=PAY
    ).json()
    url = f"/incidents/{inc['incidentId']}/runs"
    first = client.post(url, headers={**PAY, "Idempotency-Key": "k1"}, params={"memory": "off"}).json()
    again = client.post(url, headers={**PAY, "Idempotency-Key": "k1"}, params={"memory": "off"}).json()
    assert first["runId"] == again["runId"] and len(repo.runs) == 1
    assert repo.runs[first["runId"]]["memoryMode"] == "off"


def test_a_crashing_agent_still_finishes_the_run(api):
    client, repo = api

    class Boom:
        model = "boom"

        def complete(self, *a, **k):
            raise RuntimeError("model down")

    app.dependency_overrides[get_agent_deps] = lambda: AgentDeps(
        runner=FakeRunner(), memory=FakeMemoryStore(), llm=Boom(), synchronous=True
    )
    _, run_id = start(client)
    events = client.get(f"/runs/{run_id}/events", headers=PAY).json()
    assert events[-1]["type"] == "run_finished"
    assert client.get(f"/runs/{run_id}", headers=PAY).json()["status"] in ("finished", "error")
