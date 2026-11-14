"""Live practice app: the real bug on the original code, the verified fix replayed (needs the fixture MongoDB)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("live_app", ROOT / "scripts" / "live_app.py")
live_app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(live_app)


def _fixture_db_unreachable_reason() -> str | None:
    try:
        from pymongo import MongoClient

        MongoClient(live_app._fixture_uri(), serverSelectionTimeoutMS=2000).admin.command("ping")
        return None
    except Exception as exc:  # noqa: BLE001 - any failure means "not reachable"
        return type(exc).__name__


_reason = _fixture_db_unreachable_reason()
pytestmark = pytest.mark.skipif(
    _reason is not None,
    reason=f"fixture MongoDB not reachable (set FIXTURE_MONGODB_URI, e.g. mongodb://localhost:27017): {_reason}",
)


@pytest.fixture
def live():
    return live_app


@pytest.fixture
def client(live):
    return TestClient(live.app)


def _events(attempt_status: str) -> list[dict]:
    fix = (ROOT / "cases" / "B" / "reference" / "webhooks.py").read_text(encoding="utf-8")
    return [
        {"runId": "run_t", "seq": 1, "type": "patch_proposed",
         "payload": {"attempt": 1, "patch": {"path": "app/webhooks.py", "newContent": fix}, "fromMemoryLines": [3]}},
        {"runId": "run_t", "seq": 2, "type": "verification",
         "payload": {"attempt": 1, "result": {"status": attempt_status}}},
    ]


def test_before_crashes_on_the_retry(client):
    r = client.post("/api/replay", json={"case": "B", "mode": "before"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"]["source"] == "original"
    assert body["deliveries"][0]["status"] == 200
    assert body["deliveries"][1]["status"] == 500
    assert "E11000" in body["deliveries"][1]["error"]
    assert body["verdict"] == "crashed"


def test_after_replays_the_verified_fix(live, client, monkeypatch):
    monkeypatch.setattr(live, "fetch_events", lambda *_a, **_k: _events("passed"))
    r = client.post("/api/replay", json={"case": "B", "mode": "after", "runId": "run_t"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code"]["source"] == "agent-fix" and body["code"]["verified"] and body["code"]["attempt"] == 1
    assert [d["status"] for d in body["deliveries"]] == [200, 200]
    assert body["ledger"]["credited"] == 4000 == body["ledger"]["expectedCredit"]
    assert body["ledger"]["replaysRecorded"] == 1
    assert body["verdict"] == "ok"


def test_after_without_a_verified_fix_is_409(live, client, monkeypatch):
    monkeypatch.setattr(live, "fetch_events", lambda *_a, **_k: _events("failed"))
    r = client.post("/api/replay", json={"case": "B", "mode": "after", "runId": "run_t"})
    assert r.status_code == 409
    assert r.json()["detail"] == "this run has no verified fix"


def test_bad_case_or_mode_is_400(client):
    assert client.post("/api/replay", json={"case": "../x", "mode": "before"}).status_code == 400
    assert client.post("/api/replay", json={"case": "B", "mode": "sideways"}).status_code == 400
