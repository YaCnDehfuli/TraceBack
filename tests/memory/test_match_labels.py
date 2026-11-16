""""match: strong" comes from vector similarity only. An exact signature hit (same error code and
operation) still surfaces a look-alike, so its conditions can refuse it, but it is never "strong"
because of the signature. Run: uv run pytest -m atlas tests/memory"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from memory.store import STRONG_MATCH, match_label

ROOT = Path(__file__).resolve().parents[2]


def test_label_comes_from_the_vector_score_only():
    assert match_label(None) == "weak"  # found by signature only
    assert match_label(0.0) == "weak"
    assert match_label(STRONG_MATCH) == "strong"
    assert match_label(0.952) == "strong"  # a true repeat
    assert match_label(0.939) == "weak"  # look-alike D
    assert match_label(0.927) == "weak"  # look-alike C


def _store():
    from core.config import get_settings

    if not get_settings().mongodb_uri.get_secret_value():
        pytest.skip("MONGODB_URI not set")
    from memory.store import AtlasMemoryStore

    return AtlasMemoryStore()


def _promote(s, principal, text: str) -> str:
    from contracts.models import Applicability, FilePatch, MemoryDraft
    from core.clock import new_id
    from tests.memory.test_leakage import proof

    mem_id = s.promote(principal, MemoryDraft(
        incident_id=new_id("test_inc"), repository_id="payments-webhooks", source_revision="test",
        retrieval_text=text, signature={"errorCode": "11000", "operation": "POST /webhooks/provider"},
        confirmed_cause="c", applicability=Applicability(), resolution_summary="r",
        patch=FilePatch(path="app/webhooks.py", new_content="x\n")), proof())
    end = time.time() + 60
    while not s.is_searchable(principal, mem_id) and time.time() < end:
        time.sleep(1)
    return mem_id


def _cleanup(s, mem_id: str) -> None:
    s.memories.delete_many({"_id": mem_id})
    s.db.memory_audit.delete_many({"memoryId": mem_id})


@pytest.mark.atlas
def test_a_signature_only_hit_is_surfaced_but_weak(payments):
    """Same error code and operation, unrelated symptoms: still recalled (so it can be refused), but weak."""
    from contracts.models import Observations

    s = _store()
    mem_id = _promote(s, payments, "Nightly CSV export job exceeds the worker timeout for large tenants.")
    try:
        obs = Observations(incident_id="x", repository_id="payments-webhooks",
                           summary="Provider notifications fail with HTTP 500 after a retry.",
                           error_code="11000", operation="POST /webhooks/provider")
        cand = next(c for c in s.recall(payments, obs, "run_sig") if c.memory_id == mem_id)
        assert cand.source == "signature" and cand.match == "weak"
    finally:
        _cleanup(s, mem_id)


def _summary(case_id: str) -> str:
    from agent.observe import observations_from_case
    from contracts.models import CaseManifest

    m = CaseManifest.model_validate_json((ROOT / "cases" / case_id / "manifest.json").read_text("utf-8"))
    return observations_from_case(m, incident_id="x").summary


def _observations(case_id: str):
    from agent.observe import observations_from_case
    from contracts.models import CaseManifest

    m = CaseManifest.model_validate_json((ROOT / "cases" / case_id / "manifest.json").read_text("utf-8"))
    return observations_from_case(m, incident_id="x")


NEW_TEXT = _summary("A").startswith("duplicate key field:")


@pytest.mark.atlas
@pytest.mark.skipif(not NEW_TEXT, reason="needs the code-derived recall text")
def test_true_repeats_are_strong_and_look_alikes_weak(payments):
    from contracts.models import Principal

    s = _store()
    mem_id = _promote(s, payments, _summary("A"))  # the Earn memory, exactly as promote stores it
    try:
        for case_id, want in [("B", "strong"), ("B2", "strong"), ("B3", "strong"), ("C", "weak")]:
            cand = next(c for c in s.recall(payments, _observations(case_id), f"run_{case_id}")
                        if c.memory_id == mem_id)
            assert cand.match == want, f"case {case_id}: {cand.match} (score {cand.score:.3f})"
        # D is Platform's incident: Platform never sees Payments' memory; without the team filter it would,
        # and even then only as a weak match.
        platform_admin = Principal(tenant_id="demo-org", team_id="team-platform", role="memory_admin")
        hit = next(c for c in s.unscoped_cards(platform_admin, _summary("D")) if c.memory_id == mem_id)
        assert hit.match == "weak"
    finally:
        _cleanup(s, mem_id)
