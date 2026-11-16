"""Forget and expire-now. Run: uv run pytest -m atlas tests/memory"""

from __future__ import annotations

import json
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from core.clock import utc_now
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
REASON = {"reason": "Customer data in the fix"}


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


def test_forget_deletes_every_version_and_leaves_a_content_free_tombstone(client, mem, payments):
    s, mem_id = mem
    v1 = s.memories.find_one({"_id": mem_id})
    s.memories.insert_one({**v1, "_id": f"{mem_id}_v2", "version": 2, "supersedes": mem_id})  # a corrected v2
    s.memories.update_one({"_id": mem_id}, {"$set": {"status": "superseded"}})

    res = client.request("DELETE", f"/memories/{mem_id}", headers=PAY_ADMIN, json=REASON)
    assert res.status_code == 200, res.text
    card = res.json()
    assert card["forgotten"]["reason"] == REASON["reason"]
    assert card["forgotten"]["forgottenBy"] == "memory_admin@team-payments"
    assert card["title"] == "Forgotten memory" and TEXT not in res.text

    assert s.memories.count_documents({"lineageId": mem_id}) == 0  # v1 AND v2 are gone
    assert mem_id not in [c.memory_id for c in s.recall(payments, obs(), "run_after")]  # immediately
    assert client.get(f"/memories/{mem_id}", headers=PAY_ENG).status_code == 404

    tombs = list(s.db.memory_audit.find({"memoryId": {"$in": [mem_id, f"{mem_id}_v2"]}, "event": "forgotten"}))
    assert len(tombs) == 2
    for t in tombs:
        assert t["contentHash"] is None and t["reason"] == REASON["reason"]
        assert TEXT not in json.dumps(t, default=str)


def test_forget_needs_an_admin_of_the_owner_team_and_a_reason(client, mem):
    s, mem_id = mem
    assert client.request("DELETE", f"/memories/{mem_id}", headers=PAY_ENG, json=REASON).status_code == 403
    assert client.request("DELETE", f"/memories/{mem_id}", headers=PLAT_ADMIN, json=REASON).status_code == 404
    assert client.request("DELETE", f"/memories/{mem_id}", headers=PAY_ADMIN, json={"reason": "  "}).status_code == 422
    assert s.memories.count_documents({"_id": mem_id}) == 1


def test_expire_now_takes_effect_on_recall_immediately(client, mem, payments):
    s, mem_id = mem
    res = client.post(f"/memories/{mem_id}/expire", headers=PAY_ADMIN, json={"reason": "demo"})
    assert res.status_code == 200, res.text
    doc = s.memories.find_one({"_id": mem_id})
    assert doc["expiresAt"] <= utc_now() and doc["purgeAt"] > doc["expiresAt"]
    assert mem_id not in [c.memory_id for c in s.recall(payments, obs(), "run_after")]
    assert s.db.memory_audit.count_documents({"memoryId": mem_id, "event": "expired_now"}) == 1
    assert doc["purgeAt"] - doc["expiresAt"] <= timedelta(hours=1)  # TTL purge after the grace period
