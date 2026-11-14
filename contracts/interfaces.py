"""What each side promises to provide.

P2 implements MemoryStore (memory/store.py). P3 implements Runner (runner/sandbox.py).
P1's agent depends only on these interfaces, so the fakes in contracts/fakes.py can stand in
until the real implementations land.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from contracts.models import (
    FilePatch,
    MemoryCandidate,
    MemoryDraft,
    MemoryOutcome,
    MemoryUseDecision,
    Observations,
    Principal,
    VerificationResult,
)


@runtime_checkable
class MemoryStore(Protocol):
    """Provided by P2, used by P1."""

    def recall(
        self, principal: Principal, observations: Observations, run_id: str, k: int = 3
    ) -> list[MemoryCandidate]:
        """Return at most k memories the principal's team may read right now.

        Must: pre-filter inside $vectorSearch (tenant, readableBy, status=active, expiresAt>now,
        embeddingVersion), merge an exact signature lookup, re-read every hit with the same scope
        (drop and audit index lag), and write a `retrieved` audit event per returned memory.
        """
        ...

    def record_use(
        self,
        principal: Principal,
        memory_id: str,
        version: int,
        run_id: str,
        decision: MemoryUseDecision,
    ) -> MemoryOutcome | None:
        """Record what the agent did with a memory. The store decides the governance outcome and returns it:
        used + verified -> "renewed"; used + preconditions held + verification failed -> "disputed";
        rejected because preconditions were false -> "near_miss"; nothing changed -> None."""
        ...

    def promote(self, principal: Principal, draft: MemoryDraft, verification: VerificationResult) -> str:
        """Create a memory from a verified fix and return its id. Must refuse when
        `verification.verified` is False. Safe to call twice for the same incident and revision."""
        ...

    def is_searchable(self, principal: Principal, memory_id: str) -> bool:
        """True once vector search can return this memory for this principal (index lag probe)."""
        ...


@runtime_checkable
class Runner(Protocol):
    """Provided by P3, used by P1."""

    def reproduce(self, case_id: str) -> VerificationResult:
        """Run the reproduction test on the ORIGINAL code in a fresh temporary copy."""
        ...

    def verify(self, case_id: str, patch: FilePatch) -> VerificationResult:
        """Reproduce on the original, then apply `patch` (allowlisted file only) to a fresh copy and
        run every trusted test with no secrets in the environment."""
        ...
