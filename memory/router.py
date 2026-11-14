"""Memory REST endpoints (P2-4 to P2-7): cards, search, Fence comparison, forget, expire, correct, history.

Mounted by api/main.py. Every route is scoped to the caller's team; admin routes need memory_admin.
Route order matters: /memories/search and /memories/compare-unscoped must stay above /memories/{memory_id}.
"""

from __future__ import annotations

from functools import lru_cache

from fastapi import APIRouter, HTTPException, status

from contracts.models import CorrectBody, MemoryCard, MemorySearchResult, ReasonBody
from core.auth import AdminPrincipal, CurrentPrincipal
from memory.store import AtlasMemoryStore

router = APIRouter(prefix="/memories", tags=["memory"])


@lru_cache(maxsize=1)
def store() -> AtlasMemoryStore:
    return AtlasMemoryStore()


@router.get("", response_model=list[MemoryCard])
def list_memories(principal: CurrentPrincipal) -> list[MemoryCard]:
    """Memories the caller's team may read (any status, so expired ones show as expired)."""
    return store().list_cards(principal)


@router.get("/search", response_model=MemorySearchResult)
def search_memories(q: str, principal: CurrentPrincipal) -> MemorySearchResult:
    """The same scoped search as recall, for the caller's team (metadata-only cards).
    `filter` is the exact pre-filter that ran inside $vectorSearch, printed in the Fence view."""
    s = store()
    cards = s.search(principal, q)
    return MemorySearchResult(query=q, team_id=principal.team_id, count=len(cards), memories=cards,
                              filter=s.printable_scope(principal))


@router.get("/refusals")
def recent_refusals(principal: CurrentPrincipal, limit: int = 5) -> list[dict]:
    """Writes Atlas refused for the caller's team, newest first (R11, "Memory refused: no proof").
    Facts only: run, case, failing test names. Nothing was stored, so there is no content."""
    return store().refusals(principal, min(max(limit, 1), 20))


@router.get("/compare-unscoped", response_model=MemorySearchResult)
def compare_unscoped(q: str, principal: AdminPrincipal) -> MemorySearchResult:
    """Admin only, for the Fence view: what the search WOULD return without the team filter.
    Other teams' memories come back redacted (owner and match only). Never given to the agent."""
    s = store()
    cards = s.unscoped_cards(principal, q)
    shown = {k: v for k, v in s.printable_scope(principal).items() if k != "readableBy"}
    return MemorySearchResult(query=q, team_id=principal.team_id, count=len(cards), memories=cards, filter=shown)


@router.get("/{memory_id}", response_model=MemoryCard)
def get_memory(memory_id: str, principal: CurrentPrincipal) -> MemoryCard:
    card = store().get_card(principal, memory_id)
    if card is None:  # same answer for "missing" and "not your team", so ids can't be probed
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No memory with that id for your team.")
    return card


@router.get("/{memory_id}/stale")
def memory_stale(memory_id: str, principal: CurrentPrincipal) -> dict:
    """R12: has the code changed since this memory was proven? {stale, changedFiles}. Not audited,
    so the card can poll it."""
    result = store().staleness(principal, memory_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No memory with that id for your team.")
    return result


@router.get("/{memory_id}/audit")
def memory_audit(memory_id: str, principal: AdminPrincipal) -> list[dict]:
    """Who read, used, changed or deleted this memory: every audit event of its lineage, oldest first.
    Admin of the owner team; still readable after Forget (tombstones never contain content)."""
    return _admin(lambda: store().history(principal, memory_id))


@router.post("/{memory_id}/correct", response_model=MemoryCard)
def correct_memory(memory_id: str, body: CorrectBody, principal: AdminPrincipal) -> MemoryCard:
    """Version 2 with narrowed `excludes` supersedes version 1; both stay in the history. Returns v2."""
    return _admin(lambda: store().correct(principal, memory_id, body.excludes, body.reason))


@router.post("/{memory_id}/expire", response_model=MemoryCard)
def expire_memory(memory_id: str, body: ReasonBody, principal: AdminPrincipal) -> MemoryCard:
    """Expire now (admin of the owner team, reason required). Recall stops returning it immediately."""
    return _admin(lambda: store().expire_now(principal, memory_id, body.reason))


@router.delete("/{memory_id}", response_model=MemoryCard)
def forget_memory(memory_id: str, body: ReasonBody, principal: AdminPrincipal) -> MemoryCard:
    """Forget: hard delete of every version plus a content-free tombstone (admin of the owner team,
    reason required). Returns the grey "Forgotten" card (content erased)."""
    return _admin(lambda: store().forget(principal, memory_id, body.reason))


def _admin(action):
    try:
        return action()
    except LookupError:  # same answer as "doesn't exist", so other teams can't probe ids
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No memory with that id for your team.") from None
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e)) from None
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from None
