"""AtlasMemoryStore: the real MemoryStore (contracts/interfaces.py). The only code that writes memories.

Done: promote, is_searchable, recall, search, unscoped_search (P2-2, P2-5); record_use, forget,
expire_now (P2-6); correct, history (P2-7); staleness (P2-10).

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

import re
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
    MemoryOutcome,
    MemoryUseDecision,
    Observations,
    Principal,
    Proof,
    Tombstone,
    VerificationResult,
)
from core.clock import new_id, utc_now
from core.config import get_settings
from core.db import Collections, get_db

from . import audit
from .config import EMBEDDING_VERSION, MIN_SCORE, VECTOR_INDEX
from .embeddings import embed_one
from .policy import expiry_for, get_policy
from .staleness import changed_files, proven_against

NUM_CANDIDATES = 100
VECTOR_LIMIT = 5
# "match: strong/weak" (shown instead of a raw score) comes from the VECTOR score only (#55): an exact
# signature hit (same error code + operation) still surfaces a look-alike so its conditions can refuse it,
# but it no longer implies strong similarity. Measured with P1's code-derived recall text (add769c), Atlas
# scores = (1 + cosine) / 2: true repeats A/B/B2/B3/P 0.952; look-alikes D 0.939, C 0.927; best distractor 0.778.
STRONG_MATCH = 0.945


def match_label(vector_score: float | None) -> str:
    return "strong" if (vector_score or 0.0) >= STRONG_MATCH else "weak"
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
            # Describe the FIX, not the symptom (issue #17): first clause of the resolution.
            "title": title or re.split(r"[:;.]", d.resolution_summary or d.retrieval_text)[0].strip()[:80],
            "retrievalText": d.retrieval_text,
            "signature": d.signature,
            "confirmedCause": d.confirmed_cause,
            "applicability": d.applicability.model_dump(by_alias=True),
            "anchors": [a.model_dump(by_alias=True) for a in d.anchors],
            # R12: fingerprints of the touched files as they are now, i.e. the code this fix was proven on.
            "provenAgainst": proven_against(d.repository_id, [a.path for a in d.anchors] or [d.patch.path]),
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
                # Facts for the refusal receipt (R11). Test names only, never memory content.
                details={"status": v.status, "beforeFailed": v.before_failed, "afterPassed": v.after_passed,
                         "teamId": p.team_id, "caseId": v.case_id, "repositoryId": d.repository_id,
                         "testsPassed": v.tests_passed, "testsTotal": len(v.tests),
                         "failedTests": [t.name for t in v.tests if not t.passed]},
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
    ) -> MemoryOutcome | None:
        """Record what the agent did with a recalled memory. The store decides the governance outcome
        (guide 8.4); the agent never does. Returns that outcome for the run's memory_outcome event:

          rejected / stale                                  -> "near_miss" (memory stays active)
          used, no verification yet                         -> None   (audit "used")
          used, verified                                    -> "renewed" (expiry extended, capped)
          used, conditions all held, verification failed    -> "disputed" (paused: not searchable)
          used, verification inconclusive (our infra broke) -> None   (nothing blamed on the memory)

        Never raises for a memory that vanished mid-run (forgotten, expired, other team): it logs
        `use_ignored` and returns None, so a run is never crashed by governance.
        """
        p, d = principal, decision
        actor = {"type": "agent", "id": f"run:{run_id}"}
        details: dict[str, Any] = {
            "decision": d.decision,
            "preconditions": [r.model_dump(by_alias=True) for r in d.preconditions],
        }
        if d.verification is not None:
            v = d.verification
            details["verification"] = {"runId": v.run_id, "status": v.status, "testsPassed": v.tests_passed,
                                       "testsTotal": len(v.tests)}

        doc = self.memories.find_one({"_id": memory_id, **self.readable(p)}, {"embedding": 0})
        if doc is None:
            audit.log(self.db, tenant_id=p.tenant_id, event="use_ignored", actor=actor, memory_id=memory_id,
                      version=version, run_id=run_id, reason="memory no longer readable", details=details)
            return None

        def log(event: str, reason: str | None = d.reason, extra: dict | None = None) -> None:
            audit.log(self.db, tenant_id=p.tenant_id, event=event, actor=actor, memory_id=memory_id,
                      version=doc["version"], run_id=run_id, reason=reason,
                      details={**details, **(extra or {})}, content_hash=audit.content_hash(doc))

        # Not applied: its conditions didn't hold here (or it was stale). Not the memory's fault.
        if d.decision in ("rejected", "stale"):
            log("near_miss")
            return "near_miss"

        # decision == "used"
        if d.verification is None or d.verification.status == "inconclusive":
            log("used")
            return None

        if d.verification.verified:
            log("used")
            policy = get_policy(self.db, doc["tenantId"], doc["ownerTeamId"])
            if not policy["renewOnReverify"]:
                return None
            now = utc_now()
            new_exp, new_purge = expiry_for(policy, doc["createdAt"], now)
            # Only a memory that is STILL active and unexpired is renewed, checked atomically in the
            # update: a run in flight must never undo an admin's "expire now", a dispute or a revoke.
            res = self.memories.update_one(
                {"_id": memory_id, "status": "active", "expiresAt": {"$gt": now, "$lt": new_exp}},
                {"$set": {"expiresAt": new_exp, "purgeAt": new_purge}},
            )
            if res.modified_count:
                log("renewed", extra={"from": doc["expiresAt"], "expiresAt": new_exp, "purgeAt": new_purge})
                return "renewed"
            live = self.memories.find_one({"_id": memory_id, "status": "active", "expiresAt": {"$gt": now}},
                                          {"_id": 1})
            if live:  # still valid, already at its max lifetime: nothing to extend
                log("renewed", extra={"expiresAt": doc["expiresAt"], "capped": True})
                return "renewed"
            log("not_renewed", reason="expired, disputed or revoked while the run was in flight")
            return None

        # Applied and verification failed.
        held = bool(d.preconditions) and all(r.held is True for r in d.preconditions)
        if not held:
            # Conditions weren't all confirmed, so the failure isn't evidence against the memory.
            log("used", extra={"verificationFailed": True})
            return None
        res = self.memories.update_one({"_id": memory_id, "status": "active"}, {"$set": {"status": "disputed"}})
        if not res.modified_count:  # already disputed / revoked / superseded by someone else
            log("used", extra={"verificationFailed": True, "statusAlready": doc["status"]})
            return None
        log("disputed", reason=d.reason or "conditions held but the remembered fix failed verification")
        return "disputed"

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

        vector_scores: dict[str, float] = {}  # every vector hit, also those below the cutoff (for labels)
        for h in self._vector(embed_one(text, "query"), scope):
            vector_scores[h["_id"]] = h["score"]
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
                scores.setdefault(doc["_id"], vector_scores.get(doc["_id"], 0.0))  # its real similarity
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
            doc["_match"] = match_label(scores[doc["_id"]])  # similarity only; a signature hit is not "strong"
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
        """Fence comparison only: the same search WITHOUT the team filter (readableBy). The tenant filter
        stays, so it can never reach another company. Admin only, never given to the agent.
        Returns id, owner team and score only, never content."""
        filt = {"tenantId": principal.tenant_id, "status": "active", "expiresAt": {"$gt": utc_now()},
                "embeddingVersion": EMBEDDING_VERSION}
        hits = [h for h in self._vector(embed_one(q, "query"), filt, limit=k) if h["score"] >= MIN_SCORE]
        audit.log(self.db, tenant_id=principal.tenant_id, event="unscoped_compared", actor=_actor(principal),
                  details={"memoryIds": [h["_id"] for h in hits]})
        return hits

    def unscoped_cards(self, principal: Principal, q: str, k: int = 5) -> list[MemoryCard]:
        """unscoped_search as cards. Memories the caller's team may NOT read are redacted: owner, status
        and match only, no title or conditions, so the comparison itself leaks nothing."""
        hits = self.unscoped_search(principal, q, k)
        docs = {d["_id"]: d for d in self.memories.find({"_id": {"$in": [h["_id"] for h in hits]}},
                                                         {"embedding": 0, "hmacSecret": 0})}
        cards = []
        for h in hits:
            doc = docs.get(h["_id"])
            if doc is None:  # deleted since the index saw it
                continue
            doc["_match"] = match_label(h["score"])
            card = self.to_card(doc)
            if principal.team_id not in doc["readableBy"]:
                owner = doc["ownerTeamId"].removeprefix("team-").capitalize()
                card = card.model_copy(update={"title": f"Hidden: a {owner} memory", "applicability": Applicability(),
                                               "readable_by": [doc["ownerTeamId"]]})
            cards.append(card)
        return cards

    # ------------------------------------------------------------------ admin lifecycle (P2-6)

    def _owned(self, p: Principal, memory_id: str) -> dict:
        """The memory, if the caller's team may read it AND owns it. Raises LookupError (-> 404) when the
        team can't even see it, PermissionError (-> 403) when it can see it but doesn't own it."""
        doc = self.memories.find_one({"_id": memory_id, **self.readable(p)}, {"embedding": 0})
        if doc is None:
            raise LookupError(memory_id)
        if doc["ownerTeamId"] != p.team_id:
            raise PermissionError("only an admin of the owner team can do this")
        return doc

    def forget(self, principal: Principal, memory_id: str, reason: str) -> MemoryCard:
        """Forget for good: hard-delete EVERY version of this memory (a superseded v1 still holds the
        text) and leave a tombstone in the audit log with no content: who, why, when, which versions.
        The per-memory HMAC secret is deleted with the documents, so earlier audit hashes can no longer
        be linked to any content. Returns the grey "Forgotten" card."""
        if not reason or not reason.strip():
            raise ValueError("a reason is required")
        doc = self._owned(principal, memory_id)
        versions = list(self.memories.find({"lineageId": doc["lineageId"]}, {"_id": 1, "version": 1}))
        self.memories.delete_many({"lineageId": doc["lineageId"]})
        now = utc_now()
        actor = _actor(principal)
        audit.log_many(self.db, [
            {"tenantId": principal.tenant_id, "memoryId": v["_id"], "version": v["version"], "event": "forgotten",
             "actor": actor, "runId": None, "reason": reason.strip(), "contentHash": None,
             "details": {"lineageId": doc["lineageId"], "versionsDeleted": len(versions)}}
            for v in versions
        ])
        card = self.to_card(doc)
        return card.model_copy(update={
            "title": "Forgotten memory", "applicability": Applicability(),
            "forgotten": Tombstone(forgotten_by=actor["id"], reason=reason.strip(), at=now),
        })

    def forget_for_reset(self, tenant_id: str, repositories: list[str], reason: str) -> dict:
        """Demo/dev reset only (#67): forget every NON-seeded memory (seeded absent or false) in the given
        repositories of one tenant, e.g. memories promoted by earlier agent runs, so a reset can't leave
        stale duplicates recallable. Same path as forget(): every version of each lineage is deleted and a
        content-free tombstone is written per version, recorded as done by policy:demo-reset (no human
        admin is impersonated). Other repositories and seeded memories are untouched.
        Returns {"lineages": n, "versions": n}."""
        scope = {"tenantId": tenant_id, "repositoryId": {"$in": repositories}, "seeded": {"$ne": True}}
        lineages = self.memories.distinct("lineageId", scope)
        if not lineages:
            return {"lineages": 0, "versions": 0}
        versions = list(self.memories.find({"lineageId": {"$in": lineages}}, {"_id": 1, "version": 1, "lineageId": 1}))
        self.memories.delete_many({"lineageId": {"$in": lineages}})
        actor = {"type": "policy", "id": "demo-reset"}
        audit.log_many(self.db, [
            {"tenantId": tenant_id, "memoryId": v["_id"], "version": v["version"], "event": "forgotten",
             "actor": actor, "runId": None, "reason": reason, "contentHash": None,
             "details": {"lineageId": v["lineageId"], "reset": True}}
            for v in versions
        ])
        return {"lineages": len(lineages), "versions": len(versions)}

    def expire_now(self, principal: Principal, memory_id: str, reason: str) -> MemoryCard:
        """Expire immediately: recall stops returning it at once (the search filter checks expiresAt);
        the TTL index deletes it after the policy's purge grace."""
        if not reason or not reason.strip():
            raise ValueError("a reason is required")
        doc = self._owned(principal, memory_id)
        now = utc_now()
        policy = get_policy(self.db, doc["tenantId"], doc["ownerTeamId"])
        purge = now + timedelta(seconds=policy["purgeGraceSeconds"])
        self.memories.update_one({"_id": memory_id}, {"$set": {"expiresAt": now, "purgeAt": purge}})
        audit.log(self.db, tenant_id=principal.tenant_id, event="expired_now", actor=_actor(principal),
                  memory_id=memory_id, version=doc["version"], reason=reason.strip(),
                  details={"from": doc["expiresAt"], "purgeAt": purge}, content_hash=audit.content_hash(doc))
        doc.update(expiresAt=now, purgeAt=purge)
        return self.to_card(doc)

    # ------------------------------------------------------------------ correction and audit (P2-7)

    def correct(self, principal: Principal, memory_id: str, excludes: list[str], reason: str) -> MemoryCard:
        """Correct WITHOUT overwriting (guide rule 5): a new version with narrowed `excludes` supersedes
        the current one, and both stay in the lineage. Only narrowing is allowed here (adding exclusions);
        changing the fix itself would need a new verification run. Same proof, same expiry, same
        embedding (the retrieval text doesn't change), a fresh per-version HMAC secret."""
        if not reason or not reason.strip():
            raise ValueError("a reason is required")
        added = [x.strip() for x in excludes if x and x.strip()]
        if not added:
            raise ValueError("give at least one exclusion to add")
        old = self._owned(principal, memory_id)
        if old["status"] != "active":
            raise ValueError(f"only an active memory can be corrected (this one is {old['status']})")
        old = self.memories.find_one({"_id": memory_id})  # with the embedding, to copy it
        merged = list(dict.fromkeys([*old.get("applicability", {}).get("excludes", []), *added]))

        new_version = old["version"] + 1
        new_id = f"{old['lineageId']}_v{new_version}"
        now = utc_now()
        new = {**old, "_id": new_id, "version": new_version, "supersedes": memory_id, "status": "active",
               "applicability": {**old.get("applicability", {}), "excludes": merged},
               "hmacSecret": secrets.token_hex(32), "createdAt": now,
               "correction": {"by": _actor(principal)["id"], "reason": reason.strip(), "at": now,
                              "addedExcludes": added}}

        # Retire the old version first, atomically (only if still active), then add the new one.
        res = self.memories.update_one({"_id": memory_id, "status": "active"}, {"$set": {"status": "superseded"}})
        if not res.modified_count:
            raise ValueError("the memory changed meanwhile; reload and try again")
        try:
            self.memories.insert_one(new)
        except Exception:
            self.memories.update_one({"_id": memory_id}, {"$set": {"status": "active"}})  # roll back
            raise

        actor = _actor(principal)
        audit.log_many(self.db, [
            {"tenantId": principal.tenant_id, "memoryId": memory_id, "version": old["version"], "event": "corrected",
             "actor": actor, "runId": None, "reason": reason.strip(), "contentHash": audit.content_hash(old),
             "details": {"supersededBy": new_id, "addedExcludes": added}},
            {"tenantId": principal.tenant_id, "memoryId": new_id, "version": new_version, "event": "corrected",
             "actor": actor, "runId": None, "reason": reason.strip(), "contentHash": audit.content_hash(new),
             "details": {"supersedes": memory_id, "addedExcludes": added}},
        ])
        return self.to_card(new)

    def history(self, principal: Principal, memory_id: str) -> list[dict]:
        """GET /memories/{id}/audit: every audit event of this memory's whole lineage, oldest first
        ("who read memory X?"). Admin of the owner team. After Forget, the tombstone history is still
        readable by an admin of the team that forgot it. Events never contain memory content."""
        doc = self.memories.find_one({"_id": memory_id, **self.readable(principal)}, {"lineageId": 1, "ownerTeamId": 1})
        if doc is not None:
            if doc["ownerTeamId"] != principal.team_id:
                raise PermissionError("only an admin of the owner team can read the history")
            ids = [d["_id"] for d in self.memories.find({"lineageId": doc["lineageId"]}, {"_id": 1})]
        else:
            tomb = self.db.memory_audit.find_one({"memoryId": memory_id, "event": "forgotten",
                                                  "tenantId": principal.tenant_id})
            if tomb is None or not tomb["actor"]["id"].endswith(f"@{principal.team_id}"):
                raise LookupError(memory_id)
            lineage = tomb.get("details", {}).get("lineageId", memory_id)
            ids = self.db.memory_audit.distinct("memoryId", {"tenantId": principal.tenant_id, "event": "forgotten",
                                                             "details.lineageId": lineage}) or [memory_id]
        events = self.db.memory_audit.find({"tenantId": principal.tenant_id, "memoryId": {"$in": ids}},
                                           {"_id": 0, "tenantId": 0}).sort("at", 1)
        return list(events)

    def staleness(self, principal: Principal, memory_id: str) -> dict | None:
        """R12, cheap and unaudited (the UI polls it): has the code changed since this memory was
        proven? None if the caller's team can't read the memory."""
        doc = self.memories.find_one({"_id": memory_id, **self.readable(principal)},
                                     {"repositoryId": 1, "provenAgainst": 1})
        if doc is None:
            return None
        changed = changed_files(doc["repositoryId"], doc.get("provenAgainst", []))
        return {"memoryId": memory_id, "stale": bool(changed), "changedFiles": changed,
                "checked": bool(doc.get("provenAgainst"))}

    def refusals(self, principal: Principal, limit: int = 5) -> list[dict]:
        """Recent writes Atlas refused for the caller's team (R11): newest first, facts only
        (run, case, which tests failed). Nothing was stored, so there is no memory to show."""
        cur = self.db.memory_audit.find(
            {"tenantId": principal.tenant_id, "event": "refused", "details.teamId": principal.team_id},
            {"_id": 0, "tenantId": 0, "memoryId": 0, "version": 0, "contentHash": 0},
        ).sort("at", -1).limit(limit)
        return list(cur)

    @staticmethod
    def printable_scope(p: Principal) -> dict:
        """The $vectorSearch pre-filter as shown on screen in the Fence view."""
        return {**AtlasMemoryStore.scope(p, utc_now()), "expiresAt": {"$gt": "now"}}

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
            stale=bool(changed_files(doc["repositoryId"], doc.get("provenAgainst", []))),
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
            stale=bool(changed_files(doc["repositoryId"], doc.get("provenAgainst", []))),
            match=doc.get("_match"),
        )
