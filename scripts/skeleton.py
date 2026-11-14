"""Walking skeleton, rung R1 (P1-1). No LLM, no API: calls P3's runner and P2's memory directly.

    reference fix for case A -> runner.verify() -> memory.promote() under Payments
    -> recall() with case B's observations: Payments must find it, Platform must find nothing

    uv run python scripts/skeleton.py                      # real runner and Atlas memory, fakes if not merged yet
    uv run python scripts/skeleton.py --strict             # fail instead of falling back to fakes
    uv run python scripts/skeleton.py --runner fake --memory fake

Done when it prints "R1 OK: Payments finds 1, Platform finds 0".
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

# Used only with --runner fake when P3's cases are not on this branch yet.
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
        raise SystemExit(f"cases/{case_id}/manifest.json not found (P3-4). Merge P3's cases or use --runner fake.")
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


def pick_runner(choice: str) -> tuple[Runner, str]:
    if choice == "fake":
        return FakeRunner(), "FakeRunner"
    from runner.sandbox import LocalRunner

    return LocalRunner(), "LocalRunner"


def pick_memory(choice: str) -> tuple[MemoryStore, str]:
    if choice == "fake":
        return FakeMemoryStore(seed_example=False), "FakeMemoryStore"
    from memory.store import AtlasMemoryStore

    return AtlasMemoryStore(), "AtlasMemoryStore"


def call_with_fallback(label, real_call, fake_call, strict: bool):
    """Call the real implementation; if it is still a stub (NotImplementedError), use the fake."""
    try:
        return real_call(), False
    except NotImplementedError as e:
        if strict:
            raise SystemExit(f"{label}: not implemented yet ({e}) and --strict is set.") from None
        say(f"  ({label} not merged yet: {e}. Using the fake.)")
        return fake_call(), True


def wait_searchable(memory: MemoryStore, memory_id: str, timeout_s: float = 60) -> float | None:
    started = time.monotonic()
    while time.monotonic() - started < timeout_s:
        if memory.is_searchable(PAYMENTS, memory_id):
            return time.monotonic() - started
        time.sleep(1)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walking skeleton (rung R1): verify, promote, recall.")
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
    if args.runner == "local":
        result, faked = runner.verify(earn.case_id, patch), False
    else:
        result, faked = call_with_fallback(
            runner_name,
            lambda: runner.verify(earn.case_id, patch),
            lambda: FakeRunner().verify(earn.case_id, patch),
            args.strict,
        )
    passed = sum(t.passed for t in result.tests)
    say(
        f"   {'FakeRunner' if faked else runner_name}: status={result.status} before_failed={result.before_failed} "
        f"after_passed={result.after_passed} tests {passed}/{len(result.tests)}"
    )
    if not result.verified:
        for t in result.tests:
            if not t.passed:
                say(f"   failed: {t.name}: {t.detail}")
        if result.detail:
            say(f"   detail: {result.detail}")
        say("R1 FAILED: the reference fix is not verified, so nothing may be promoted.")
        return 1

    # 2. Earn: promote under Payments, then wait until vector search can see it.
    say("2. Promote the proven fix as a Payments memory")
    obs_earn = observations_from_case(earn, incident_id=new_id("inc"))
    draft = build_draft(
        obs_earn, patch, source_revision=git_revision(), confirmed_cause=CAUSE, resolution_summary=RESOLUTION
    )
    memory, memory_name = pick_memory(args.memory)
    fake_memory = FakeMemoryStore(seed_example=False)
    if args.memory == "atlas":
        memory_id, mem_faked = memory.promote(PAYMENTS, draft, result), False
    else:
        memory_id, mem_faked = call_with_fallback(
            memory_name,
            lambda: memory.promote(PAYMENTS, draft, result),
            lambda: fake_memory.promote(PAYMENTS, draft, result),
            args.strict,
        )
    if mem_faked:
        memory, memory_name = fake_memory, "FakeMemoryStore"
    say(f"   {memory_name}: promoted {memory_id}")
    waited = wait_searchable(memory, memory_id)
    if waited is None:
        say("R1 FAILED: the memory never became searchable within 60 s (vector index not ready?).")
        return 1
    say(f"   searchable after {waited:.1f} s")

    # 3. Reuse and Fence: recall with case B's observations under both teams.
    say(f"3. Recall with case {reuse.case_id}'s observations")
    obs_reuse = observations_from_case(reuse, incident_id=new_id("inc"))
    payments_hits = memory.recall(PAYMENTS, obs_reuse, run_id=new_id("run"))
    platform_hits = memory.recall(PLATFORM, obs_reuse, run_id=new_id("run"))
    say(f"   Payments finds {len(payments_hits)}; Platform finds {len(platform_hits)}")
    if payments_hits:
        top = payments_hits[0]
        results = check_conditions(top.applicability.conditions, obs_reuse)
        held = sum(bool(r.held) for r in results)
        say(f"   top memory {top.memory_id} (match {top.match}); conditions {held}/{len(results)} hold")

    ok = len(payments_hits) >= 1 and not platform_hits
    uses_fakes = faked or mem_faked or args.runner == "fake" or args.memory == "fake"
    say(
        f"R1 {'OK' if ok else 'FAILED'}: Payments finds {len(payments_hits)}, Platform finds {len(platform_hits)}"
        + ("   [some parts were fakes]" if uses_fakes else "")
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
