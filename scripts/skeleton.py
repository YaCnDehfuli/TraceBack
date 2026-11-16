"""Walking skeleton. No LLM, no API: calls the runner and the memory service directly.

    reference fix for case A -> runner.verify() -> memory.promote() under Payments
    -> recall() with case B's observations: Payments must find it, Platform must find nothing

    uv run python scripts/skeleton.py                      # real runner and Atlas memory, fakes if not merged yet
    uv run python scripts/skeleton.py --strict             # fail instead of falling back to fakes
    uv run python scripts/skeleton.py --runner fake --memory fake

Done when it prints "Skeleton OK: Payments finds 1, Platform finds 0".
The real runner needs the fixture database:  docker run -d --name fixture-mongo -p 27018:27017 mongo
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.conditions import check_conditions  # noqa: E402
from agent.drafts import build_draft  # noqa: E402
from agent.observe import observations_from_case  # noqa: E402
from contracts.fakes import REFERENCE_FIX, FakeMemoryStore, FakeRunner  # noqa: E402
from contracts.interfaces import MemoryStore, Runner  # noqa: E402
from contracts.models import CaseManifest, FilePatch, Principal  # noqa: E402
from core.clock import new_id  # noqa: E402

PAYMENTS = Principal(tenant_id="demo-org", team_id="team-payments", authorized_repos=["payments-webhooks"])
PLATFORM = Principal(tenant_id="demo-org", team_id="team-platform", authorized_repos=["platform-webhooks"])

# Facts the skeleton states about the proven fix. Not read from labels.json (those stay hidden).
CAUSE = "A provider retry re-delivers an already-processed event; the handler inserts it again."
RESOLUTION = (
    "Treat a duplicate provider_event_id as already processed: keep the unique index, don't credit "
    "again, record it with ledger.mark_replayed(event.id), return 200."
)

# Used only with --runner fake when the case files are not available.
_FALLBACK_CASES = {
    "A": {
        "caseId": "A",
        "teamId": "team-payments",
        "repositoryId": "payments-webhooks",
        "fixturePath": "fixture_app/payments-webhooks",
        "request": {
            "method": "POST",
            "path": "/webhooks/provider",
            "report": "Provider notifications are failing with HTTP 500.",
            "deliveries": [{"id": "evt_1001"}, {"id": "evt_1001"}],
        },
        "logs": 'File "app/webhooks.py", line 20, in receive\npymongo.errors.DuplicateKeyError: E11000 duplicate key '
        "error collection: fixture_payments.payments index: provider_event_id_1 dup key: "
        '{ provider_event_id: "evt_1001" }',
        "patchableFiles": ["app/webhooks.py"],
        "reproductionTest": "test_duplicate_event_reproduces",
    },
    "B": {
        "caseId": "B",
        "teamId": "team-payments",
        "repositoryId": "payments-webhooks",
        "fixturePath": "fixture_app/payments-webhooks",
        "request": {
            "method": "POST",
            "path": "/webhooks/provider",
            "report": "Our notification endpoint is throwing server errors and the provider keeps retrying.",
            "deliveries": [{"id": "evt_2001"}, {"id": "evt_2001"}],
        },
        "logs": 'File "app/webhooks.py", line 21, in handle_provider_event\npymongo.errors.DuplicateKeyError: E11000 '
        "duplicate key error collection: fixture_payments.payments index: provider_event_id_1 dup key: "
        '{ provider_event_id: "evt_2001" }',
        "patchableFiles": ["app/webhooks.py"],
        "reproductionTest": "test_duplicate_event_reproduces",
    },
}


def say(msg: str) -> None:
    print(msg, flush=True)


def load_case(case_id: str, allow_fallback: bool) -> CaseManifest:
    path = ROOT / "cases" / case_id / "manifest.json"
    if path.exists():
        return CaseManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))
    if not allow_fallback:
        raise SystemExit(f"cases/{case_id}/manifest.json not found. Use --runner fake.")
    say(f"  (cases/{case_id} not on this branch yet: using a built-in copy)")
    return CaseManifest.model_validate(_FALLBACK_CASES[case_id])


def reference_fix(manifest: CaseManifest) -> FilePatch:
    path = ROOT / "cases" / manifest.case_id / "reference" / Path(manifest.patchable_files[0]).name
    content = path.read_text(encoding="utf-8") if path.exists() else REFERENCE_FIX
    if not path.exists():
        say(f"  (no {path.relative_to(ROOT)} yet: using contracts.fakes.REFERENCE_FIX)")
    return FilePatch(path=manifest.patchable_files[0], new_content=content)


def git_revision() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


FIXTURE_HINT = "start it with: docker run -d --name fixture-mongo -p 27018:27017 mongo"


def pick_runner(choice: str) -> tuple[Runner, str]:
    if choice == "fake":
        return FakeRunner(), "FakeRunner"
    from runner.sandbox import LocalRunner

    return LocalRunner(), "LocalRunner"


def pick_memory(choice: str, strict: bool) -> tuple[MemoryStore, str, bool]:
    """Returns (store, name, is_fallback). Falls back to the fake only in auto mode, and says so."""
    if choice == "fake":
        return FakeMemoryStore(seed_example=False), "FakeMemoryStore", False
    try:
        from memory.store import AtlasMemoryStore

        return AtlasMemoryStore(), "AtlasMemoryStore", False
    except RuntimeError as e:  # e.g. MONGODB_URI not set yet
        if strict or choice == "atlas":
            raise SystemExit(f"AtlasMemoryStore: {e}") from None
        say(f"  (Atlas not configured yet: {e} Using the fake memory.)")
        return FakeMemoryStore(seed_example=False), "FakeMemoryStore", True


def explain_memory_error(e: Exception) -> str:
    name = type(e).__name__
    if name == "MemoryRefused":
        return str(e) or "Memory refused: no proof."
    if "ServerSelectionTimeout" in name:
        return "cannot reach Atlas: add your IP in Atlas > Database & Network Access > IP Access List"
    if "OperationFailure" in name and "auth" in str(e).lower():
        return "Atlas authentication failed: check the user and password in MONGODB_URI"
    return f"{name}: {str(e)[:200]}"


def wait_searchable(memory: MemoryStore, memory_id: str, timeout_s: float = 60) -> float | None:
    started = time.monotonic()
    while time.monotonic() - started < timeout_s:
        if memory.is_searchable(PAYMENTS, memory_id):
            return time.monotonic() - started
        time.sleep(1)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walking skeleton: verify, promote, recall.")
    parser.add_argument("--earn", default="A", help="case whose reference fix is promoted (default A)")
    parser.add_argument("--recall", default="B", help="case whose observations are used for recall (default B)")
    parser.add_argument("--runner", choices=["auto", "local", "fake"], default="auto")
    parser.add_argument("--memory", choices=["auto", "atlas", "fake"], default="auto")
    parser.add_argument("--strict", action="store_true", help="never fall back to fakes")
    args = parser.parse_args(argv)
    allow_fallback = not args.strict

    earn = load_case(args.earn, allow_fallback)
    reuse = load_case(args.recall, allow_fallback)
    patch = reference_fix(earn)

    # 1. Proof: the runner verifies the reference fix.
    say(f"1. Verify the reference fix for case {earn.case_id}")
    runner, runner_name = pick_runner(args.runner)
    must_be_real = args.strict or args.runner == "local"
    faked = args.runner == "fake"
    try:
        result = runner.verify(earn.case_id, patch)
    except NotImplementedError as e:
        if must_be_real:
            raise SystemExit(f"{runner_name}: not implemented yet ({e}).") from None
        say(f"  ({runner_name} not merged yet: {e}. Using the fake runner.)")
        result, faked, runner_name = FakeRunner().verify(earn.case_id, patch), True, "FakeRunner"
    if not faked and result.status == "inconclusive" and (result.detail or "").startswith("fixture database"):
        if must_be_real:
            say(f"Skeleton FAILED: fixture database unreachable; {FIXTURE_HINT}")
            return 1
        say(f"  (fixture database unreachable: using the fake runner. For the real one, {FIXTURE_HINT})")
        result, faked, runner_name = FakeRunner().verify(earn.case_id, patch), True, "FakeRunner"
    passed = sum(t.passed for t in result.tests)
    say(
        f"   {runner_name}: status={result.status} before_failed={result.before_failed} "
        f"after_passed={result.after_passed} tests {passed}/{len(result.tests)}"
    )
    if not result.verified:
        for t in result.tests:
            if not t.passed:
                say(f"   failed: {t.name}: {t.detail}")
        if result.detail:
            say(f"   detail: {result.detail}")
        say("Skeleton FAILED: the reference fix is not verified, so nothing may be promoted.")
        return 1

    # 2. Earn: promote under Payments, then wait until vector search can see it.
    say("2. Promote the proven fix as a Payments memory")
    obs_earn = observations_from_case(earn, incident_id=new_id("inc"))
    draft = build_draft(
        obs_earn, patch, source_revision=git_revision(), confirmed_cause=CAUSE, resolution_summary=RESOLUTION
    )
    memory, memory_name, mem_faked = pick_memory(args.memory, args.strict)
    try:
        memory_id = memory.promote(PAYMENTS, draft, result)
    except NotImplementedError as e:
        if args.strict or args.memory == "atlas":
            raise SystemExit(f"{memory_name}: not implemented yet ({e}).") from None
        say(f"  ({memory_name} not merged yet: {e}. Using the fake memory.)")
        memory, memory_name, mem_faked = FakeMemoryStore(seed_example=False), "FakeMemoryStore", True
        memory_id = memory.promote(PAYMENTS, draft, result)
    except Exception as e:  # noqa: BLE001 - report any Atlas problem in one line
        say(f"Skeleton FAILED: promote: {explain_memory_error(e)}")
        return 1
    say(f"   {memory_name}: promoted {memory_id}")
    waited = wait_searchable(memory, memory_id)
    if waited is None:
        say("Skeleton FAILED: the memory never became searchable within 60 s (vector index not ready?).")
        return 1
    say(f"   searchable after {waited:.1f} s")

    # 3. Reuse and Fence: recall with case B's observations under both teams.
    say(f"3. Recall with case {reuse.case_id}'s observations")
    obs_reuse = observations_from_case(reuse, incident_id=new_id("inc"))
    try:
        payments_hits = memory.recall(PAYMENTS, obs_reuse, run_id=new_id("run"))
        platform_hits = memory.recall(PLATFORM, obs_reuse, run_id=new_id("run"))
    except Exception as e:  # noqa: BLE001
        say(f"Skeleton FAILED: recall: {explain_memory_error(e)}")
        return 1
    say(f"   Payments finds {len(payments_hits)}; Platform finds {len(platform_hits)}")
    if payments_hits:
        top = payments_hits[0]
        results = check_conditions(top.applicability.conditions, obs_reuse)
        held = sum(bool(r.held) for r in results)
        say(f"   top memory {top.memory_id} (match {top.match}); conditions {held}/{len(results)} hold")

    ok = len(payments_hits) >= 1 and not platform_hits
    uses_fakes = faked or mem_faked or args.runner == "fake" or args.memory == "fake"
    say(
        f"Skeleton {'OK' if ok else 'FAILED'}: Payments finds {len(payments_hits)}, Platform finds {len(platform_hits)}"
        + ("   [some parts were fakes]" if uses_fakes else "")
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
