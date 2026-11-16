"""Fence endpoints: scoped search and the admin-only unscoped comparison.
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
from tests.memory.test_leakage import TEXT, draft, proof  # noqa: E402

KEYS = {**DEMO_PRINCIPALS,
        "test-platform-admin": {"tenantId": "demo-org", "teamId": "team-platform", "role": "memory_admin"}}
PAY, PLAT = {"X-API-Key": "test-payments-eng"}, {"X-API-Key": "test-platform-eng"}
PLAT_ADMIN = {"X-API-Key": "test-platform-admin"}
TITLE = "Fence test: record the replay"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEMO_PRINCIPALS", json.dumps(KEYS))
    get_settings.cache_clear()
    return TestClient(app)


@pytest.fixture
def memory_id(payments):
    s = AtlasMemoryStore()
    mem_id = s.promote(payments, draft(), proof(), title=TITLE)
    end = time.time() + 60
    while not s.is_searchable(payments, mem_id) and time.time() < end:
        time.sleep(1)
    yield mem_id
    s.memories.delete_many({"_id": mem_id})
    s.db.memory_audit.delete_many({"memoryId": mem_id})


def ids(res) -> list[str]:
    return [m["memoryId"] for m in res.json()["memories"]]


def test_search_is_team_scoped_and_prints_its_filter(client, memory_id):
    pay = client.get("/memories/search", params={"q": TEXT}, headers=PAY)
    plat = client.get("/memories/search", params={"q": TEXT}, headers=PLAT)
    assert pay.status_code == plat.status_code == 200
    assert memory_id in ids(pay)
    assert memory_id not in ids(plat)
    f = plat.json()["filter"]
    assert f["readableBy"] == {"$in": ["team-platform"]} and f["tenantId"] == "demo-org"
    assert f["expiresAt"] == {"$gt": "now"}


def test_compare_unscoped_is_admin_only(client, memory_id):
    assert client.get("/memories/compare-unscoped", params={"q": TEXT}, headers=PLAT).status_code == 403


def test_compare_unscoped_finds_it_but_leaks_nothing(client, memory_id):
    res = client.get("/memories/compare-unscoped", params={"q": TEXT}, headers=PLAT_ADMIN)
    assert res.status_code == 200
    hit = next(m for m in res.json()["memories"] if m["memoryId"] == memory_id)
    assert hit["ownerTeamId"] == "team-payments"
    assert hit["title"] == "Hidden: a Payments memory"
    # No content of the hidden memory: not its title, not its conditions. (The query itself is echoed
    # back in "query", so search only the memories part of the response.)
    memories = json.dumps(res.json()["memories"])
    assert TITLE not in memories, memories
    assert hit["applicability"] == {"conditions": {"dupKeyField": None, "sameEventIdOnBothDeliveries": None},
                                    "excludes": []}
    assert "readableBy" not in res.json()["filter"]  # the team filter is exactly what is dropped
