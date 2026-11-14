"""Seed the demo database (owner: P2; plan section 8). P3's scripts/demo_reset.py calls it with --reset.

    uv run python scripts/seed_demo.py --db traceback_demo --reset    # what demo_reset runs
    uv run python scripts/seed_demo.py --db traceback_demo            # top up, keep what exists
    uv run python scripts/seed_demo.py --db traceback_p2 --sample     # + a hand-made webhook memory (testing)

Creates:
- team policies (24 h life, 48 h max lifetime)
- the **Earn memory**: case A's reference fix, verified by P3's real runner (LocalRunner) and promoted
  under Payments, exactly the path a real run takes. With --reset it is recreated, so its 24 h
  restart and a memory forgotten in the previous judging round comes back.
- the 90-second **canary** (seeded), recreated every time so its countdown restarts

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
from memory.store import AtlasMemoryStore  # noqa: E402

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


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed Traceback demo data.")
    ap.add_argument("--db", required=True)
    ap.add_argument("--reset", action="store_true", help="recreate the Earn memory, delete seeded memories")
    ap.add_argument("--runner", choices=["local", "fake"], default="local",
                    help="fake only without Docker; the Earn memory is then labelled seeded")
    ap.add_argument("--no-earn", action="store_true", help="skip the Earn memory")
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
    ok = True if a.no_earn else earn(store, a.runner, a.reset)

    # The canary is recreated every time, so its 90-second countdown restarts.
    db.memories.delete_many({"provenance.sourceIncidentId": "seed_canary"})
    canary = store.promote(PAYMENTS, CANARY, SEEDED_PROOF, title="Canary: nightly export timeout",
                           seeded=True, expires_in_seconds=90)
    print("canary (90 s):", canary)
    if a.sample:
        print("sample webhook memory:", store.promote(PAYMENTS, SAMPLE_WEBHOOK, SEEDED_PROOF, seeded=True,
                                                      title="Sample: duplicate webhook (hand-made)"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
