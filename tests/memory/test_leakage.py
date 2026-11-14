"""Fence and proof, against real Atlas (P2-3). Run: uv run pytest -m atlas tests/memory

Uses MONGODB_DB from .env (your own database, e.g. traceback_p2) after scripts/atlas_setup.py.
"""

from __future__ import annotations

import time

import pytest

from contracts.models import (
    Applicability,
    FilePatch,
    MemoryDraft,
    Observations,
    Principal,
    TestOutcome,
    VerificationResult,
)
from core.clock import new_id
from core.config import get_settings

pytestmark = pytest.mark.atlas

if not get_settings().mongodb_uri.get_secret_value():
    pytest.skip("MONGODB_URI not set", allow_module_level=True)

from memory.store import AtlasMemoryStore, MemoryRefused  # noqa: E402

TEXT = "Duplicate webhook delivery raises E11000 on provider_event_id; retry carries the same event identifier."
SIG = {"errorCode": "11000", "operation": "webhook.insert"}


def proof(**over) -> VerificationResult:
    base = dict(run_id=new_id("verify"), case_id="test", status="passed", before_failed=True, after_passed=True,
                tests=[TestOutcome(name="t", passed=True)], evidence_hashes=["h"])
    return VerificationResult(**{**base, **over})


def draft() -> MemoryDraft:
    return MemoryDraft(incident_id=new_id("test_inc"), repository_id="payments-webhooks", source_revision="test",
                       retrieval_text=TEXT, signature=SIG, confirmed_cause="c", applicability=Applicability(),
                       resolution_summary="r", patch=FilePatch(path="app/webhooks.py", new_content="x\n"))


def obs() -> Observations:
    return Observations(incident_id="inc_obs", repository_id="payments-webhooks", summary=TEXT,
                        error_code="11000", operation="webhook.insert")


@pytest.fixture
def store():
    s = AtlasMemoryStore()
    made: list[str] = []
    yield s, made
    s.memories.delete_many({"_id": {"$in": made}})
    s.db.memory_audit.delete_many({"memoryId": {"$in": made}})


def wait_searchable(s: AtlasMemoryStore, p: Principal, mem_id: str, timeout: float = 60) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if s.is_searchable(p, mem_id):
            return
        time.sleep(1)
    pytest.fail(f"{mem_id} not searchable after {timeout}s")


def test_platform_never_sees_payments_memory(store, payments, platform):
    s, made = store
    mem_id = s.promote(payments, draft(), proof())
    made.append(mem_id)
    wait_searchable(s, payments, mem_id)

    assert mem_id in [c.memory_id for c in s.recall(payments, obs(), "run_t1")]
    assert mem_id not in [c.memory_id for c in s.recall(platform, obs(), "run_t2")]
    assert mem_id not in [c.memory_id for c in s.search(platform, TEXT)]
    # Without the team filter Platform's query WOULD find it: the filter is what stops it.
    admin = platform.model_copy(update={"role": "memory_admin"})
    assert mem_id in [h["_id"] for h in s.unscoped_search(admin, TEXT)]


def test_results_never_carry_secret_or_vector(store, payments):
    s, made = store
    mem_id = s.promote(payments, draft(), proof())
    made.append(mem_id)
    wait_searchable(s, payments, mem_id)
    for doc in s._find(payments, TEXT, None, {"type": "test", "id": "t"}, None, 5, None):
        assert "hmacSecret" not in doc and "embedding" not in doc


def test_promote_is_idempotent(store, payments):
    s, made = store
    d = draft()
    first = s.promote(payments, d, proof())
    made.append(first)
    assert s.promote(payments, d, proof()) == first


@pytest.mark.parametrize("bad", [{"after_passed": False}, {"before_failed": False}, {"status": "failed"}])
def test_atlas_refuses_memory_without_proof(store, payments, bad):
    s, _ = store
    d, v = draft(), proof(**bad)
    with pytest.raises(MemoryRefused, match="Memory refused: no proof"):
        s.promote(payments, d, v)
    assert s.memories.count_documents({"provenance.sourceIncidentId": d.incident_id}) == 0
    assert s.db.memory_audit.count_documents({"event": "refused", "runId": v.run_id}) == 1
    s.db.memory_audit.delete_many({"runId": v.run_id})
