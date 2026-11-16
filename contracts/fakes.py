"""Stand-ins for the real MemoryStore and Runner, for tests that need neither Atlas nor a test database.

    from contracts.fakes import FakeMemoryStore, FakeRunner

Production uses memory.store.AtlasMemoryStore and runner.sandbox.LocalRunner instead.
They follow the same rules as the real ones (team scope, verify-gated promotion), only in memory
and with canned answers. FakeRunner also models the Payments convention: a fix without
`ledger.mark_replayed(...)` fails test_replay_recorded_for_reconciliation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from contracts.models import (
    Applicability,
    Conditions,
    FileAnchor,
    FilePatch,
    MemoryCandidate,
    MemoryDraft,
    MemoryOutcome,
    MemoryUseDecision,
    Observations,
    Principal,
    TestOutcome,
    VerificationResult,
)
from core.clock import new_id, sha256_text, utc_now

TRUSTED_TESTS = [
    "test_duplicate_event_reproduces",
    "test_duplicate_event_single_effect",
    "test_replay_recorded_for_reconciliation",
    "test_distinct_events_same_customer",
    "test_unique_index_still_present",
    "test_single_payment_regression",
    "test_invalid_payload_rejected",
]

REFERENCE_FIX = """\
from pymongo.errors import DuplicateKeyError


def receive(event, db, ledger):
    try:
        db.payments.insert_one(
            {"provider_event_id": event.id, "customer_id": event.customer_id, "amount": event.amount}
        )
    except DuplicateKeyError:
        ledger.mark_replayed(event.id)
        return {"ok": True, "duplicate": True}
    ledger.credit(event.customer_id, event.amount)
    return {"ok": True}
"""


def example_memory_candidate(rank: int = 1, score: float = 0.83) -> MemoryCandidate:
    """The webhook-replay memory from the Earn beat, as recall would return it."""
    return MemoryCandidate(
        memory_id="mem_webhook_replay",
        version=1,
        owner_team_id="team-payments",
        repository_id="payments-webhooks",
        rank=rank,
        score=score,
        match="strong",
        source="vector",
        retrieval_text=(
            "Duplicate webhook delivery raises E11000 on provider_event_id; first delivery succeeded; "
            "retry carries the same event identifier."
        ),
        confirmed_cause="Replay path performs a second insert for an already-processed provider event.",
        resolution_summary=(
            "Treat a repeated provider_event_id as already processed, record it with "
            "ledger.mark_replayed(event_id), keep the unique index, credit exactly once."
        ),
        resolution_patch=FilePatch(path="app/webhooks.py", new_content=REFERENCE_FIX),
        applicability=Applicability(
            conditions=Conditions(dup_key_field="provider_event_id", same_event_id_on_both_deliveries=True),
            excludes=["unique index on a non-event field (e.g. customer_id)"],
        ),
        anchors=[FileAnchor(path="app/webhooks.py", sha256=sha256_text(REFERENCE_FIX))],
        expires_at=utc_now() + timedelta(hours=24),
    )


@dataclass
class _FakeMemory:
    candidate: MemoryCandidate
    tenant_id: str
    readable_by: list[str]
    error_code: str | None


@dataclass
class FakeMemoryStore:
    """In-memory MemoryStore. Enforces team scope and verify-gated promotion like the real one."""

    seed_example: bool = True
    tenant_id: str = "demo-org"
    memories: dict[str, _FakeMemory] = field(default_factory=dict)
    uses: list[dict] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.seed_example:
            c = example_memory_candidate()
            self.memories[c.memory_id] = _FakeMemory(c, self.tenant_id, ["team-payments"], "11000")

    def recall(
        self, principal: Principal, observations: Observations, run_id: str, k: int = 3
    ) -> list[MemoryCandidate]:
        hits = [
            m.candidate
            for m in self.memories.values()
            if m.tenant_id == principal.tenant_id
            and principal.team_id in m.readable_by
            and m.candidate.expires_at > utc_now()
            and (observations.error_code is None or m.error_code == observations.error_code)
        ]
        return [c.model_copy(update={"rank": i + 1}) for i, c in enumerate(hits[:k])]

    def record_use(
        self,
        principal: Principal,
        memory_id: str,
        version: int,
        run_id: str,
        decision: MemoryUseDecision,
    ) -> MemoryOutcome | None:
        """Same outcomes as AtlasMemoryStore.record_use (no expiry arithmetic, no audit trail)."""
        self.uses.append(
            {
                "team_id": principal.team_id,
                "memory_id": memory_id,
                "version": version,
                "run_id": run_id,
                "decision": decision.decision,
            }
        )
        if decision.decision in ("rejected", "stale"):
            return "near_miss"
        v = decision.verification
        if v is None or v.status == "inconclusive":
            return None
        if v.verified:
            return "renewed"
        held = bool(decision.preconditions) and all(r.held is True for r in decision.preconditions)
        if held and memory_id in self.memories:
            self.memories.pop(memory_id)  # disputed: no longer recalled
            return "disputed"
        return None

    def promote(self, principal: Principal, draft: MemoryDraft, verification: VerificationResult) -> str:
        if not verification.verified:
            raise ValueError("Memory refused: no proof.")
        memory_id = f"mem_{draft.incident_id}"
        if memory_id in self.memories:  # idempotent
            return memory_id
        candidate = MemoryCandidate(
            memory_id=memory_id,
            version=1,
            owner_team_id=principal.team_id,
            repository_id=draft.repository_id,
            rank=1,
            score=1.0,
            match="strong",
            source="vector",
            retrieval_text=draft.retrieval_text,
            confirmed_cause=draft.confirmed_cause,
            resolution_summary=draft.resolution_summary,
            resolution_patch=draft.patch,
            applicability=draft.applicability,
            anchors=draft.anchors,
            expires_at=utc_now() + timedelta(hours=24),
        )
        self.memories[memory_id] = _FakeMemory(
            candidate, principal.tenant_id, [principal.team_id], draft.signature.get("errorCode")
        )
        return memory_id

    def is_searchable(self, principal: Principal, memory_id: str) -> bool:
        m = self.memories.get(memory_id)
        return bool(m and principal.team_id in m.readable_by)


@dataclass
class FakeRunner:
    """Canned Runner. The bug always reproduces. A patch to an allowlisted file passes the
    duplicate-handling tests if it catches DuplicateKeyError, and the reconciliation test only if it
    also calls ledger.mark_replayed (the team convention that memory carries)."""

    patchable_files: tuple[str, ...] = ("app/webhooks.py",)

    def reproduce(self, case_id: str) -> VerificationResult:
        return VerificationResult(
            run_id=new_id("verify"),
            case_id=case_id,
            status="failed",
            before_failed=True,
            after_passed=False,
            tests=[
                TestOutcome(
                    name="test_duplicate_event_reproduces",
                    passed=False,
                    detail="DuplicateKeyError: E11000 duplicate key error",
                )
            ],
            evidence_hashes=[sha256_text(f"repro:{case_id}")],
        )

    def verify(self, case_id: str, patch: FilePatch) -> VerificationResult:
        allowed = patch.path in self.patchable_files
        handles_duplicate = allowed and "DuplicateKeyError" in patch.new_content
        records_replay = handles_duplicate and "mark_replayed" in patch.new_content
        tests: list[TestOutcome] = []
        for name in TRUSTED_TESTS:
            passed = records_replay if name == "test_replay_recorded_for_reconciliation" else handles_duplicate
            detail = None
            if not passed and name == "test_replay_recorded_for_reconciliation":
                detail = "AssertionError: expected the replayed event to be recorded exactly once, got 0"
            tests.append(TestOutcome(name=name, passed=passed, detail=detail))
        all_passed = all(t.passed for t in tests)
        return VerificationResult(
            run_id=new_id("verify"),
            case_id=case_id,
            status="passed" if all_passed else "failed",
            before_failed=True,
            after_passed=all_passed,
            tests=tests,
            evidence_hashes=[sha256_text(f"verify:{case_id}:{patch.new_content}")],
            detail=None if allowed else f"{patch.path} is not an allowlisted file",
        )
