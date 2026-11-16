"""Calibration: does the agent find the team convention on its own?

    uv run python evals/calibrate.py --case B --memory off --runs 3
    uv run python evals/calibrate.py --case B --memory off --runs 3 --model claude-haiku-5-5
    uv run python evals/calibrate.py --case B --memory real --runs 3      # after case A earned the memory

Runs the real agent N times with promotion disabled, so the memory store never changes. Prints one row
per run: verified on attempt 1?, attempts, tool calls, files read, searches, and the tests that failed
on attempt 1. The story needs: memory off -> attempt 1 usually fails
test_replay_recorded_for_reconciliation; memory real -> attempt 1 passes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.events import EventSink  # noqa: E402
from agent.llm import get_llm  # noqa: E402
from agent.loop import run_investigation  # noqa: E402
from agent.run import TEAMS, git_revision, pick_runner, pick_store  # noqa: E402
from contracts.models import CaseManifest, Principal  # noqa: E402
from core.clock import new_id  # noqa: E402


def summarize(events) -> dict:
    reads = [
        e.payload["args"].get("path", "") for e in events if e.type == "tool_call" and e.payload["tool"] == "read_file"
    ]
    searches = [
        e.payload["args"].get("query", "")
        for e in events
        if e.type == "tool_call" and e.payload["tool"] == "search_code"
    ]
    verifications = [e.payload for e in events if e.type == "verification"]
    first = verifications[0]["result"] if verifications else None
    finished = next((e.payload for e in events if e.type == "run_finished"), {})
    return {
        "attempt1": bool(first and first["status"] == "passed"),
        "outcome": finished.get("outcome"),
        "attempts": len(verifications),
        "tool_calls": sum(e.type in ("tool_call", "patch_proposed") for e in events),
        "reads": reads,
        "searches": searches,
        "docs_opened": [r for r in reads if r.startswith("docs/")],
        "failed_on_attempt1": [t["name"] for t in (first or {}).get("tests", []) if not t["passed"]],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Calibrate: how often is the fix verified on attempt 1?")
    parser.add_argument("--case", default="B")
    parser.add_argument("--team", default="payments", choices=sorted(TEAMS))
    parser.add_argument("--memory", default="off", choices=["off", "real", "placebo"])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--model", default=None, help="override LLM_MODEL, e.g. claude-haiku-5-5")
    parser.add_argument("--runner", default="auto", choices=["auto", "local", "fake"])
    parser.add_argument("--store", default="auto", choices=["auto", "atlas", "fake"])
    args = parser.parse_args(argv)

    case = CaseManifest.model_validate(json.loads((ROOT / "cases" / args.case / "manifest.json").read_text()))
    principal = Principal(**TEAMS[args.team])
    try:
        llm = get_llm(args.model)
    except RuntimeError as e:
        raise SystemExit(str(e)) from None
    runner, runner_name = pick_runner(args.runner)
    store, store_name = pick_store(args.store, seed=True)
    print(f"calibrate: case {case.case_id} · memory {args.memory} · {llm.model} · {runner_name} · {store_name}\n")

    rows = []
    for i in range(1, args.runs + 1):
        sink = EventSink(new_id("cal"))
        run_investigation(
            principal,
            case,
            store,
            runner,
            llm,
            memory_mode=args.memory,
            sink=sink,
            promote=False,
            revision=git_revision(),
        )
        row = summarize(sink.events)
        rows.append(row)
        failed = ", ".join(row["failed_on_attempt1"]) or "-"
        print(
            f"run {i}: attempt1={'PASS' if row['attempt1'] else 'fail'} outcome={row['outcome']} "
            f"attempts={row['attempts']} tool_calls={row['tool_calls']}\n"
            f"       read={row['reads']} searched={row['searches']}\n"
            f"       failed on attempt 1: {failed}"
        )

    passes = sum(r["attempt1"] for r in rows)
    docs = sum(bool(r["docs_opened"]) for r in rows)
    print(f"\nverified on attempt 1: {passes} of {len(rows)} · opened docs/: {docs} of {len(rows)}")
    if args.memory == "off" and passes == len(rows):
        print("-> The agent finds the convention without memory every time: bury it deeper or use a smaller model.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
