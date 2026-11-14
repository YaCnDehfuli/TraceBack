"""Run one investigation from the command line (P1-2):

    uv run python -m agent.run --case B --team payments [--memory real|off|placebo]
                               [--runner auto|local|fake] [--store auto|atlas|fake] [--no-seed] [--json]

auto = the real runner / Atlas memory when available, else the fake (announced). The fake memory is
seeded with the Earn memory unless --no-seed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEAMS = {
    "payments": {"tenant_id": "demo-org", "team_id": "team-payments", "authorized_repos": ["payments-webhooks"]},
    "platform": {"tenant_id": "demo-org", "team_id": "team-platform", "authorized_repos": ["platform-webhooks"]},
}
FIXTURE_HINT = "docker run -d --name fixture-mongo -p 27018:27017 mongo"


def say(msg: str) -> None:
    print(msg, flush=True)


def describe(event) -> str:
    p, t = event.payload, event.type
    if t == "run_started":
        return f"run started: case {p['caseId']} for {p['teamId']} (memory {p['memoryMode']})"
    if t == "observation":
        return f"observed: {p['observations']['summary']}"
    if t == "recall":
        return f"recall: {p['count']} memories"
    if t == "precondition_check":
        return f"conditions {p['held']}/{p['total']} for {p['memory']['memoryId']}" + (
            f": {p['notAppliedReason']}" if p.get("notAppliedReason") else ""
        )
    if t == "tool_call":
        return f"tool: {p['tool']} {json.dumps(p['args'])[:100]}"
    if t == "tool_result":
        return f"  -> {p['summary']}"
    if t == "patch_proposed":
        tag = f", {len(p['fromMemoryLines'])} lines from memory" if p.get("fromMemoryLines") else ""
        return f"fix proposed for {p['patch']['path']} (attempt {p['attempt']}{tag})"
    if t == "verification":
        r = p["result"]
        passed = sum(x["passed"] for x in r["tests"])
        failed = [x["name"] for x in r["tests"] if not x["passed"]]
        return f"verification: {r['status']} {passed}/{len(r['tests'])}" + (
            f"; failed: {', '.join(failed)}" if failed else ""
        )
    if t == "memory_outcome":
        return f"memory: {p['message']}"
    if t == "run_finished":
        return f"FINISHED {p['outcome'].upper()}: {p['summary']}"
    if t == "error":
        return f"note: {p['message']}"
    return t


def pick_runner(choice: str):
    from contracts.fakes import FakeRunner

    if choice == "fake":
        return FakeRunner(), "FakeRunner"
    from runner.sandbox import LocalRunner

    if choice == "local":
        return LocalRunner(), "LocalRunner"
    try:
        from pymongo import MongoClient

        from core.config import get_settings

        uri = get_settings().fixture_mongodb_uri.get_secret_value()
        MongoClient(uri, serverSelectionTimeoutMS=1500).admin.command("ping")
        return LocalRunner(), "LocalRunner"
    except Exception:  # noqa: BLE001
        say(f"(fixture database unreachable: using FakeRunner. For the real runner: {FIXTURE_HINT})")
        return FakeRunner(), "FakeRunner"


def pick_store(choice: str, seed: bool):
    from contracts.fakes import FakeMemoryStore

    if choice == "fake":
        return FakeMemoryStore(seed_example=seed), "FakeMemoryStore"
    from core.config import get_settings

    try:
        from memory.store import AtlasMemoryStore

        if not get_settings().voyage_api_key.get_secret_value():
            raise RuntimeError("VOYAGE_API_KEY is not set")
        return AtlasMemoryStore(), "AtlasMemoryStore"
    except RuntimeError as e:
        if choice == "atlas":
            raise SystemExit(f"AtlasMemoryStore: {e}") from None
        say(f"(Atlas memory not ready: {e}. Using FakeMemoryStore{' seeded with the Earn memory' if seed else ''}.)")
        return FakeMemoryStore(seed_example=seed), "FakeMemoryStore"


def git_revision() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True)
        return out.stdout.strip() or "unknown"
    except OSError:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one Traceback investigation from the command line.")
    parser.add_argument("--case", required=True, help="case id: A, B, B2, B3, C, D, P")
    parser.add_argument("--team", required=True, choices=sorted(TEAMS))
    parser.add_argument("--memory", default="real", choices=["real", "off", "placebo"])
    parser.add_argument("--runner", default="auto", choices=["auto", "local", "fake"])
    parser.add_argument("--store", default="auto", choices=["auto", "atlas", "fake"])
    parser.add_argument("--no-seed", action="store_true", help="fake store starts empty")
    parser.add_argument("--json", action="store_true", help="print the RunView as JSON at the end")
    args = parser.parse_args(argv)

    sys.path.insert(0, str(ROOT))
    from agent.events import EventSink
    from agent.llm import get_llm
    from agent.loop import NotAuthorized, run_investigation
    from contracts.models import CaseManifest, Principal
    from core.clock import new_id

    manifest_path = ROOT / "cases" / args.case / "manifest.json"
    if not manifest_path.exists():
        raise SystemExit(f"No case {args.case}: {manifest_path} not found.")
    case = CaseManifest.model_validate(json.loads(manifest_path.read_text(encoding="utf-8")))
    principal = Principal(**TEAMS[args.team])
    try:
        llm = get_llm()
    except RuntimeError as e:
        raise SystemExit(str(e)) from None
    runner, runner_name = pick_runner(args.runner)
    store, store_name = pick_store(args.store, seed=not args.no_seed)
    say(f"case {case.case_id} · team {args.team} · memory {args.memory} · {runner_name} · {store_name} · {llm.model}")

    sink = EventSink(new_id("run"), on_event=lambda e: say(f"{e.seq:>2}. {describe(e)}"))
    try:
        view = run_investigation(
            principal, case, store, runner, llm, memory_mode=args.memory, sink=sink, revision=git_revision()
        )
    except NotAuthorized as e:
        raise SystemExit(f"Refused: {e}") from None
    if args.json:
        print(view.model_dump_json(by_alias=True, indent=2))
    return 0 if view.outcome == "verified" else 1


if __name__ == "__main__":
    raise SystemExit(main())
