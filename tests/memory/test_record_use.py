"""record_use: the store turns the agent's decision into the governance outcome.
Run: uv run pytest -m atlas tests/memory"""

from __future__ import annotations

from datetime import timedelta

import pytest

from contracts.models import MemoryUseDecision, PreconditionResult, TestOutcome
from core.clock import utc_now
from core.config import get_settings

pytestmark = pytest.mark.atlas

if not get_settings().mongodb_uri.get_secret_value():
    pytest.skip("MONGODB_URI not set", allow_module_level=True)

from memory.policy import DEMO_POLICY  # noqa: E402
from memory.store import AtlasMemoryStore  # noqa: E402
from tests.memory.test_leakage import draft, obs, proof  # noqa: E402

HELD = [
    PreconditionResult(check="dup_key_field", expected="provider_event_id", actual="provider_event_id", held=True),
    PreconditionResult(check="same_event_id_on_both_deliveries", expected="true", actual="true", held=True),
]
FAILED_KEY = [
    PreconditionResult(check="dup_key_field", expected="provider_event_id", actual="customer_id", held=False),
    HELD[1],
]


@pytest.fixture
def mem(payments):
    s = AtlasMemoryStore()
    mem_id = s.promote(payments, draft(), proof())
    yield s, mem_id
    s.memories.delete_many({"_id": mem_id})
    s.db.memory_audit.delete_many({"memoryId": mem_id})


def events(s: AtlasMemoryStore, mem_id: str) -> list[str]:
    return [e["event"] for e in s.db.memory_audit.find({"memoryId": mem_id}).sort("at", 1)]


def test_conditions_false_is_a_near_miss_and_memory_stays_active(mem, payments):
    s, mem_id = mem
    d = MemoryUseDecision(decision="rejected", preconditions=FAILED_KEY, reason="duplicate key is customer_id")
    assert s.record_use(payments, mem_id, 1, "run_c", d) == "near_miss"
    assert s.memories.find_one({"_id": mem_id})["status"] == "active"
    assert "near_miss" in events(s, mem_id)


def test_verified_reuse_renews_expiry(mem, payments):
    s, mem_id = mem
    soon = utc_now() + timedelta(minutes=5)
    s.memories.update_one({"_id": mem_id}, {"$set": {"expiresAt": soon}})
    d = MemoryUseDecision(decision="used", preconditions=HELD, reason="2/2 hold", verification=proof())
    assert s.record_use(payments, mem_id, 1, "run_b", d) == "renewed"
    doc = s.memories.find_one({"_id": mem_id})
    assert doc["expiresAt"] > soon + timedelta(hours=1)
    assert doc["purgeAt"] > doc["expiresAt"]
    assert events(s, mem_id)[-2:] == ["used", "renewed"]


def test_renewal_is_capped_at_max_lifetime(mem, payments):
    s, mem_id = mem
    created = utc_now() - timedelta(hours=47)
    s.memories.update_one({"_id": mem_id}, {"$set": {"createdAt": created, "expiresAt": utc_now()
                                                     + timedelta(minutes=1)}})
    d = MemoryUseDecision(decision="used", preconditions=HELD, reason="ok", verification=proof())
    s.record_use(payments, mem_id, 1, "run_b", d)
    doc = s.memories.find_one({"_id": mem_id})
    assert doc["expiresAt"] <= created + timedelta(seconds=DEMO_POLICY["maxLifetimeSeconds"]) + timedelta(seconds=1)


def test_failed_reuse_with_conditions_held_disputes_and_hides_it(mem, payments):
    s, mem_id = mem
    failed = proof(status="failed", after_passed=False, tests=[TestOutcome(name="t", passed=False)])
    d = MemoryUseDecision(decision="used", preconditions=HELD, reason="applied", verification=failed)
    assert s.record_use(payments, mem_id, 1, "run_x", d) == "disputed"
    assert s.memories.find_one({"_id": mem_id})["status"] == "disputed"
    # Even while the vector index lags, recall's re-read guard drops it.
    assert mem_id not in [c.memory_id for c in s.recall(payments, obs(), "run_y")]


def test_inconclusive_verification_blames_nothing(mem, payments):
    s, mem_id = mem
    d = MemoryUseDecision(decision="used", preconditions=HELD, reason="applied",
                          verification=proof(status="inconclusive", after_passed=False))
    assert s.record_use(payments, mem_id, 1, "run_i", d) is None
    assert s.memories.find_one({"_id": mem_id})["status"] == "active"


def test_other_team_or_vanished_memory_is_ignored_not_raised(mem, platform):
    s, mem_id = mem
    d = MemoryUseDecision(decision="used", preconditions=HELD, reason="x", verification=proof())
    assert s.record_use(platform, mem_id, 1, "run_p", d) is None
    assert s.memories.find_one({"_id": mem_id})["status"] == "active"
    assert s.record_use(platform, "mem_gone", 1, "run_p", d) is None
    s.db.memory_audit.delete_many({"memoryId": "mem_gone"})


def test_run_in_flight_never_revives_an_expired_memory(mem, payments):
    """An admin's "expire now" during a run must stick, even if the run's fix then verifies."""
    s, mem_id = mem
    gone = utc_now() - timedelta(seconds=1)
    s.memories.update_one({"_id": mem_id}, {"$set": {"expiresAt": gone}})
    d = MemoryUseDecision(decision="used", preconditions=HELD, reason="ok", verification=proof())
    assert s.record_use(payments, mem_id, 1, "run_late", d) is None
    assert s.memories.find_one({"_id": mem_id})["expiresAt"] <= gone + timedelta(milliseconds=1)
    assert "not_renewed" in events(s, mem_id)


def test_disputed_memory_is_not_renewed(mem, payments):
    s, mem_id = mem
    s.memories.update_one({"_id": mem_id}, {"$set": {"status": "disputed"}})
    d = MemoryUseDecision(decision="used", preconditions=HELD, reason="ok", verification=proof())
    assert s.record_use(payments, mem_id, 1, "run_late", d) is None
    assert s.memories.find_one({"_id": mem_id})["status"] == "disputed"
