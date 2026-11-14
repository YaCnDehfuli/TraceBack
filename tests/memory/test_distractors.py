"""R8: vector search means something. With ~20 labelled distractors seeded across both teams, every
case's real recall query finds the real memory above the cutoff, no distractor clears it, and the
Fence still reads "Platform sees 0". Run: uv run pytest -m atlas tests/memory"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from core.config import get_settings

pytestmark = pytest.mark.atlas

if not get_settings().mongodb_uri.get_secret_value():
    pytest.skip("MONGODB_URI not set", allow_module_level=True)

from agent.observe import observations_from_case  # noqa: E402
from contracts.models import (  # noqa: E402
    Applicability,
    CaseManifest,
    FilePatch,
    MemoryDraft,
)
from core.clock import new_id, utc_now  # noqa: E402
from memory.config import MIN_SCORE  # noqa: E402
from memory.embeddings import embed_one  # noqa: E402
from memory.store import AtlasMemoryStore  # noqa: E402
from scripts.seed_demo import seed_distractors  # noqa: E402
from tests.memory.test_leakage import proof  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CASES = ["A", "B", "B2", "B3", "C", "D", "P"]
FENCE_QUERY = "Duplicate webhook delivery raises E11000 on provider_event_id; retry carries the same event identifier."


def summary(case_id: str) -> str:
    m = CaseManifest.model_validate_json((ROOT / "cases" / case_id / "manifest.json").read_text("utf-8"))
    return observations_from_case(m, incident_id="x").summary


@pytest.fixture(scope="module")
def world():
    """Distractors (idempotent) + a memory earned from case A, exactly as a real promote stores it."""
    from contracts.models import Principal
    s = AtlasMemoryStore()
    seed_distractors(s)
    payments = Principal(tenant_id="demo-org", team_id="team-payments")
    real = s.promote(payments, MemoryDraft(
        incident_id=new_id("test_inc"), repository_id="payments-webhooks", source_revision="test",
        retrieval_text=summary("A"), signature={"errorCode": "11000", "operation": "POST /webhooks/provider"},
        confirmed_cause="c", applicability=Applicability(), resolution_summary="r",
        patch=FilePatch(path="app/webhooks.py", new_content="x\n")), proof())
    end = time.time() + 60
    while not s.is_searchable(payments, real) and time.time() < end:
        time.sleep(1)
    distractors = {d["_id"] for d in s.memories.find(
        {"provenance.sourceIncidentId": {"$regex": "^seed_distractor_"}}, {"_id": 1})}
    yield s, real, distractors
    s.memories.delete_many({"_id": real})
    s.db.memory_audit.delete_many({"memoryId": real})


@pytest.mark.parametrize("case_id", CASES)
def test_cutoff_separates_the_real_memory_from_every_distractor(world, case_id):
    s, real, distractors = world
    assert len(distractors) >= 20
    filt = {"tenantId": "demo-org", "status": "active", "expiresAt": {"$gt": utc_now()}, "embeddingVersion": 1}
    hits = {h["_id"]: h["score"] for h in s._vector(embed_one(summary(case_id), "query"), filt, limit=40)}
    assert hits.get(real, 0) >= MIN_SCORE, f"{case_id}: real memory scored {hits.get(real)} < {MIN_SCORE}"
    worst = max((hits[i] for i in distractors if i in hits), default=0)
    assert worst < MIN_SCORE, f"{case_id}: a distractor scored {worst} >= {MIN_SCORE}"


def test_fence_still_reads_payments_1_platform_0_with_distractors(world, payments, platform):
    s, real, distractors = world
    pay = [c.memory_id for c in s.search(payments, FENCE_QUERY)]
    assert real in pay and not set(pay) & distractors
    assert [c.memory_id for c in s.search(platform, FENCE_QUERY)] == []


def test_case_d_platform_recall_finds_nothing(world, platform):
    s, _, _ = world
    from contracts.models import Observations
    obs = Observations(incident_id="d", repository_id="platform-webhooks", summary=summary("D"),
                       error_code="11000", operation="POST /webhooks/provider")
    assert s.recall(platform, obs, "run_d") == []
