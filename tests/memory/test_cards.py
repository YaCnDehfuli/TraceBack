"""Memory card routes are team-scoped (P2-4). Run: uv run pytest -m atlas tests/memory"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from core.config import get_settings

pytestmark = pytest.mark.atlas

if not get_settings().mongodb_uri.get_secret_value():
    pytest.skip("MONGODB_URI not set", allow_module_level=True)

from api.main import app  # noqa: E402
from memory.store import AtlasMemoryStore  # noqa: E402
from tests.memory.test_leakage import draft, proof  # noqa: E402

PAY = {"X-API-Key": "test-payments-eng"}  # keys from tests/conftest.py
PLAT = {"X-API-Key": "test-platform-eng"}


@pytest.fixture
def memory_id(payments):
    s = AtlasMemoryStore()
    mem_id = s.promote(payments, draft(), proof())
    yield mem_id
    s.memories.delete_many({"_id": mem_id})
    s.db.memory_audit.delete_many({"memoryId": mem_id})


def test_cards_are_team_scoped(memory_id):
    c = TestClient(app)
    assert memory_id in [m["memoryId"] for m in c.get("/memories", headers=PAY).json()]
    assert memory_id not in [m["memoryId"] for m in c.get("/memories", headers=PLAT).json()]

    card = c.get(f"/memories/{memory_id}", headers=PAY)
    assert card.status_code == 200
    assert card.json()["proof"] == {"beforeFailed": True, "afterPassed": True, "testsTotal": 1,
                                    "verificationRunId": card.json()["proof"]["verificationRunId"]}
    for secret in ("hmacSecret", "embedding", "retrievalText", "resolution"):
        assert secret not in card.text

    # Same answer for "not your team" as for "doesn't exist": ids can't be probed.
    assert c.get(f"/memories/{memory_id}", headers=PLAT).status_code == 404
    assert c.get("/memories/mem_does_not_exist", headers=PAY).status_code == 404
    assert c.get("/memories").status_code == 401
