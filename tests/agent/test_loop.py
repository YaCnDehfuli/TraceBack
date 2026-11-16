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


def test_refused_memory_is_named_even_when_the_fix_then_verifies():
    store = FakeMemoryStore()
    view, sink = run("C", store, [[("propose_fix", fix("A"))]])
    assert view.outcome == "verified" and not view.seen_before
    assert (
        sink.events[-1]
        .payload["summary"]
        .startswith("A similar memory didn't apply (duplicate key is `customer_id`). Fix verified on the first attempt")
    )


def test_brief_does_not_list_the_docs():
    captured = {}

    def first(messages):
        captured["brief"] = messages[0]["content"]
        return [("propose_fix", fix("B"))]

    run("B", FakeMemoryStore(), [first], memory_mode="off", promote=False)
    assert "RUNBOOK" not in captured["brief"] and "docs/" not in captured["brief"]
    assert "list_files" in captured["brief"]


def test_calibration_summary_reads_the_timeline():
    import importlib.util

    spec = importlib.util.spec_from_file_location("calibrate", ROOT / "evals" / "calibrate.py")
    calibrate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(calibrate)
    script = [
        [("read_file", {"path": "app/webhooks.py"})],
        [("propose_fix", fix("B", without_convention=True))],
        [("propose_fix", fix("B"))],
    ]
    _, sink = run("B", FakeMemoryStore(), script, memory_mode="off", promote=False)
    row = calibrate.summarize(sink.events)
    assert row["attempt1"] is False and row["attempts"] == 2 and row["outcome"] == "verified"
    assert row["failed_on_attempt1"] == ["test_replay_recorded_for_reconciliation"]
    assert row["reads"] == ["app/webhooks.py"] and row["docs_opened"] == []


# ---------------------------------------------------------------- receipts, placebo, escalation


class _StoreSays(FakeMemoryStore):
    """A store whose record_use returns a fixed outcome, to prove the receipt follows the store."""

    def __init__(self, outcome):
        super().__init__()
        self.outcome = outcome

    def record_use(self, *args, **kw):
        super().record_use(*args, **kw)
        return self.outcome


def outcomes(sink) -> list[str]:
    return [e.payload["outcome"] for e in sink.events if e.type == "memory_outcome"]


def test_receipt_reports_what_the_store_did_not_what_we_expected():
    _, sink = run("B", _StoreSays(None), [[("propose_fix", fix("B"))]])
    assert outcomes(sink) == []  # verified, but the store changed nothing (renewal off / expired mid-run)
    _, sink = run("B", _StoreSays("renewed"), [[("propose_fix", fix("B"))]])
    assert outcomes(sink) == ["renewed"]


def test_fake_store_disputes_when_conditions_held_but_the_fix_failed():
    store = FakeMemoryStore()
    bad = fix("B", without_convention=True)
    view, sink = run("B", store, [[("propose_fix", bad)], [("propose_fix", bad)]], promote=False)
    assert view.outcome == "escalated" and outcomes(sink) == ["disputed"]
    assert not store.memories  # paused: no longer recalled


def test_placebo_is_named_in_a_recall_event_and_never_recorded(tmp_path, monkeypatch):
    import agent.loop as loop

    seed = FakeMemoryStore().memories
    placebo = next(iter(seed.values())).candidate.model_copy(update={"memory_id": "placebo_x"})
    path = tmp_path / "placebo_memories.json"
    path.write_text(json.dumps([placebo.model_dump(by_alias=True, mode="json")]))
    monkeypatch.setattr(loop, "PLACEBO_FILE", path)
    store = FakeMemoryStore()
    view, sink = run("B", store, [[("propose_fix", fix("B"))]], memory_mode="placebo", promote=False)
    recall = next(e for e in sink.events if e.type == "recall").payload
    assert recall["count"] == 1 and recall["memories"][0]["memoryId"] == "placebo_x"
    assert store.uses == [] and outcomes(sink) == [] and not view.seen_before


def test_missing_placebo_file_says_so_and_runs_without(tmp_path, monkeypatch):
    import agent.loop as loop

    monkeypatch.setattr(loop, "PLACEBO_FILE", tmp_path / "nope.json")
    _, sink = run("B", FakeMemoryStore(), [[("propose_fix", fix("B"))]], memory_mode="placebo", promote=False)
    assert "recall" not in types(sink)
    assert any(e.type == "error" and "placebo" in e.payload["message"] for e in sink.events)


def test_escalation_summary_is_copyable_and_says_why():
    _, sink = run("C", FakeMemoryStore(), [[("propose_fix", fix("A", without_convention=True))], "I am not sure."])
    done = sink.events[-1].payload
    assert done["outcome"] == "escalated"
    text = done["escalation"]
    assert "duplicate key is `customer_id`" in text and "run run_test" in text and "Last proposed fix" in text


def test_verified_runs_have_no_escalation():
    _, sink = run("B", FakeMemoryStore(), [[("propose_fix", fix("B"))]])
    assert sink.events[-1].payload["escalation"] is None


def test_corrections_reach_the_agent():
    from agent.loop import _memory_block

    mem = next(iter(FakeMemoryStore().memories.values())).candidate
    assert "does NOT apply to: unique index on a non-event field" in _memory_block(mem)
