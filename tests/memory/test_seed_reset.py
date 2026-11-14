"""#67: `seed_demo.py --reset` starts the demo memory from a known state. Memories earlier agent runs
promoted in the demo repositories are forgotten (every version, tombstones), unrelated repositories
survive, a second reset is a no-op, and the canonical Earn memory comes back exactly once.
Run: uv run pytest -m atlas tests/memory   (never against traceback_demo: it resets the database)"""

from __future__ import annotations

import pytest

from core.config import get_settings

pytestmark = pytest.mark.atlas

_s = get_settings()
if not _s.mongodb_uri.get_secret_value():
    pytest.skip("MONGODB_URI not set", allow_module_level=True)
if _s.mongodb_db == "traceback_demo":
    pytest.skip("this test resets the database; never run it against traceback_demo", allow_module_level=True)

from contracts.models import Principal  # noqa: E402
from core.clock import new_id  # noqa: E402
from memory.store import AtlasMemoryStore  # noqa: E402
from scripts import seed_demo  # noqa: E402
from tests.memory.test_leakage import draft, obs, proof  # noqa: E402

ADMIN = Principal(tenant_id="demo-org", team_id="team-payments", role="memory_admin")
PLATFORM = Principal(tenant_id="demo-org", team_id="team-platform")


@pytest.fixture
def store():
    s = AtlasMemoryStore()
    made: list[str] = []
    yield s, made
    s.memories.delete_many({"lineageId": {"$in": made}})
    s.db.memory_audit.delete_many({"memoryId": {"$regex": "^(" + "|".join(made) + ")"}} if made else {"_id": None})


def test_reset_forgets_earlier_agent_memories_in_demo_repos_only(store, payments):
    s, made = store
    dup = s.promote(payments, draft(), proof())  # an agent-promoted duplicate Earn (seeded=False)
    s.correct(ADMIN, dup, ["Unique index on customer_id"], "a v2 the reset must also remove")
    plat_draft = draft().model_copy(update={"repository_id": "platform-webhooks"})
    plat = s.promote(PLATFORM, plat_draft, proof())  # a case-D-style Platform memory
    keep_draft = draft().model_copy(update={"repository_id": "payments-billing", "incident_id": new_id("keep")})
    keep = s.promote(payments, keep_draft, proof())  # another repository: must survive
    made += [dup, plat, keep]

    first = seed_demo.reset_memories(s)
    assert first["lineages"] >= 2 and first["versions"] >= 3
    assert s.memories.count_documents({"lineageId": {"$in": [dup, plat]}}) == 0  # v1, v2 and Platform's
    assert s.memories.count_documents({"_id": keep}) == 1  # unrelated repository untouched
    assert dup not in [c.memory_id for c in s.recall(payments, obs(), "run_after_reset")]

    tombs = list(s.db.memory_audit.find({"memoryId": {"$in": [dup, f"{dup}_v2", plat]}, "event": "forgotten"}))
    assert len(tombs) == 3
    assert all(t["actor"] == {"type": "policy", "id": "demo-reset"} and t["contentHash"] is None for t in tombs)

    second = seed_demo.reset_memories(s)  # stable: nothing left to forget
    assert second["lineages"] == 0 and second["versions"] == 0
    assert s.memories.count_documents({"_id": keep}) == 1


def test_reset_then_reseed_gives_exactly_one_earn_and_the_distractors(store):
    s, _ = store
    for _ in range(2):  # reset + re-earn twice: still exactly one canonical Earn memory
        seed_demo.reset_memories(s)
        assert seed_demo.earn(s, "fake", reset=True) is True
        assert seed_demo.seed_distractors(s) == 20
    assert s.memories.count_documents({"provenance.sourceIncidentId": seed_demo.EARN_INCIDENT}) == 1
    assert s.memories.count_documents({"repositoryId": {"$in": seed_demo.DEMO_REPOSITORIES},
                                       "status": "active"}) == 1 + 2  # Earn + one distractor in each demo repo
    assert s.memories.count_documents({"provenance.sourceIncidentId": {"$regex": "^seed_distractor_"}}) == 20
