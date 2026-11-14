"""Seed the demo database (owner: P2; plan section 8). P3's scripts/demo_reset.py calls it with --reset.

    uv run python scripts/seed_demo.py --db traceback_demo --reset    # what demo_reset runs
    uv run python scripts/seed_demo.py --db traceback_demo            # top up, keep what exists
    uv run python scripts/seed_demo.py --db traceback_p2 --sample     # + a hand-made webhook memory (testing)
    uv run python scripts/seed_demo.py --db traceback_demo --poison   # + a real "Memory refused: no proof" (R11)

Creates:
- team policies (24 h life, 48 h max lifetime)
- the **Earn memory**: case A's reference fix, verified by P3's real runner (LocalRunner) and promoted
  under Payments, exactly the path a real run takes. With --reset it is recreated, so its 24 h
  restart and a memory forgotten in the previous judging round comes back.
- with --reset, memories that earlier agent runs promoted in the two demo repositories are forgotten
  first (tombstones kept), so rehearsals can't leave stale duplicates behind (#67)
- the 90-second **canary** (seeded), recreated every time so its countdown restarts
- about 20 labelled **distractors** across both teams (R8): other bug families, so vector search and
  its score cutoff (memory/config.py MIN_SCORE) have something real to reject

Honesty rule: a memory is labelled `seeded: true` unless the real runner proved it. If the fixture
database (Docker) is down, the Earn step fails loudly; `--runner fake` exists only for laptops
without Docker, and then the Earn memory is labelled seeded too.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.drafts import build_draft  # noqa: E402
from agent.observe import observations_from_case  # noqa: E402
from contracts.models import (  # noqa: E402
    Applicability,
    CaseManifest,
    Conditions,
    FilePatch,
    MemoryDraft,
    Principal,
    VerificationResult,
)
from core.db import get_db  # noqa: E402
from memory.policy import DEMO_POLICY  # noqa: E402
from memory.store import AtlasMemoryStore, MemoryRefused  # noqa: E402

TENANT = "demo-org"
TEAMS = ["team-payments", "team-platform"]
PAYMENTS = Principal(tenant_id=TENANT, team_id="team-payments", role="engineer",
                     authorized_repos=["payments-webhooks"])

# ------------------------------------------------------------------ the Earn memory (case A)

EARN_CASE = "A"
EARN_INCIDENT = "inc_demo_earn_A"  # fixed, so re-running without --reset doesn't duplicate it
EARN_TITLE = "Replayed webhook: record the replay, credit once"
EARN_CAUSE = "A provider retry re-delivers an already-processed event; the handler inserts it again."
EARN_RESOLUTION = (
    "Treat a duplicate provider_event_id as already processed: keep the unique index, don't credit "
    "again, record it with ledger.mark_replayed(event.id), return 200."
)

# ------------------------------------------------------------------ seeded memories

SEEDED_PROOF = VerificationResult(run_id="seed", case_id="seed", status="passed",
                                  before_failed=True, after_passed=True, evidence_hashes=["seeded"])
NO_PATCH = FilePatch(path="SEEDED.txt", new_content="# seeded memory: no real patch\n")

# Deliberately NOT about webhooks, so it never shows up in the Fence or Reuse searches.
CANARY = MemoryDraft(
    incident_id="seed_canary", repository_id="billing-exports", source_revision="seed",
    retrieval_text="Nightly CSV export job exceeds the 30 second worker timeout for tenants with many invoices.",
    signature={"errorCode": "TIMEOUT", "operation": "export.nightly"},
    confirmed_cause="Export loads all invoices into memory before streaming.",
    applicability=Applicability(), resolution_summary="Stream invoices in pages of 500.", patch=NO_PATCH,
)

SAMPLE_WEBHOOK = MemoryDraft(
    incident_id="seed_sample_webhook", repository_id="payments-webhooks", source_revision="seed",
    retrieval_text=("Duplicate webhook delivery raises E11000 on provider_event_id; first delivery succeeded; "
                    "retry carries the same event identifier."),
    signature={"errorCode": "11000", "operation": "webhook.insert"},
    confirmed_cause="Replay path performs a second insert for an already-processed provider event.",
    applicability=Applicability(conditions=Conditions(dup_key_field="provider_event_id",
                                                      same_event_id_on_both_deliveries=True)),
    resolution_summary=EARN_RESOLUTION,
    patch=NO_PATCH,
)


# ------------------------------------------------------------------ distractors (R8, plan 4.4)
# Realistic incidents from OTHER bug families, across both teams, so vector search has something to
# rank and the score cutoff has something to reject. All labelled seeded. A few are deliberate near
# misses (a webhook signature failure, a webhook relay timeout, a missing index) to test the cutoff.
# None uses error 11000 on POST /webhooks/provider, so none can enter through the exact signature lookup.
# (team, repository, title, symptoms = retrievalText, errorCode, operation, cause, fix)
DISTRACTORS = [
    ("team-payments", "payments-billing", "Round JPY totals once, at the end",
     "Invoice totals for JPY customers are off by one yen; line items look right but the sum differs.",
     "ROUNDING", "invoice.total", "Each line is rounded before summing.", "Sum exact amounts, round once."),
    ("team-payments", "payments-webhooks", "Reload the signing secret after rotation",
     "Provider webhooks rejected with HTTP 401 invalid signature since this morning's secret rotation.",
     "401", "POST /webhooks/provider/verify", "The old signing secret is cached in memory.",
     "Reload the secret on rotation; accept old and new during the overlap."),
    ("team-payments", "payments-billing", "Compare card expiry in the card's own month",
     "Cards are declined as expired one day early for customers in Asia and Australia.",
     "CARD_EXPIRED", "card.validate", "Expiry compared against UTC midnight.", "Compare end of month in issuer time."),
    ("team-payments", "payments-settlement", "Back off on 429 during settlement",
     "Nightly settlement batch stops halfway with HTTP 429 Too Many Requests from the bank API.",
     "429", "settlement.batch", "No backoff between bank API calls.", "Exponential backoff with jitter."),
    ("team-payments", "payments-ledger", "Store money as integer minor units",
     "Ledger balances drift by fractions of a cent after many small transfers.",
     "FLOAT_DRIFT", "ledger.write", "Amounts stored as floating point.", "Store integer minor units."),
    ("team-payments", "payments-billing", "Stream long receipts to PDF",
     "Receipt PDF download times out for invoices with more than a few hundred lines.",
     "TIMEOUT", "receipt.render", "Whole receipt built in memory first.", "Render pages incrementally."),
    ("team-payments", "payments-billing", "Invalidate tax cache on region change",
     "Customers who moved region are still charged their old sales-tax rate.",
     "STALE_CACHE", "tax.lookup", "Tax rate cached by customer id only.", "Key the cache by region too."),
    ("team-payments", "payments-billing", "Schedule renewals in UTC",
     "Some subscriptions renewed twice on the night the clocks changed for daylight saving.",
     "CRON_DST", "subscription.renew", "Cron runs in local time across the DST change.", "Run the job in UTC."),
    ("team-payments", "payments-payouts", "Validate IBAN before payout",
     "Payouts to some European bank accounts bounce days later as invalid account number.",
     "IBAN_INVALID", "payout.create", "IBAN checksum not validated.", "Validate IBAN checksum at entry."),
    ("team-payments", "payments-billing", "Paginate the invoice export",
     "Monthly invoice export for large merchants crashes the worker with out of memory.",
     "OOM", "invoice.export", "Whole month loaded at once.", "Paginate by 1,000 invoices."),
    ("team-platform", "platform-infra", "Raise the resize worker's memory limit",
     "Image resize pods are OOMKilled and restart in a loop when users upload very large photos.",
     "OOMKilled", "worker.resize", "Full-size image decoded in memory.", "Downscale while decoding."),
    ("team-platform", "platform-infra", "Size the Redis pool to the worker count",
     "Under peak load requests fail with Redis connection pool exhausted.",
     "POOL_EXHAUSTED", "cache.get", "Pool smaller than the number of workers.", "Pool size per worker."),
    ("team-platform", "platform-gateway", "Renew the internal gateway certificate",
     "Service-to-service calls fail with TLS handshake error: certificate has expired.",
     "TLS_EXPIRED", "gateway.handshake", "Internal certificate not auto-renewed.", "Automate renewal."),
    ("team-platform", "platform-config", "Default missing feature flags",
     "Config loader crashes with a null pointer when a feature flag is missing.",
     "NULL_FLAG", "flags.load", "Missing flag returns null.", "Return the declared default."),
    ("team-platform", "platform-observability", "Alert before the log disk fills",
     "Log shipper silently drops lines when the node disk is full.",
     "DISK_FULL", "logs.ship", "No disk alert; shipper drops on write error.", "Alert at 80% and back-pressure."),
    ("team-platform", "platform-audit", "Index the audit log by date",
     "Audit log page takes 30 seconds to load; the database does a full collection scan.",
     "SLOW_QUERY", "audit.list", "No index on created_at.", "Add an index on created_at."),
    ("team-platform", "platform-infra", "Cache DNS for service discovery",
     "Intermittent 'name not resolved' errors between services during traffic spikes.",
     "DNS_FAIL", "discovery.resolve", "DNS lookups not cached.", "Local DNS cache with a short TTL."),
    ("team-platform", "platform-deploy", "Make migrations reversible",
     "Deploy rollback fails because the database migration cannot be undone.",
     "MIGRATION", "deploy.rollback", "Destructive migration in one step.", "Expand, migrate, contract."),
    ("team-platform", "platform-webhooks", "Time out the webhook relay sooner",
     "Our webhook relay to partners times out and piles up requests when a partner is slow.",
     "TIMEOUT", "POST /relay/partner", "No timeout on outbound partner calls.", "Five-second timeout and a queue."),
    ("team-platform", "platform-auth", "Allow clock skew in token checks",
     "Users are logged out at random with 'token not yet valid' errors.",
     "JWT_NBF", "auth.verify", "Server clocks differ by a few seconds.", "Allow 30 seconds of skew."),
]


def seed_distractors(store: AtlasMemoryStore) -> int:
    n = 0
    for i, (team_id, repo, title, symptoms, code, op, cause, fix) in enumerate(DISTRACTORS, 1):
        draft = MemoryDraft(
            incident_id=f"seed_distractor_{i:02d}", repository_id=repo, source_revision="seed",
            retrieval_text=symptoms, signature={"errorCode": code, "operation": op}, confirmed_cause=cause,
            applicability=Applicability(), resolution_summary=fix, patch=NO_PATCH,
        )
        owner = Principal(tenant_id=TENANT, team_id=team_id, role="engineer")
        store.promote(owner, draft, SEEDED_PROOF, title=title, seeded=True)
        n += 1
    return n


def git_revision() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def earn(store: AtlasMemoryStore, runner_choice: str, reset: bool) -> bool:
    """Verify case A's reference fix with the runner and promote it, as a real run would."""
    manifest = CaseManifest.model_validate_json((ROOT / "cases" / EARN_CASE / "manifest.json").read_text("utf-8"))
    path = manifest.patchable_files[0]
    patch = FilePatch(path=path, new_content=(ROOT / "cases" / EARN_CASE / "reference" / Path(path).name)
                      .read_text("utf-8"))

    if reset:  # every version of the previous Earn memory, so its 24 h restart
        old = store.memories.delete_many({"provenance.sourceIncidentId": EARN_INCIDENT}).deleted_count
        if old:
            print(f"earn: removed the previous Earn memory ({old} version(s))")

    if runner_choice == "fake":
        from contracts.fakes import FakeRunner
        result, seeded = FakeRunner().verify(EARN_CASE, patch), True
        print("earn: FAKE runner, so the Earn memory is labelled seeded (no real proof)")
    else:
        from runner.sandbox import LocalRunner
        result, seeded = LocalRunner().verify(EARN_CASE, patch), False

    passed = sum(t.passed for t in result.tests)
    print(f"earn: case {EARN_CASE} reference fix -> {result.status}, tests {passed}/{len(result.tests)}")
    if not result.verified:
        hint = (" Start it: docker run -d --name fixture-mongo -p 27018:27017 mongo"
                if (result.detail or "").startswith("fixture database") else "")
        print(f"earn: FAILED, not promoted ({result.detail or 'reference fix did not verify'}).{hint}")
        return False

    obs = observations_from_case(manifest, incident_id=EARN_INCIDENT)
    draft = build_draft(obs, patch, source_revision=git_revision(), confirmed_cause=EARN_CAUSE,
                        resolution_summary=EARN_RESOLUTION)
    mem_id = store.promote(PAYMENTS, draft, result, title=EARN_TITLE, seeded=seeded)
    print(f"earn: Earn memory {mem_id} (Payments, 24 h)")
    return True


DEMO_REPOSITORIES = ["payments-webhooks", "platform-webhooks"]


def reset_memories(store: AtlasMemoryStore) -> dict:
    """--reset (#67): start the demo memory from a known state.
    1. Seeded memories (canary, distractors, a fake-runner Earn) are deleted; they're recreated below.
    2. Every NON-seeded memory in the two demo repositories (the previous Earn, and anything earlier agent
       runs promoted: duplicate Earns, case C/D memories) is forgotten, all versions, with tombstones by
       policy:demo-reset, so no stale duplicate stays recallable. Other repositories are untouched.
    Safe to run twice."""
    seeded = store.memories.delete_many({"tenantId": TENANT, "seeded": True}).deleted_count
    forgot = store.forget_for_reset(TENANT, DEMO_REPOSITORIES, "demo reset: start from a known state (#67)")
    print(f"reset: deleted {seeded} seeded memories; forgot {forgot['lineages']} earlier memories in "
          f"{', '.join(DEMO_REPOSITORIES)} ({forgot['versions']} version(s), tombstones kept)")
    return {"seeded": seeded, **forgot}


def poison(store: AtlasMemoryStore) -> bool:
    """R11, deterministic: run case P's POISONED fix (it follows the log's injected "drop the unique
    index" instruction) through the real runner, then try to save it as a memory the way a run would.
    The runner fails test_unique_index_still_present, so Atlas's validator refuses the write.
    Returns True only if the database really refused it."""
    from runner.sandbox import LocalRunner

    manifest = CaseManifest.model_validate_json((ROOT / "cases" / "P" / "manifest.json").read_text("utf-8"))
    path = manifest.patchable_files[0]
    fix = FilePatch(path=path, new_content=(ROOT / "cases" / "P" / "poisoned" / Path(path).name).read_text("utf-8"))
    result = LocalRunner().verify("P", fix)
    failed = [t.name for t in result.tests if not t.passed]
    print(f"poison: case P poisoned fix -> {result.status}, failed: {', '.join(failed) or 'none'}")
    if result.status == "inconclusive":
        print(f"poison: FAILED, runner could not run ({result.detail}). "
              "Start it: docker run -d --name fixture-mongo -p 27018:27017 mongo")
        return False
    obs = observations_from_case(manifest, incident_id="inc_demo_poison_P")
    draft = build_draft(obs, fix, source_revision=git_revision(), confirmed_cause="Drop the unique index.",
                        resolution_summary="Drop the unique index on provider_event_id.")
    try:
        mem_id = store.promote(PAYMENTS, draft, result)
    except MemoryRefused as e:
        print(f"poison: {e} (Atlas validator; audit event 'refused', run {result.run_id})")
        return True
    store.memories.delete_many({"_id": mem_id})  # must never happen: don't leave it behind
    print("poison: FAILED, the poisoned fix verified and was stored; removed it. Check case P.")
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed Traceback demo data.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--reset", action="store_true", help="recreate the Earn memory, delete seeded memories")
    ap.add_argument("--runner", choices=["local", "fake"], default="local",
                    help="fake only without Docker; the Earn memory is then labelled seeded")
    ap.add_argument("--no-earn", action="store_true", help="skip the Earn memory")
    ap.add_argument("--no-distractors", action="store_true", help="skip the ~20 labelled distractor memories")
    ap.add_argument("--sample", action="store_true", help="also seed a hand-made webhook memory (testing only)")
    ap.add_argument("--poison", action="store_true",
                    help="R11: real runner on case P's poisoned fix, then a write Atlas refuses (needs Docker)")
    a = ap.parse_args()
    db = get_db(a.db)

    for team in TEAMS:
        db.policies.replace_one({"_id": f"{TENANT}:{team}"},
                                {"tenantId": TENANT, "teamId": team, **DEMO_POLICY}, upsert=True)
    print(f"policies: {', '.join(TEAMS)}")

    store = AtlasMemoryStore(db)
    if a.reset:
        reset_memories(store)

    ok = True if a.no_earn else earn(store, a.runner, a.reset)

    # The canary is recreated every time, so its 90-second countdown restarts.
    db.memories.delete_many({"provenance.sourceIncidentId": "seed_canary"})
    canary = store.promote(PAYMENTS, CANARY, SEEDED_PROOF, title="Canary: nightly export timeout",
                           seeded=True, expires_in_seconds=90)
    print("canary (90 s):", canary)
    if not a.no_distractors:
        print(f"distractors: {seed_distractors(store)} labelled seeded memories (both teams, 24 h)")
    if a.poison:
        ok = poison(store) and ok
    if a.sample:
        print("sample webhook memory:", store.promote(PAYMENTS, SAMPLE_WEBHOOK, SEEDED_PROOF, seeded=True,
                                                      title="Sample: duplicate webhook (hand-made)"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
