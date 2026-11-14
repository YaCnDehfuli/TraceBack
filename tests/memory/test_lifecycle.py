"""Correction and history (P2-7, R7), and that no retired memory ever comes back from recall.
Run: uv run pytest -m atlas tests/memory"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from core.config import get_settings

pytestmark = pytest.mark.atlas

if not get_settings().mongodb_uri.get_secret_value():
    pytest.skip("MONGODB_URI not set", allow_module_level=True)

from api.main import app  # noqa: E402
from memory.store import AtlasMemoryStore  # noqa: E402
from tests.conftest import DEMO_PRINCIPALS  # noqa: E402
from tests.memory.test_leakage import TEXT, draft, obs, proof  # noqa: E402

KEYS = {**DEMO_PRINCIPALS,
        "test-platform-admin": {"tenantId": "demo-org", "teamId": "team-platform", "role": "memory_admin"}}
PAY_ENG, PAY_ADMIN = {"X-API-Key": "test-payments-eng"}, {"X-API-Key": "test-payments-admin"}
PLAT_ADMIN = {"X-API-Key": "test-platform-admin"}
NARROW = {"excludes": ["Unique index on customer_id"], "reason": "Near-misses on case C"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEMO_PRINCIPALS", json.dumps(KEYS))
    get_settings.cache_clear()
    return TestClient(app)


@pytest.fixture
def mem(payments):
    s = AtlasMemoryStore()
    mem_id = s.promote(payments, draft(), proof())
    end = time.time() + 60
    while not s.is_searchable(payments, mem_id) and time.time() < end:
        time.sleep(1)
    yield s, mem_id
    s.memories.delete_many({"lineageId": mem_id})
    s.db.memory_audit.delete_many({"memoryId": {"$regex": f"^{mem_id}"}})


def recalled(s: AtlasMemoryStore, p) -> list[str]:
    return [c.memory_id for c in s.recall(p, obs(), "run_t")]


def test_correction_makes_v2_and_keeps_v1_in_history(client, mem, payments):
    s, mem_id = mem
    res = client.post(f"/memories/{mem_id}/correct", headers=PAY_ADMIN, json=NARROW)
    assert res.status_code == 200, res.text
    v2 = res.json()
    assert v2["version"] == 2 and v2["memoryId"] == f"{mem_id}_v2"
    assert v2["applicability"]["excludes"] == NARROW["excludes"]

    v1 = s.memories.find_one({"_id": mem_id})
    assert v1["status"] == "superseded"  # kept, not overwritten
    assert s.memories.find_one({"_id": f"{mem_id}_v2"})["supersedes"] == mem_id

    found = recalled(s, payments)
    assert f"{mem_id}_v2" in found and mem_id not in found  # superseded never comes back

    # v1 can't be corrected again; the active version can.
    assert client.post(f"/memories/{mem_id}/correct", headers=PAY_ADMIN, json=NARROW).status_code == 422


def test_correction_rules(client, mem):
    s, mem_id = mem
    assert client.post(f"/memories/{mem_id}/correct", headers=PAY_ENG, json=NARROW).status_code == 403
    assert client.post(f"/memories/{mem_id}/correct", headers=PLAT_ADMIN, json=NARROW).status_code == 404
    bad = {"excludes": ["  "], "reason": "x"}
    assert client.post(f"/memories/{mem_id}/correct", headers=PAY_ADMIN, json=bad).status_code == 422
    assert s.memories.find_one({"_id": mem_id})["status"] == "active"


def test_history_shows_the_whole_lineage_and_survives_forget(client, mem, payments):
    s, mem_id = mem
    s.recall(payments, obs(), "run_reader")  # a read to show up in "who read it"
    client.post(f"/memories/{mem_id}/correct", headers=PAY_ADMIN, json=NARROW)

    hist = client.get(f"/memories/{mem_id}/audit", headers=PAY_ADMIN)
    assert hist.status_code == 200, hist.text
    events = [e["event"] for e in hist.json()]
    assert events[0] == "promoted" and "retrieved" in events and events.count("corrected") == 2
    assert any(e["runId"] == "run_reader" for e in hist.json())
    assert client.get(f"/memories/{mem_id}/audit", headers=PAY_ENG).status_code == 403
    assert client.get(f"/memories/{mem_id}/audit", headers=PLAT_ADMIN).status_code == 404

    client.request("DELETE", f"/memories/{mem_id}_v2", headers=PAY_ADMIN, json={"reason": "cleanup"})
    after = client.get(f"/memories/{mem_id}/audit", headers=PAY_ADMIN)
    assert after.status_code == 200
    assert [e["event"] for e in after.json()].count("forgotten") == 2  # v1 and v2 tombstones
    assert TEXT not in after.text  # history never holds memory content
    assert client.get(f"/memories/{mem_id}/audit", headers=PLAT_ADMIN).status_code == 404


def test_no_retired_memory_ever_comes_back(mem, payments):
    """Superseded, revoked, disputed, expired: recall drops each one at once (re-read guard)."""
    s, mem_id = mem
    assert mem_id in recalled(s, payments)
    for change in ({"status": "superseded"}, {"status": "revoked"}, {"status": "disputed"}):
        s.memories.update_one({"_id": mem_id}, {"$set": {**change}})
        assert mem_id not in recalled(s, payments), change
        s.memories.update_one({"_id": mem_id}, {"$set": {"status": "active"}})
    from core.clock import utc_now
    s.memories.update_one({"_id": mem_id}, {"$set": {"expiresAt": utc_now()}})
    assert mem_id not in recalled(s, payments)
