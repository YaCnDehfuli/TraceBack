"""The agent loop end to end with a scripted LLM, FakeRunner and FakeMemoryStore (no keys, no databases)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent.budgets import Budget
from agent.llm import ScriptedLLM
from agent.loop import NotAuthorized, run_investigation
from agent.workspace import PathRefused, Workspace
from contracts.fakes import FakeMemoryStore, FakeRunner
from contracts.models import CaseManifest, Principal

ROOT = Path(__file__).resolve().parents[2]
PAYMENTS = Principal(tenant_id="demo-org", team_id="team-payments", authorized_repos=["payments-webhooks"])
PLATFORM = Principal(tenant_id="demo-org", team_id="team-platform", authorized_repos=["platform-webhooks"])


def case(case_id: str) -> CaseManifest:
    return CaseManifest.model_validate(json.loads((ROOT / "cases" / case_id / "manifest.json").read_text()))


def fix(case_id: str, without_convention: bool = False) -> dict:
    content = (ROOT / "cases" / case_id / "reference" / "webhooks.py").read_text()
    if without_convention:
        content = "\n".join(line for line in content.splitlines() if "mark_replayed" not in line) + "\n"
    return {"path": "app/webhooks.py", "new_content": content, "cause": "retry inserts again", "summary": "idempotent"}


def types(view_sink) -> list[str]:
    return [e.type for e in view_sink.events]


def run(case_id, store, script, principal=PAYMENTS, **kw):
    from agent.events import EventSink

    sink = EventSink("run_test")
    view = run_investigation(principal, case(case_id), store, FakeRunner(), ScriptedLLM(script), sink=sink, **kw)
    return view, sink


def test_reuse_verified_on_first_attempt_with_the_line_from_memory():
    store = FakeMemoryStore()  # seeded with the Earn memory
    view, sink = run("B", store, [[("read_file", {"path": "app/webhooks.py"})], [("propose_fix", fix("B"))]])
    assert view.outcome == "verified" and view.attempt == 1 and view.seen_before
    assert view.memory_used and view.memory_used.owner_team_id == "team-payments"
    check = next(e for e in sink.events if e.type == "precondition_check")
    assert (check.payload["held"], check.payload["total"]) == (2, 2)
    patch = next(e for e in sink.events if e.type == "patch_proposed").payload
    lines = patch["patch"]["newContent"].splitlines()
    tagged = [lines[n - 1].strip() for n in patch["fromMemoryLines"]]
    assert "ledger.mark_replayed(notification.id)" in tagged  # adapted name, still "from memory"
    assert store.uses[-1]["decision"] == "used"
    assert sink.events[-1].payload["summary"].startswith("Seen before. Fix verified on the first attempt")


def test_earn_without_memory_needs_the_runbook_and_promotes():
    store = FakeMemoryStore(seed_example=False)
    view, sink = run("A", store, [[("propose_fix", fix("A", without_convention=True))], [("propose_fix", fix("A"))]])
    assert view.outcome == "verified" and view.attempt == 2 and not view.seen_before
    failed_first = next(e for e in sink.events if e.type == "verification").payload["result"]["tests"]
    assert [t["name"] for t in failed_first if not t["passed"]] == ["test_replay_recorded_for_reconciliation"]
    outcome = [e.payload for e in sink.events if e.type == "memory_outcome"]
    assert outcome and outcome[-1]["outcome"] == "promoted"
    assert len(store.memories) == 1


def test_refuse_lookalike_with_a_plain_reason_and_no_unproven_memory():
    store = FakeMemoryStore()
    view, sink = run("C", store, [[("propose_fix", fix("A", without_convention=True))], "I am not sure.", "Done."])
    check = next(e for e in sink.events if e.type == "precondition_check").payload
    assert check["notAppliedReason"] == (
        "Not applied: duplicate key is `customer_id`; this memory requires `provider_event_id`."
    )
    assert not view.seen_before and view.outcome == "escalated"
    outcomes = [e.payload["outcome"] for e in sink.events if e.type == "memory_outcome"]
    assert outcomes == ["near_miss", "refused"]  # refused: the failed fix may not become memory
    assert store.uses[0]["decision"] == "rejected"


def test_memory_off_skips_recall():
    view, sink = run("B", FakeMemoryStore(), [[("propose_fix", fix("B"))]], memory_mode="off", promote=False)
    assert "recall" not in types(sink) and not view.seen_before and view.outcome == "verified"


def test_budget_stops_a_runaway_agent():
    view, sink = run("B", FakeMemoryStore(), [[("list_files", {})]], budget=Budget(max_tool_calls=3))
    assert view.outcome == "unresolved" and view.budget.tool_calls == 3
    assert any(e.type == "error" and "tool_calls" in e.payload["message"] for e in sink.events)


def test_identity_decides_which_apps_a_team_may_touch():
    with pytest.raises(NotAuthorized):
        run("B", FakeMemoryStore(), [[("list_files", {})]], principal=PLATFORM)


def test_workspace_path_checks_and_contents():
    ws = Workspace(case("B"))
    assert "app/webhooks.py" in ws.list_files()
    assert not any(f.startswith(("trusted_tests", "cases", "reference")) for f in ws.list_files())
    assert "handle_provider_event" in ws.original("app/webhooks.py")  # case overlay wins
    for bad in ["../.env", "/etc/passwd", "app/../../.env", "trusted_tests/test_webhooks.py", "C:\\x"]:
        with pytest.raises(PathRefused):
            ws.read(bad)
