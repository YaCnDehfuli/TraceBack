"""AtlasMemoryStore: the real MemoryStore (contracts/interfaces.py). The only code that writes memories.

Done (P2-2): promote, is_searchable, recall, search, unscoped_search.
Still to do: record_use, forget, expire (P2-6); correct (P2-7).

Rules it keeps (team guide section 8, plan 4.4 and 4.5):
- recall: $vectorSearch pre-filter on tenantId, readableBy, status="active", expiresAt > now,
  embeddingVersion; exact signature lookup merged in; minimum score cutoff; re-read guard; audit
  `retrieved` / `index_lag_dropped`.
- promote: the Atlas $jsonSchema validator is the gate. It refuses any memory whose verification is
  not status="passed", beforeFailed=true, afterPassed=true (the same rule as VerificationResult.verified).
  There is deliberately no Python pre-check, so a poisoned run's write is refused by the database
  itself and the demo can show it. Idempotent per (tenant, incident, revision, version).
- forget: hard delete of every version plus tombstone; audit hashes use a per-memory HMAC secret
  stored in the memory, so they die with it.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from typing import Any

from pymongo.database import Database
from pymongo.errors import DuplicateKeyError, WriteError

from contracts.models import (
    Applicability,
    FileAnchor,
    FilePatch,
    MemoryCandidate,
    MemoryCard,
    MemoryDraft,
    MemoryUseDecision,
    Observations,
    Principal,
    Proof,
    VerificationResult,
)
from core.clock import new_id, utc_now
from core.config import get_settings
from core.db import Collections, get_db

from . import audit
from .config import EMBEDDING_VERSION, MIN_SCORE, VECTOR_INDEX
from .embeddings import embed_one
from .policy import expiry_for, get_policy

NUM_CANDIDATES = 100
VECTOR_LIMIT = 5
STRONG_MATCH = 0.80  # display only: "match: strong/weak", never a raw score on screen
HIDDEN = {"embedding": 0}  # hmacSecret is read for audit hashes, then stripped before returning


class MemoryRefused(Exception):
    """Atlas's validator rejected the write: the fix has no passing proof."""

    MESSAGE = "Memory refused: no proof."

    def __init__(self, detail: str = ""):
        super().__init__(self.MESSAGE)
        self.detail = detail


def _actor(p: Principal) -> dict:
    return {"type": "human", "id": f"{p.role}@{p.team_id}"}


class AtlasMemoryStore:
    def __init__(self, db: Database | None = None):
        self.db = db if db is not None else get_db()
        self.memories = self.db[Collections.MEMORIES]

    @staticmethod
    def scope(p: Principal, now: datetime) -> dict:
        """The team filter. Runs inside $vectorSearch and again in the re-read guard."""
        return {
            "tenantId": p.tenant_id,
            "readableBy": {"$in": [p.team_id]},
            "status": "active",
            "expiresAt": {"$gt": now},
            "embeddingVersion": EMBEDDING_VERSION,
        }

    # ------------------------------------------------------------------ write

    def promote(
        self,
        principal: Principal,
        draft: MemoryDraft,
        verification: VerificationResult,
        *,
        title: str | None = None,
        seeded: bool = False,
        expires_in_seconds: int | None = None,
    ) -> str:
        """Turn a verified fix into a memory and return its id. Raises MemoryRefused if Atlas refuses it.

        `seeded` and `expires_in_seconds` are for scripts/seed_demo.py only (labelled seeded data,
        the 90-second canary). The agent never passes them.
        """
        p, d, v = principal, draft, verification
        key = {
            "tenantId": p.tenant_id,
            "provenance.sourceIncidentId": d.incident_id,
            "provenance.sourceRevision": d.source_revision,
            "version": 1,
        }
        existing = self.memories.find_one(key, {"_id": 1})
        if existing:
            return existing["_id"]

        now = utc_now()
        policy = get_policy(self.db, p.tenant_id, p.team_id)
        expires_at, purge_at = expiry_for(policy, now, now)
        if expires_in_seconds is not None:
            expires_at = now + timedelta(seconds=expires_in_seconds)
            purge_at = expires_at + timedelta(seconds=policy["purgeGraceSeconds"])

        mem_id = new_id("mem")
        s = get_settings()
        doc: dict[str, Any] = {
            "_id": mem_id,
            "lineageId": mem_id,
            "version": 1,
            "supersedes": None,
            "tenantId": p.tenant_id,
            "ownerTeamId": p.team_id,
            "readableBy": [p.team_id],
            "repositoryId": d.repository_id,
            "status": "active",
            "title": title or d.retrieval_text.split(";")[0].split(".")[0][:80],
            "retrievalText": d.retrieval_text,
            "signature": d.signature,
            "confirmedCause": d.confirmed_cause,
            "applicability": d.applicability.model_dump(by_alias=True),
            "anchors": [a.model_dump(by_alias=True) for a in d.anchors],
            "resolution": {"summary": d.resolution_summary, "patch": d.patch.model_dump(by_alias=True)},
            "provenance": {
                "sourceIncidentId": d.incident_id,
                "sourceRevision": d.source_revision,
                "createdBy": f"run:{v.run_id}",
                "promotedBy": "policy:verify-gate",
                "policyVersion": policy["policyVersion"],
            },
            # Passed through exactly as the runner reported it; the validator judges it.
            "verification": {
                "runId": v.run_id,
                "caseId": v.case_id,
                "status": v.status,
                "environment": "seeded" if seeded else "controlled-fixture",
                "beforeFailed": v.before_failed,
                "afterPassed": v.after_passed,
                "tests": [t.name for t in v.tests if t.passed],
                "testsTotal": len(v.tests),
                "evidenceHashes": v.evidence_hashes,
            },
            "seeded": seeded,
            "expiresAt": expires_at,
            "purgeAt": purge_at,
            "embeddingModel": s.embedding_model,
            "embeddingDimensions": s.embedding_dimensions,
            "embeddingVersion": EMBEDDING_VERSION,
            "embedding": embed_one(d.retrieval_text, "document"),
            "hmacSecret": secrets.token_hex(32),
            "createdAt": now,
        }

        actor = {"type": "policy", "id": "verify-gate"}
        try:
            self.memories.insert_one(doc)
        except DuplicateKeyError:
            return self.memories.find_one(key, {"_id": 1})["_id"]
        except WriteError as e:
            if e.code != 121:  # 121 = DocumentValidationFailure
                raise
            audit.log(
                self.db, tenant_id=p.tenant_id, event="refused", actor=actor, run_id=v.run_id,
                reason="no proof: verification must be passed, failed before and passed after",
                details={"status": v.status, "beforeFailed": v.before_failed, "afterPassed": v.after_passed},
            )
            raise MemoryRefused(str(e.details)) from e

        audit.log(
            self.db, tenant_id=p.tenant_id, event="promoted", actor=actor, memory_id=mem_id, version=1,
            run_id=v.run_id, content_hash=audit.content_hash(doc),
            details={"expiresAt": doc["expiresAt"], "purgeAt": doc["purgeAt"], "seeded": seeded},
        )
        return mem_id

    def record_use(
        self, principal: Principal, memory_id: str, version: int, run_id: str, decision: MemoryUseDecision
    ) -> None:
        raise NotImplementedError("P2-6: record_use")

    # ------------------------------------------------------------------ read

    def _vector(self, query_vector: list[float], filt: dict, limit: int = VECTOR_LIMIT) -> list[dict]:
        return list(self.memories.aggregate([
            {"$vectorSearch": {"index": VECTOR_INDEX, "path": "embedding", "queryVector": query_vector,
                               "numCandidates": NUM_CANDIDATES, "limit": limit, "filter": filt}},
            {"$project": {"_id": 1, "ownerTeamId": 1, "score": {"$meta": "vectorSearchScore"}}},
        ]))

    def is_searchable(self, principal: Principal, memory_id: str) -> bool:
        """True once the vector index returns this memory for this principal (index lag probe)."""
        doc = self.memories.find_one({"_id": memory_id}, {"embedding": 1})
        if not doc:
            return False
        hits = self._vector(doc["embedding"], self.scope(principal, utc_now()), limit=10)
        return any(h["_id"] == memory_id for h in hits)

    def _find(self, p: Principal, text: str, signature: dict | None, actor: dict,
              run_id: str | None, k: int, repo: str | None) -> list[dict]:
        """Scoped vector + signature search, re-read guard, audit. Returns raw docs (no vector, no secret)."""
        scope = self.scope(p, utc_now())
        scores: dict[str, float] = {}
        sources: dict[str, set[str]] = {}

        for h in self._vector(embed_one(text, "query"), scope):
            if h["score"] >= MIN_SCORE:
                scores[h["_id"]] = h["score"]
                sources.setdefault(h["_id"], set()).add("vector")

        # Exact signature lookup. Bypasses the score cutoff, so a look-alike (case C) still
        # surfaces and is then refused by its conditions.
        if signature and signature.get("errorCode"):
            sig = {"signature.errorCode": str(signature["errorCode"])}
            if signature.get("operation"):
                sig["signature.operation"] = signature["operation"]
            for doc in self.memories.find({**scope, **sig}, {"_id": 1}).limit(VECTOR_LIMIT):
                scores.setdefault(doc["_id"], 0.0)
                sources.setdefault(doc["_id"], set()).add("signature")

        if not scores:
            return []

        # Re-read guard: only what is still allowed right now (protects against index lag).
        live = {doc["_id"]: doc for doc in self.memories.find({"_id": {"$in": list(scores)}, **scope}, HIDDEN)}
        dropped = [i for i in scores if i not in live]
        ranked = sorted(live.values(), key=lambda doc: (doc.get("repositoryId") != repo, -scores[doc["_id"]]))[:k]

        base = {"tenantId": p.tenant_id, "actor": actor, "runId": run_id, "reason": None}
        events = [{**base, "memoryId": i, "version": None, "event": "index_lag_dropped", "details": {},
                   "contentHash": None} for i in dropped]
        for rank, doc in enumerate(ranked, 1):
            src = sources[doc["_id"]]
            events.append({**base, "memoryId": doc["_id"], "version": doc["version"], "event": "retrieved",
                           "details": {"rank": rank, "score": scores[doc["_id"]], "sources": sorted(src)},
                           "contentHash": audit.content_hash(doc)})
            doc.pop("hmacSecret", None)
            doc["_rank"] = rank
            doc["_score"] = scores[doc["_id"]]
            doc["_source"] = "vector" if "vector" in src else "signature"
            doc["_match"] = "strong" if scores[doc["_id"]] >= STRONG_MATCH or "signature" in src else "weak"
        audit.log_many(self.db, events)
        return ranked

    def recall(
        self, principal: Principal, observations: Observations, run_id: str, k: int = 3
    ) -> list[MemoryCandidate]:
        o = observations
        signature = {"errorCode": o.error_code, "operation": o.operation}
        docs = self._find(principal, o.summary, signature, {"type": "agent", "id": f"run:{run_id}"},
                          run_id, k, o.repository_id)
        return [self.to_candidate(doc) for doc in docs]

    def search(self, principal: Principal, q: str, k: int = 5) -> list[MemoryCard]:
        """GET /memories/search (UI and voice agent): the same scope as recall, metadata-only cards."""
        docs = self._find(principal, q, None, _actor(principal), None, k, None)
        return [self.to_card(doc) for doc in docs]

    def unscoped_search(self, principal: Principal, q: str, k: int = 5) -> list[dict]:
        """Fence comparison only: the same search WITHOUT tenantId/readableBy. Admin only, never given
        to the agent or the voice agent. Returns id, owner team and score only, never content."""
        filt = {"status": "active", "expiresAt": {"$gt": utc_now()}, "embeddingVersion": EMBEDDING_VERSION}
        hits = [h for h in self._vector(embed_one(q, "query"), filt, limit=k) if h["score"] >= MIN_SCORE]
        audit.log(self.db, tenant_id=principal.tenant_id, event="unscoped_compared", actor=_actor(principal),
                  details={"memoryIds": [h["_id"] for h in hits]})
        return hits

    # ------------------------------------------------------------------ cards (UI)

    @staticmethod
    def readable(p: Principal) -> dict:
        """Who may SEE a memory's card: same tenant and team in readableBy, any status or expiry,
        so the UI can show expired / superseded states. Searching still uses scope()."""
        return {"tenantId": p.tenant_id, "readableBy": {"$in": [p.team_id]}}

    def list_cards(self, principal: Principal, limit: int = 20) -> list[MemoryCard]:
        """GET /memories: the caller's team's memories, earned ones first, then seeded."""
        docs = list(
            self.memories.find(self.readable(principal), {"embedding": 0, "hmacSecret": 0})
            .sort([("seeded", 1), ("createdAt", -1)])
            .limit(limit)
        )
        if docs:
            audit.log(self.db, tenant_id=principal.tenant_id, event="listed", actor=_actor(principal),
                      details={"memoryIds": [d["_id"] for d in docs]})
        return [self.to_card(d) for d in docs]

    def get_card(self, principal: Principal, memory_id: str) -> MemoryCard | None:
        """GET /memories/{id}. None if missing OR not readable, so other teams can't probe for ids."""
        doc = self.memories.find_one({"_id": memory_id, **self.readable(principal)}, {"embedding": 0})
        if not doc:
            return None
        audit.log(self.db, tenant_id=principal.tenant_id, event="viewed", actor=_actor(principal),
                  memory_id=memory_id, version=doc["version"], content_hash=audit.content_hash(doc))
        return self.to_card(doc)

    # ------------------------------------------------------------------ shapes

    @staticmethod
    def to_candidate(doc: dict) -> MemoryCandidate:
        res = doc.get("resolution", {})
        return MemoryCandidate(
            memory_id=doc["_id"],
            version=doc["version"],
            owner_team_id=doc["ownerTeamId"],
            repository_id=doc["repositoryId"],
            rank=doc["_rank"],
            score=doc["_score"],
            match=doc["_match"],
            source=doc["_source"],
            retrieval_text=doc["retrievalText"],
            confirmed_cause=doc.get("confirmedCause") or "",
            resolution_summary=res.get("summary") or "",
            resolution_patch=FilePatch.model_validate(res["patch"]) if res.get("patch") else None,
            applicability=Applicability.model_validate(doc.get("applicability") or {}),
            anchors=[FileAnchor.model_validate(a) for a in doc.get("anchors", [])],
            expires_at=doc["expiresAt"],
        )

    @staticmethod
    def to_card(doc: dict) -> MemoryCard:
        v = doc["verification"]
        return MemoryCard(
            memory_id=doc["_id"],
            version=doc["version"],
            title=doc.get("title") or "",
            owner_team_id=doc["ownerTeamId"],
            readable_by=doc["readableBy"],
            status=doc["status"],
            created_at=doc["createdAt"],
            expires_at=doc["expiresAt"],
            purge_at=doc["purgeAt"],
            proof=Proof(before_failed=v["beforeFailed"], after_passed=v["afterPassed"],
                        tests_total=v.get("testsTotal", 0), verification_run_id=v["runId"]),
            applicability=Applicability.model_validate(doc.get("applicability") or {}),
            seeded=doc.get("seeded", False),
            match=doc.get("_match"),
        )
