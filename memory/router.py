"""Memory REST endpoints (P2-5, P2-6, P2-7). Stubs return 501 until implemented.

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


def _todo(item: str) -> HTTPException:
    return HTTPException(status.HTTP_501_NOT_IMPLEMENTED, f"Not implemented yet ({item}).")


@router.get("", response_model=list[MemoryCard])
def list_memories(principal: CurrentPrincipal) -> list[MemoryCard]:
    """Memories the caller's team may read (any status, so expired ones show as expired)."""
    return store().list_cards(principal)


@router.get("/search", response_model=MemorySearchResult)
def search_memories(q: str, principal: CurrentPrincipal) -> MemorySearchResult:
    """The same scoped search as recall, for the caller's team. Also used by the voice agent (metadata only)."""
    raise _todo("P2-5")


@router.get("/compare-unscoped", response_model=MemorySearchResult)
def compare_unscoped(q: str, principal: AdminPrincipal) -> MemorySearchResult:
    """Admin only, for the Fence view: what the search WOULD return without the team filter.
    Never given to the agent or the voice agent."""
    raise _todo("P2-5")


@router.get("/{memory_id}", response_model=MemoryCard)
def get_memory(memory_id: str, principal: CurrentPrincipal) -> MemoryCard:
    card = store().get_card(principal, memory_id)
    if card is None:  # same answer for "missing" and "not your team", so ids can't be probed
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No memory with that id for your team.")
    return card


@router.get("/{memory_id}/audit")
def memory_audit(memory_id: str, principal: AdminPrincipal) -> list[dict]:
    """Who read, used, changed or deleted this memory."""
    raise _todo("P2-7")


@router.post("/{memory_id}/correct", response_model=MemoryCard)
def correct_memory(memory_id: str, body: CorrectBody, principal: AdminPrincipal) -> MemoryCard:
    """Version 2 with narrowed `excludes` supersedes version 1; both stay in the history."""
    raise _todo("P2-7")


@router.post("/{memory_id}/expire", response_model=MemoryCard)
def expire_memory(memory_id: str, body: ReasonBody, principal: AdminPrincipal) -> MemoryCard:
    raise _todo("P2-6")


@router.delete("/{memory_id}", response_model=MemoryCard)
def forget_memory(memory_id: str, body: ReasonBody, principal: AdminPrincipal) -> MemoryCard:
    """Forget: hard delete plus tombstone. Returns the grey "Forgotten" card (content erased)."""
    raise _todo("P2-6")
