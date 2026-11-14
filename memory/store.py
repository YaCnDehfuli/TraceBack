"""AtlasMemoryStore: the real MemoryStore (P2-2, P2-6). Stub until then; use contracts.fakes.FakeMemoryStore.

Rules it must keep (team guide section 8, plan 4.4 and 4.5):
- recall: $vectorSearch pre-filter on tenantId, readableBy, status="active", expiresAt > now,
  embeddingVersion; exact signature lookup merged in; minimum score cutoff; re-read guard; audit
  `retrieved` / `index_lag_dropped`.
- promote: refuse unless verification.verified; the $jsonSchema validator refuses it too
  ("Memory refused: no proof."); idempotent per (tenant, incident, revision, version).
- forget: hard delete plus tombstone; audit hashes use a per-memory HMAC secret stored in the memory.
"""

from __future__ import annotations

from contracts.models import (
    MemoryCandidate,
    MemoryDraft,
    MemoryUseDecision,
    Observations,
    Principal,
    VerificationResult,
)


class AtlasMemoryStore:
    def recall(
        self, principal: Principal, observations: Observations, run_id: str, k: int = 3
    ) -> list[MemoryCandidate]:
        raise NotImplementedError("P2-2: recall")

    def record_use(
        self,
        principal: Principal,
        memory_id: str,
        version: int,
        run_id: str,
        decision: MemoryUseDecision,
    ) -> None:
        raise NotImplementedError("P2-6: record_use")

    def promote(self, principal: Principal, draft: MemoryDraft, verification: VerificationResult) -> str:
        raise NotImplementedError("P2-2: promote")

    def is_searchable(self, principal: Principal, memory_id: str) -> bool:
        raise NotImplementedError("P2-2: is_searchable")
