"""R10 ablation harness (evals/run_ablation.py): isolation naming and cleanup, placebo validation,
scoring from recorded event streams, and results.md. No Atlas, no LLM."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pymongo.errors import OperationFailure

from evals import run_ablation as ab

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = json.loads((ROOT / "contracts" / "sample_run_events.json").read_text(encoding="utf-8"))
LABELS_B = ab.load_labels("B")

# =========================================================================== isolation


def test_eval_db_names_are_unique_prefixed_and_safe():
    plan = ab.plan_runs(["B", "B2", "B3"], ["off", "placebo", "real"], 2, "1114153000")
    names = [p.db for p in plan]
    assert len(plan) == 18 and len(set(names)) == 18
    assert names[0] == "traceback_eval_1114153000_b_off_1"
    assert all(n.startswith(ab.EVAL_PREFIX) and len(n) <= 63 and n == n.lower() for n in names)
    assert [(p.case, p.arm) for p in plan[:3]] == [("B", "off"), ("B", "placebo"), ("B", "real")]


@pytest.mark.parametrize("name", ["traceback_demo", "traceback_p1", "traceback_p2", "traceback_p3",
                                  "traceback_dev", "admin", "traceback_eval_", "traceback_eval_X", "x" * 70])
def test_refuses_non_eval_databases(name):
    with pytest.raises(ValueError):
        ab.assert_eval_db(name)


class FakeDb:
    def __init__(self, colls):
        self.colls = list(colls)

    def list_collection_names(self):
        return list(self.colls)

    def drop_collection(self, name):
        self.colls.remove(name)


class FakeClient:
    """Like the Atlas app user: dropDatabase is not authorized."""

    def __init__(self, allow_drop_database=False):
        self.allow = allow_drop_database
        self.dbs = {}
        self.dropped = []

    def __getitem__(self, name):
        return self.dbs.setdefault(name, FakeDb(["memories", "runs", "run_events"]))

    def drop_database(self, name):
        if not self.allow:
            raise OperationFailure("not authorized", code=13)
        self.dropped.append(name)


def test_drop_falls_back_to_dropping_collections():
    client = FakeClient()
    assert ab.drop_eval_db(client, "traceback_eval_1_b_off_1") == "dropped (collections)"
    assert client["traceback_eval_1_b_off_1"].list_collection_names() == []
    ok = FakeClient(allow_drop_database=True)
    assert ab.drop_eval_db(ok, "traceback_eval_1_b_off_1") == "dropped"


def test_drop_never_touches_the_demo_database():
    client = FakeClient(allow_drop_database=True)
    with pytest.raises(ValueError):
        ab.drop_eval_db(client, "traceback_demo")
    assert client.dropped == [] and client.dbs == {}


def test_every_database_is_dropped_even_when_runs_fail():
    plan = ab.plan_runs(["B"], ["off", "placebo", "real"], 1, "1")
    dropped = []

    def run_one(p):
        if p.arm == "placebo":
            raise RuntimeError("worker crashed")
        return {"case": p.case, "arm": p.arm, "repeat": p.repeat, "db": p.db, "events": []}

    recs = ab.execute_plan(plan, run_one, lambda n: dropped.append(n) or "dropped", progress=lambda _: None)
    assert dropped == [p.db for p in plan]
    assert recs[1]["error"].startswith("RuntimeError") and all(r["cleanup"] == "dropped" for r in recs)


def test_keep_skips_the_drop_and_interrupts_still_clean_up():
    plan = ab.plan_runs(["B"], ["off", "real"], 1, "1")
    dropped = []
    recs = ab.execute_plan(plan, lambda p: {"events": []}, lambda n: dropped.append(n), keep=True,
                           progress=lambda _: None)
    assert dropped == [] and {r["cleanup"] for r in recs} == {"kept (--keep)"}

    def interrupted(p):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        ab.execute_plan(plan, interrupted, lambda n: dropped.append(n) or "dropped", progress=lambda _: None)
    assert dropped == [plan[0].db]


# =========================================================================== placebos


def test_placebo_file_is_valid_and_length_matched():
    raw = ab.load_placebo_file()
    report = ab.validate_placebos(raw, ab.real_memory_lengths())
    assert report["ok"], report["problems"]
    assert 3 <= len(report["items"]) <= 5
    for it in report["items"]:
        assert all(abs(r - 1) <= 0.15 for r in it["ratios"].values())


def test_placebo_file_loads_through_the_loops_own_reader():
    loop = pytest.importorskip("agent.loop")
    from contracts.models import Observations

    obs = Observations(incident_id="inc_abc", repository_id="payments-webhooks", summary="x")
    picked = loop._load_placebo(obs)
    raw = ab.load_placebo_file()
    assert picked is not None and picked.memory_id == ab.placebo_for("inc_abc", raw)["memoryId"]


def test_only_prompt_fields_are_length_gated():
    """retrieval_text never reaches the prompt, so a recall-text change can't invalidate the placebos."""
    raw = ab.load_placebo_file()
    ref = ab.real_memory_lengths()
    halved = {**ref, "retrieval_text": max(1, ref["retrieval_text"] // 2)}
    report = ab.validate_placebos(raw, halved)
    assert report["ok"], report["problems"]
    assert all("retrieval_text" in item["ratios"] for item in report["items"]), "still reported"

    off = {**ref, "injected": ref["injected"] * 2}
    assert any("injected length" in p for p in ab.validate_placebos(raw, off)["problems"])


def test_placebo_validation_catches_shape_length_count_and_topic():
    ref = ab.real_memory_lengths()
    raw = ab.load_placebo_file()
    short = copy.deepcopy(raw)
    short[0]["resolutionPatch"]["newContent"] = "x = 1\n"
    assert any("patch length" in p for p in ab.validate_placebos(short, ref)["problems"])

    broken = copy.deepcopy(raw)
    del broken[1]["expiresAt"]
    assert any("not a MemoryCandidate" in p for p in ab.validate_placebos(broken, ref)["problems"])

    on_topic = copy.deepcopy(raw)
    on_topic[2]["confirmedCause"] = on_topic[2]["confirmedCause"][:-10] + " E11000 xx."
    assert any("vocabulary" in p for p in ab.validate_placebos(on_topic, ref)["problems"])

    assert not ab.validate_placebos(raw[:2], ref)["ok"]
    assert not ab.validate_placebos({"not": "a list"}, ref)["ok"]


# =========================================================================== scoring


def record(events, arm="real", case="B", **extra):
    for e in events:
        if e["type"] == "run_started":
            e["payload"]["memoryMode"] = arm
    view = {"model": "claude-x", "promptVersion": "system_v1",
            "budget": {"toolCalls": 2, "maxToolCalls": 8, "maxPatchAttempts": 2, "deadlineSeconds": 120}}
    return {"case": case, "arm": arm, "repeat": 1, "db": "traceback_eval_1_b_x_1", "runId": "run_sample_b",
            "runView": view, "events": events, **extra}


def sample(arm="real"):
    return record(copy.deepcopy(SAMPLE), arm)


def failed_verification(ev, attempt):
    ev = copy.deepcopy(ev)
    ev["payload"]["attempt"] = attempt
    res = ev["payload"]["result"]
    res["status"], res["afterPassed"] = "failed", False
    res["tests"][2]["passed"] = False
    return ev


def renumber(events):
    for i, e in enumerate(events, 1):
        e["seq"] = i
    return events


def test_sample_stream_scores_as_verified_on_attempt_1():
    s = ab.score_run(sample(), LABELS_B)
    assert s["validity"] == "valid" and s["outcome"] == "verified" and s["outcomeAsLabelled"]
    assert s["verifiedOnAttempt1"] and s["verifiedAttempt"] == 1 and s["attempts"] == 1
    assert s["toolCalls"] == 2  # one read_file + one propose_fix, as evals/calibrate.py counts
    assert s["failingTestsLastAttempt"] == 0 and s["testsTotalLastAttempt"] == 7
    assert s["memoryUsed"] == "mem_webhook_replay" and s["recallCount"] == 1


def test_verified_on_attempt_2():
    ev = copy.deepcopy(SAMPLE)
    patch = next(e for e in ev if e["type"] == "patch_proposed")
    verif = next(e for e in ev if e["type"] == "verification")
    patch2 = copy.deepcopy(patch)
    patch2["payload"]["attempt"] = 2
    verif2 = copy.deepcopy(verif)
    verif2["payload"]["attempt"] = 2
    i = ev.index(verif)
    ev[i] = failed_verification(verif, 1)
    ev[i + 1:i + 1] = [patch2, verif2]
    ev[-1]["payload"]["attempt"] = 2
    s = ab.score_run(record(renumber(ev)), LABELS_B)
    assert s["validity"] == "valid" and s["verified"] and not s["verifiedOnAttempt1"]
    assert s["verifiedAttempt"] == 2 and s["attempts"] == 2 and s["toolCalls"] == 3
    assert s["failingTestNamesAttempt1"] == ["test_replay_recorded_for_reconciliation"]
    assert s["failingTestsLastAttempt"] == 0


def test_escalated_run_is_valid_but_not_verified():
    ev = copy.deepcopy(SAMPLE)
    verif = next(e for e in ev if e["type"] == "verification")
    ev[ev.index(verif)] = failed_verification(verif, 1)
    ev = [e for e in ev if e["type"] != "memory_outcome"]
    ev[-1]["payload"].update(outcome="escalated", testsPassed=7)
    s = ab.score_run(record(renumber(ev), arm="off"), LABELS_B)
    assert s["validity"] == "valid" and s["outcome"] == "escalated" and not s["outcomeAsLabelled"]
    assert not s["verified"] and not s["verifiedOnAttempt1"] and s["failingTestsLastAttempt"] == 1


def _crashed(message, arm="off"):
    ev = copy.deepcopy(SAMPLE[:2])
    ev.append({"runId": "run_sample_b", "seq": 3, "type": "error", "payload": {"message": message},
               "at": "2026-11-14T15:00:09Z"})
    ev.append({"runId": "run_sample_b", "seq": 4, "type": "run_finished", "at": "2026-11-14T15:00:10Z",
               "payload": {"outcome": "unresolved", "seenBefore": False, "summary": "No fix was verified."}})
    return record(ev, arm=arm)


def test_infrastructure_error_is_error_not_a_result():
    s = ab.score_run(_crashed("LLM call failed: APIConnectionError: timed out"), LABELS_B)
    assert s["validity"] == "ERROR" and s["outcome"] == "unresolved"


def test_llm_401_is_invalid():
    msg = "LLM call failed: AuthenticationError: Error code: 401 - invalid x-api-key"
    for arm in ("off", "placebo", "real"):
        assert ab.score_run(_crashed(msg, arm), LABELS_B)["validity"] == "INVALID"


def test_missing_placebo_is_invalid_never_placebo():
    ev = copy.deepcopy(SAMPLE)
    ev = [e for e in ev if e["type"] not in ("recall", "precondition_check", "memory_outcome")]
    ev.insert(2, {"runId": "run_sample_b", "seq": 0, "type": "error", "at": "2026-11-14T15:00:09Z",
                  "payload": {"message": "placebo mode: placebo_memories.json missing; running without"}})
    s = ab.score_run(record(renumber(ev), arm="placebo"), LABELS_B, ab.load_placebo_file())
    assert s["validity"] == "INVALID" and "placebo not injected" in s["reasons"][0]
    assert ab.summarize([s], ["placebo"])["placebo"]["valid"] == 0


def test_placebo_run_records_which_placebo_was_injected():
    raw = ab.load_placebo_file()
    ev = [e for e in copy.deepcopy(SAMPLE) if e["type"] not in ("recall", "precondition_check", "memory_outcome")]
    s = ab.score_run(record(renumber(ev), arm="placebo"), LABELS_B, raw)
    assert s["validity"] == "valid" and s["placeboMemoryId"] == ab.placebo_for("inc_sample_b", raw)["memoryId"]


def test_wrong_mode_and_fake_runner_are_invalid():
    rec = sample("real")
    rec["events"][0]["payload"]["memoryMode"] = "off"
    assert ab.score_run(rec, LABELS_B)["validity"] == "INVALID"
    deps = {"available": True, "runner": "FakeRunner", "store": "AtlasMemoryStore", "storeDb": "traceback_p3",
            "expectedDb": "traceback_eval_1_b_real_1"}
    problems = ab.deps_problems(deps)
    assert len(problems) == 2
    bad = ab.failed_record(ab.PlannedRun("B", "real", 1, "traceback_eval_1_b_real_1"), "RuntimeError: x")
    bad["invalidReasons"] = problems
    assert ab.score_run(bad, LABELS_B)["validity"] == "INVALID"


def test_recall_failure_invalidates_the_real_arm():
    ev = copy.deepcopy(SAMPLE[:2])
    ev.append({"runId": "r", "seq": 3, "type": "error", "at": "2026-11-14T15:00:09Z",
               "payload": {"message": "Recall unavailable (OperationFailure: x); continuing without memory"}})
    assert ab.score_run(record(ev, arm="real"), LABELS_B)["validity"] == "INVALID"


def test_worker_failure_without_events_is_error():
    rec = ab.failed_record(ab.PlannedRun("B", "off", 1, "traceback_eval_1_b_off_1"), "RuntimeError: no Atlas")
    assert ab.score_run(rec, LABELS_B)["validity"] == "ERROR"


def test_worker_runs_with_the_real_runner_atlas_and_no_promotion(monkeypatch):
    """The parent's .env can't loosen these: AGENT_RUNNER/STORE refuse fakes, AGENT_PROMOTE keeps memory fixed."""
    monkeypatch.setenv("AGENT_RUNNER", "auto")
    monkeypatch.setenv("AGENT_PROMOTE", "true")
    seen = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs["env"])
        raise ab.subprocess.TimeoutExpired(cmd, 0)

    monkeypatch.setattr(ab.subprocess, "run", fake_run)
    run_one = ab.subprocess_run_one(model=None, timeout_s=1, wait_index_s=1)
    with pytest.raises(ab.subprocess.TimeoutExpired):
        run_one(ab.PlannedRun("B", "off", 1, "traceback_eval_1_b_off_1"))
    expected = {"AGENT_RUNNER": "local", "AGENT_STORE": "atlas", "AGENT_PROMOTE": "false"}
    assert {k: seen[k] for k in expected} == expected
    assert seen["MONGODB_DB"] == "traceback_eval_1_b_off_1"


# =========================================================================== results


def test_results_markdown_has_raw_counts_and_no_percentages(tmp_path):
    raw = ab.load_placebo_file()
    placebo_ev = [e for e in copy.deepcopy(SAMPLE) if e["type"] not in ("recall", "precondition_check",
                                                                        "memory_outcome")]
    escalated = copy.deepcopy(SAMPLE)
    v = next(e for e in escalated if e["type"] == "verification")
    escalated[escalated.index(v)] = failed_verification(v, 1)
    escalated[-1]["payload"]["outcome"] = "escalated"
    recs = [record(escalated, arm="off"), record(renumber(placebo_ev), arm="placebo"), sample("real"),
            sample("real"), _crashed("LLM call failed: AuthenticationError: 401", "off")]
    recs[3]["case"] = "B2"
    labels = {"B": LABELS_B, "B2": ab.load_labels("B2")}
    scores = [ab.score_run(r, labels[r["case"]], raw) for r in recs]
    summary = ab.summarize(scores, ["off", "placebo", "real"])
    assert summary["real"]["verifiedOnAttempt1"] == 2 and summary["off"]["valid"] == 1
    meta = {"cases": ["B", "B2"], "repeats": 1, "isolation": "per-run databases.", "generatedAt": "now",
            "revision": {"git": "abc1234", "fixtureTree": "f00", "trustedTestsTree": "t00", "uncommittedChanges": []},
            "fairness": ab.fairness(scores)}
    report = ab.validate_placebos(raw, ab.real_memory_lengths())
    md, js = ab.write_results(meta, recs, scores, summary, report, tmp_path)
    text = md.read_text(encoding="utf-8")
    assert "%" not in text
    assert "| verified on attempt 1 | 0/1 | 1/1 | 2/2 |" in text
    assert "| valid runs | 1/2 | 1/1 | 2/2 |" in text
    assert "| INVALID / ERROR runs (not counted) | 1 / 0 | 0 / 0 | 0 / 0 |" in text
    assert "`run_sample_b`" in text and "LLM rejected the API key" in text
    assert "| real (Earn, case A) | 296 | 245 | 880 | 1125 |" in text
    data = json.loads(js.read_text(encoding="utf-8"))
    assert len(data["runs"]) == 5 and data["summary"]["real"]["verified"] == 2


def test_dry_run_needs_no_atlas_or_llm(capsys):
    assert ab.main(["--dry-run", "--cases", "B", "--arms", "off", "placebo", "real"]) == 0
    out = capsys.readouterr().out
    assert "dry run: nothing executed" in out and "traceback_eval_" in out and "_b_real_1" in out
