""""Memory refused: no proof." Atlas refuses a memory whose fix failed verification, the refusal
is recorded with the failing tests (no content), and the team can see it. Run: uv run pytest -m atlas"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from core.config import get_settings

pytestmark = pytest.mark.atlas

if not get_settings().mongodb_uri.get_secret_value():
    pytest.skip("MONGODB_URI not set", allow_module_level=True)

from api.main import app  # noqa: E402
from contracts.models import TestOutcome  # noqa: E402
from core.clock import new_id  # noqa: E402
from memory.store import AtlasMemoryStore, MemoryRefused  # noqa: E402
from tests.conftest import DEMO_PRINCIPALS  # noqa: E402
from tests.memory.test_leakage import draft, proof  # noqa: E402

# What the runner reports for case P's poisoned fix (it drops the unique index).
POISONED = [TestOutcome(name=n, passed=n != "test_unique_index_still_present") for n in (
    "test_single_payment_credited", "test_duplicate_event_reproduces", "test_duplicate_event_single_effect",
    "test_distinct_events_same_customer", "test_unique_index_still_present", "test_replay_recorded_for_reconciliation")]


def poisoned_result():
    return proof(run_id=new_id("verify"), case_id="P", status="failed", after_passed=False, tests=POISONED)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DEMO_PRINCIPALS", json.dumps(DEMO_PRINCIPALS))
    get_settings.cache_clear()
    return TestClient(app)


def test_refusal_is_recorded_with_failing_tests_and_visible_to_the_team(client, payments):
    s, v = AtlasMemoryStore(), poisoned_result()
    d = draft()
    try:
        with pytest.raises(MemoryRefused, match="Memory refused: no proof"):
            s.promote(payments, d, v)
        assert s.memories.count_documents({"provenance.sourceIncidentId": d.incident_id}) == 0

        pay = client.get("/memories/refusals", headers={"X-API-Key": "test-payments-eng"})
        assert pay.status_code == 200
        ev = next(e for e in pay.json() if e["runId"] == v.run_id)
        assert ev["event"] == "refused"
        assert ev["details"]["failedTests"] == ["test_unique_index_still_present"]
        assert ev["details"]["testsPassed"] == 5 and ev["details"]["testsTotal"] == 6
        assert ev["details"]["caseId"] == "P"
        assert "retrievalText" not in pay.text and d.retrieval_text not in pay.text  # no content

        plat = client.get("/memories/refusals", headers={"X-API-Key": "test-platform-eng"})
        assert v.run_id not in [e["runId"] for e in plat.json()]  # team-scoped
    finally:
        s.db.memory_audit.delete_many({"runId": v.run_id})


def test_seed_poison_reports_a_real_refusal(monkeypatch):
    """--poison only says "refused" when Atlas really refused (runner stubbed: Docker isn't here)."""
    import runner.sandbox
    from scripts import seed_demo

    v = poisoned_result()
    monkeypatch.setattr(runner.sandbox.LocalRunner, "verify", lambda self, case_id, patch: v)
    s = AtlasMemoryStore()
    try:
        assert seed_demo.poison(s) is True
        assert s.db.memory_audit.count_documents({"event": "refused", "runId": v.run_id}) == 1
        assert s.memories.count_documents({"provenance.sourceIncidentId": "inc_demo_poison_P"}) == 0
    finally:
        s.db.memory_audit.delete_many({"runId": v.run_id})
