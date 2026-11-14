"""The API shell: health, identity from the API key only, admin-only routes, stubs answer 501."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "service": "traceback"}


def test_ui_is_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Traceback" in r.text


def test_identity_comes_only_from_the_key(client):
    assert client.get("/whoami").status_code == 401
    assert client.get("/whoami", headers={"X-API-Key": "nope"}).status_code == 401
    me = client.get("/whoami", headers={"X-API-Key": "test-platform-eng"}).json()
    assert me["teamId"] == "team-platform"


def test_admin_routes_refuse_engineers(client):
    r = client.request("DELETE", "/memories/mem_1", headers={"X-API-Key": "test-payments-eng"}, json={"reason": "test"})
    assert r.status_code == 403


def test_stubs_answer_501(client):
    key = {"X-API-Key": "test-payments-eng"}
    assert client.get("/runs/run_1", headers=key).status_code == 501
    # /memories/search is implemented since P2-5 (covered by tests/memory/test_fence.py).


def test_sample_events_endpoint(client):
    events = client.get("/dev/sample-run-events").json()
    assert events and events[0]["type"] == "run_started"
