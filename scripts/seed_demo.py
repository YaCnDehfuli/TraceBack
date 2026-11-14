"""Seed team policies and labelled seeded memories (owner: P2, P2-1 / P2-8; plan section 8).

    uv run python scripts/seed_demo.py --db traceback_demo            # policies + 90-second canary
    uv run python scripts/seed_demo.py --db traceback_p2 --sample     # + a hand-made webhook memory
    uv run python scripts/seed_demo.py --db traceback_demo --reset    # delete seeded memories first

Everything created here has `seeded: true` and verification.environment "seeded", so it is never
mistaken for a memory earned by a real run. The demo's Earn memory must come from a real runner
verification (case A or P1's skeleton), not from this script.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from contracts.models import (  # noqa: E402
    Applicability,
    Conditions,
    FilePatch,
    MemoryDraft,
    Principal,
    VerificationResult,
)
from core.db import get_db  # noqa: E402
from memory.policy import DEMO_POLICY  # noqa: E402
from memory.store import AtlasMemoryStore  # noqa: E402

TENANT = "demo-org"
TEAMS = ["team-payments", "team-platform"]
PAYMENTS = Principal(tenant_id=TENANT, team_id="team-payments", role="memory_admin")

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
    resolution_summary=("Treat a repeated provider_event_id as already processed; keep the unique index; "
                        "record the replay with ledger.mark_replayed(event.id)."),
    patch=NO_PATCH,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed Traceback demo data.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--reset", action="store_true", help="delete every seeded memory first")
    ap.add_argument("--sample", action="store_true", help="also seed a hand-made webhook memory (testing only)")
    a = ap.parse_args()
    db = get_db(a.db)

    for team in TEAMS:
        db.policies.replace_one({"_id": f"{TENANT}:{team}"},
                                {"tenantId": TENANT, "teamId": team, **DEMO_POLICY}, upsert=True)
    print(f"policies: {', '.join(TEAMS)}")

    if a.reset:
        print(f"reset: deleted {db.memories.delete_many({'seeded': True}).deleted_count} seeded memories")

    store = AtlasMemoryStore(db)
    # The canary is recreated every time, so its 90-second countdown restarts.
    db.memories.delete_many({"provenance.sourceIncidentId": "seed_canary"})
    canary = store.promote(PAYMENTS, CANARY, SEEDED_PROOF, title="Canary: nightly export timeout",
                           seeded=True, expires_in_seconds=90)
    print("canary (90 s):", canary)
    if a.sample:
        print("sample webhook memory:", store.promote(PAYMENTS, SAMPLE_WEBHOOK, SEEDED_PROOF, seeded=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
