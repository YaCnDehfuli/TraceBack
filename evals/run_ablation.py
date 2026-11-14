"""Memory ablation experiment (plan R10): did memory change the agent's behaviour, or just fill the prompt?

    uv run python -m evals.run_ablation --cases B B2 B3 --arms off placebo real --repeats 1
    uv run python -m evals.run_ablation --dry-run                       # plan + placebo check, no Atlas, no LLM
    uv run python -m evals.run_ablation --cases B --keep                # keep the throwaway databases
    uv run python -m evals.run_ablation --base-url http://localhost:8000   # a running server (no isolation)

Arms, all through the same API (POST /incidents, POST /incidents/{id}/runs?memory=..., GET /runs/{id}
and /events) and P1's loop:
- off:      no memory in the prompt.
- placebo:  one unrelated memory from evals/placebo_memories.json, length-matched to the real one and
            injected by the loop through the same prompt block (agent.loop._load_placebo / _memory_block).
- real:     normal recall; the database holds ONLY case A's Earn memory, proven by the real runner.

Isolation: every run gets its own throwaway Atlas database `traceback_eval_<stamp>_<case>_<arm>_<n>`,
created with scripts/atlas_setup.py and, for the real arm, seeded with the Earn memory through
scripts/seed_demo.earn (LocalRunner verifies case A's reference fix, then the memory service promotes
it). The run happens in a subprocess with MONGODB_DB set to that name, because core.config.get_settings,
core.db.get_client and api.runs.get_service are all cached per process. Afterwards the parent drops the
database (each collection; the app user may not dropDatabase). So a renew or dispute in one run can never
reach another, and traceback_demo / traceback_p1..p3 are never opened.

Scoring reads only facts from the event stream and cases/<id>/labels.json: the runner's verification
results, the attempt numbers, the tool calls and the final outcome. Nothing is forced or substituted.
results.md reports raw counts only ("2/3"), never percentages or significance.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import ValidationError  # noqa: E402

from contracts.models import CaseManifest, MemoryCandidate  # noqa: E402

CASES = ("B", "B2", "B3")
ARMS = ("off", "placebo", "real")
PLACEBO_FILE = ROOT / "evals" / "placebo_memories.json"
RESULTS_DIR = ROOT / "evals" / "results"

EVAL_PREFIX = "traceback_eval_"
_EVAL_NAME = re.compile(r"^traceback_eval_[a-z0-9_]+$")
# Never opened, never dropped. (The prefix check alone already excludes them; this is belt and braces.)
PROTECTED_DBS = frozenset(
    {"traceback_demo", "traceback_p1", "traceback_p2", "traceback_p3", "traceback_dev", "traceback_fixture"}
)

PLACEBO_COUNT = (3, 5)
LENGTH_TOLERANCE = 0.15
# A placebo must be about a different bug: none of the case B mechanism's vocabulary.
PLACEBO_FORBIDDEN = (
    "e11000", "duplicate", "provider_event_id", "webhook", "mark_replayed", "replay", "idempot",
    "insert_one", "unique index", "redeliver",
)

PAYMENTS_TEAM = "team-payments"
FINAL_STATUSES = ("finished", "error")


# =========================================================================== isolation


@dataclass(frozen=True)
class PlannedRun:
    case: str
    arm: str
    repeat: int
    db: str


def eval_stamp(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%m%d%H%M%S")


def eval_db_name(stamp: str, case: str, arm: str, repeat: int) -> str:
    name = f"{EVAL_PREFIX}{stamp}_{case}_{arm}_{repeat}".lower()
    assert_eval_db(name)
    return name


def assert_eval_db(name: str) -> None:
    """Only throwaway evaluation databases may be created, written or dropped by this harness."""
    if name in PROTECTED_DBS or not _EVAL_NAME.fullmatch(name) or len(name) > 63:
        raise ValueError(f"refusing to use {name!r}: not a throwaway {EVAL_PREFIX}* database")


def drop_eval_db(client: Any, name: str) -> str:
    """Drop a throwaway database. The Atlas app user lacks dropDatabase, so fall back to dropping every
    collection (a database without collections no longer exists)."""
    assert_eval_db(name)
    from pymongo.errors import OperationFailure

    try:
        client.drop_database(name)
        return "dropped"
    except OperationFailure:
        db = client[name]
        for coll in db.list_collection_names():
            db.drop_collection(coll)
        left = db.list_collection_names()
        return "dropped (collections)" if not left else f"drop incomplete: {len(left)} collection(s) left"


def plan_runs(cases: Iterable[str], arms: Iterable[str], repeats: int, stamp: str) -> list[PlannedRun]:
    """Repeat-major, then case, then arm: the three arms of a case run back to back."""
    cases, arms = list(cases), list(arms)
    return [
        PlannedRun(case, arm, n, eval_db_name(stamp, case, arm, n))
        for n in range(1, repeats + 1)
        for case in cases
        for arm in arms
    ]


def execute_plan(
    plan: list[PlannedRun],
    run_one: Callable[[PlannedRun], dict],
    drop: Callable[[str], str] | None,
    *,
    keep: bool = False,
    progress: Callable[[str], None] = print,
) -> list[dict]:
    """Run each planned run; its database is dropped afterwards even if the run fails or is interrupted."""
    records: list[dict] = []
    for i, p in enumerate(plan, 1):
        progress(f"[{i}/{len(plan)}] case {p.case}, memory={p.arm}, repeat {p.repeat} -> {p.db}")
        rec: dict | None = None
        try:
            rec = run_one(p)
        except Exception as e:  # noqa: BLE001 - one broken run never stops the experiment
            rec = failed_record(p, f"{type(e).__name__}: {str(e)[:300]}")
        finally:
            if drop is None:
                cleanup = "not managed (external server)"
            elif keep:
                cleanup = "kept (--keep)"
            else:
                try:
                    cleanup = drop(p.db)
                except Exception as e:  # noqa: BLE001
                    cleanup = f"drop failed: {type(e).__name__}: {str(e)[:120]}"
            progress(f"        cleanup: {cleanup}")
        rec["cleanup"] = cleanup
        records.append(rec)
    return records


def failed_record(p: PlannedRun, error: str) -> dict:
    return {"case": p.case, "arm": p.arm, "repeat": p.repeat, "db": p.db, "error": error,
            "runId": None, "incidentId": None, "runView": None, "events": [], "setup": {}}


# =========================================================================== the real memory and the placebos


def _length_fields(retrieval: str, cause: str, resolution: str, patch: str) -> dict[str, int]:
    """`injected` is what agent.loop._memory_block puts in the prompt: cause, resolution and proven fix."""
    return {
        "retrieval_text": len(retrieval),
        "cause_and_resolution": len(cause) + len(resolution),
        "patch": len(patch),
        "injected": len(cause) + len(resolution) + len(patch),
    }


def memory_lengths(m: MemoryCandidate) -> dict[str, int]:
    patch = m.resolution_patch.new_content if m.resolution_patch else ""
    return _length_fields(m.retrieval_text, m.confirmed_cause, m.resolution_summary, patch)


def real_memory_lengths() -> dict[str, int]:
    """The Earn memory, built from exactly what scripts/seed_demo.earn promotes (no Atlas needed)."""
    from agent.observe import observations_from_case
    from scripts import seed_demo

    manifest = load_manifest(seed_demo.EARN_CASE)
    obs = observations_from_case(manifest, incident_id=seed_demo.EARN_INCIDENT)
    path = manifest.patchable_files[0]
    patch = (ROOT / "cases" / seed_demo.EARN_CASE / "reference" / Path(path).name).read_text("utf-8")
    return _length_fields(obs.summary, seed_demo.EARN_CAUSE, seed_demo.EARN_RESOLUTION, patch)


def doc_lengths(doc: dict) -> dict[str, int]:
    """Lengths of a stored memory document (memories collection)."""
    res = doc.get("resolution") or {}
    patch = (res.get("patch") or {}).get("newContent") or ""
    return _length_fields(doc.get("retrievalText") or "", doc.get("confirmedCause") or "",
                          res.get("summary") or "", patch)


def validate_placebos(raw: Any, reference: dict[str, int], tolerance: float = LENGTH_TOLERANCE) -> dict:
    """Shape (MemoryCandidate), count, unrelatedness and length matching. `ok` is False on any problem."""
    problems: list[str] = []
    items: list[dict] = []
    if not isinstance(raw, list):
        return {"ok": False, "problems": ["placebo file must be a JSON list"], "items": [], "reference": reference}
    lo, hi = PLACEBO_COUNT
    if not lo <= len(raw) <= hi:
        problems.append(f"need {lo}-{hi} placebo memories, found {len(raw)}")
    seen: set[str] = set()
    for i, obj in enumerate(raw):
        try:
            m = MemoryCandidate.model_validate(obj)
        except ValidationError as e:
            problems.append(f"item {i}: not a MemoryCandidate ({e.error_count()} error(s))")
            continue
        if m.memory_id in seen:
            problems.append(f"{m.memory_id}: duplicate memoryId")
        seen.add(m.memory_id)
        if m.resolution_patch is None:
            problems.append(f"{m.memory_id}: no resolutionPatch (the real memory injects one)")
        lengths = memory_lengths(m)
        ratios = {k: round(lengths[k] / reference[k], 3) if reference[k] else None for k in lengths}
        for k, r in ratios.items():
            if r is None or abs(r - 1) > tolerance:
                problems.append(f"{m.memory_id}: {k} length {lengths[k]} vs real {reference[k]} "
                                f"(ratio outside {1 - tolerance:.2f}-{1 + tolerance:.2f})")
        text = " ".join([m.retrieval_text, m.confirmed_cause, m.resolution_summary,
                         m.resolution_patch.new_content if m.resolution_patch else ""]).lower()
        hits = [t for t in PLACEBO_FORBIDDEN if t in text]
        if hits:
            problems.append(f"{m.memory_id}: mentions the real bug's vocabulary ({', '.join(hits)})")
        items.append({"memoryId": m.memory_id, "repositoryId": m.repository_id, "lengths": lengths,
                      "ratios": ratios})
    return {"ok": not problems, "problems": problems, "items": items, "reference": reference,
            "tolerance": tolerance}


def load_placebo_file(path: Path = PLACEBO_FILE) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def placebo_for(incident_id: str, raw: list[dict]) -> dict | None:
    """Which placebo the loop injects: mirrors agent.loop._load_placebo (sum of the incident id's code
    points, modulo the number of placebos). The loop emits no event naming it, so we recompute it."""
    if not raw or not incident_id:
        return None
    return raw[sum(map(ord, incident_id)) % len(raw)]


# =========================================================================== cases, labels, revision


def load_manifest(case_id: str) -> CaseManifest:
    return CaseManifest.model_validate_json((ROOT / "cases" / case_id / "manifest.json").read_text("utf-8"))


def load_labels(case_id: str) -> dict:
    return json.loads((ROOT / "cases" / case_id / "labels.json").read_text("utf-8"))


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10)
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def revision_info() -> dict:
    """Code and fixture revision. Every arm runs from this one checkout, so they are equal by construction."""
    watched = ["fixture_app", "trusted_tests", "cases", "evals/placebo_memories.json", "agent", "runner"]
    dirty = _git("status", "--porcelain", "--", *watched)
    return {
        "git": _git("rev-parse", "--short", "HEAD") or "unknown",
        "fixtureTree": _git("rev-parse", "--short", "HEAD:fixture_app") or "unknown",
        "trustedTestsTree": _git("rev-parse", "--short", "HEAD:trusted_tests") or "unknown",
        "casesTree": _git("rev-parse", "--short", "HEAD:cases") or "unknown",
        "uncommittedChanges": sorted({line[3:] for line in dirty.splitlines()}),
    }


# =========================================================================== scoring


def _attempt_of(payload: dict) -> int:
    try:
        return int(payload.get("attempt") or 0)
    except (TypeError, ValueError):
        return 0


def _verified(result: dict) -> bool:
    """VerificationResult.verified, on the JSON form."""
    return result.get("status") == "passed" and bool(result.get("beforeFailed")) and bool(result.get("afterPassed"))


# Error events that mean our infrastructure failed (agent.loop / api.runs wording), not the agent.
INFRA_ERRORS = ("LLM call failed", "The run stopped", "Recall unavailable")


def _is_llm_auth_error(message: str) -> bool:
    m = message.lower()
    return message.startswith("LLM call failed") and ("authenticationerror" in m or "401" in m)


def score_run(rec: dict, labels: dict, placebos: list[dict] | None = None) -> dict:
    """Facts from one run's events. validity: valid | INVALID (the arm's condition did not hold) | ERROR
    (no agent behaviour to score). Only valid runs are counted."""
    arm = rec.get("arm")
    events = sorted(rec.get("events") or [], key=lambda e: e.get("seq", 0))
    by_type: dict[str, list[dict]] = {}
    for e in events:
        by_type.setdefault(e.get("type", ""), []).append(e.get("payload") or {})
    started = (by_type.get("run_started") or [None])[0]
    finished = (by_type.get("run_finished") or [None])[0]
    errors = [str(p.get("message", "")) for p in by_type.get("error", [])]
    verifications = sorted(by_type.get("verification", []), key=_attempt_of)
    recall = (by_type.get("recall") or [None])[0]
    view = rec.get("runView") or {}

    verified_attempt = next((_attempt_of(v) for v in verifications if _verified(v.get("result") or {})), None)
    last = (verifications[-1].get("result") or {}) if verifications else {}
    last_tests = last.get("tests") or []
    attempts = max((_attempt_of(v) for v in verifications), default=0) or len(by_type.get("patch_proposed", []))
    # Same definition as P1's evals/calibrate.py: file tools + fix proposals (what the budget charges).
    tool_calls = len(by_type.get("tool_call", [])) + len(by_type.get("patch_proposed", []))
    budget_error = next((m for m in errors if m.startswith("Budget reached")), None)

    if finished:
        outcome = finished.get("outcome") or "unknown"
    elif budget_error:
        outcome = "budget_exhausted"
    elif rec.get("timedOut"):
        outcome = "timed_out"
    else:
        outcome = "error"

    reasons: list[str] = list(rec.get("invalidReasons") or [])
    mode = (started or {}).get("memoryMode")
    llm_auth = [m for m in errors if _is_llm_auth_error(m)]
    if llm_auth:  # the LLM never answered: not agent behaviour, and never a result (#30)
        reasons.append(f"LLM rejected the API key: {llm_auth[0][:120]}")
    infra = [m for m in errors if m.startswith(INFRA_ERRORS)]
    if reasons:
        validity = "INVALID"
    elif rec.get("error") and not events:
        validity = "ERROR"
        reasons.append(rec["error"])
    else:
        if started is None:
            reasons.append("no run_started event")
        elif mode != arm:
            reasons.append(f"run_started memoryMode={mode!r}, expected {arm!r}")
        if arm == "placebo":
            placebo_errors = [m for m in errors if "placebo" in m.lower()]
            if placebo_errors:
                reasons.append(f"placebo not injected: {placebo_errors[0][:120]}")
            elif errors and not tool_calls:
                reasons.append(f"errored before the agent acted, placebo injection unconfirmed: {errors[0][:120]}")
        if arm == "real":
            recall_errors = [m for m in errors if m.startswith("Recall unavailable")]
            if recall_errors:
                reasons.append(f"recall failed: {recall_errors[0][:120]}")
        if reasons:
            validity = "INVALID"
        elif not verifications and (infra or outcome in ("error", "timed_out")):
            # P1's API ends a crashed run with run_finished(unresolved); without any verification that
            # is our infrastructure failing, not the agent.
            validity = "ERROR"
            reasons.append((infra or errors or [rec.get("error") or outcome])[0][:160])
        else:
            validity = "valid"

    placebo = placebo_for((started or {}).get("incidentId", ""), placebos or []) if arm == "placebo" else None
    expected = labels.get("expectedOutcome")
    return {
        "case": rec.get("case"),
        "arm": arm,
        "repeat": rec.get("repeat"),
        "db": rec.get("db"),
        "runId": rec.get("runId"),
        "incidentId": (started or {}).get("incidentId") or rec.get("incidentId"),
        "validity": validity,
        "reasons": reasons,
        "outcome": outcome,
        "expectedOutcome": expected,
        "outcomeAsLabelled": bool(finished) and outcome == expected,
        "verifiedOnAttempt1": verified_attempt == 1,
        "verified": verified_attempt is not None,
        "verifiedAttempt": verified_attempt,
        "attempts": attempts,
        "toolCalls": tool_calls,
        "budgetToolCalls": (view.get("budget") or {}).get("toolCalls"),
        "failingTestsLastAttempt": sum(not t.get("passed") for t in last_tests) if verifications else None,
        "testsTotalLastAttempt": len(last_tests) if verifications else None,
        "failingTestNamesAttempt1": [
            t.get("name") for t in ((verifications[0].get("result") or {}).get("tests") or []) if not t.get("passed")
        ] if verifications else [],
        "recallCount": recall.get("count") if recall else None,
        "memoryUsed": ((finished or {}).get("memoryUsed") or {}).get("memoryId"),
        "placeboMemoryId": placebo.get("memoryId") if placebo else None,
        "errors": errors,
        "runFinishedMissing": finished is None,
        "model": view.get("model"),
        "promptVersion": view.get("promptVersion"),
        "budget": {k: (view.get("budget") or {}).get(k) for k in ("maxToolCalls", "maxPatchAttempts",
                                                                   "deadlineSeconds")},
    }


def summarize(scores: list[dict], arms: Iterable[str]) -> dict[str, dict]:
    """Raw counts per arm, over valid runs only."""
    out: dict[str, dict] = {}
    for arm in arms:
        mine = [s for s in scores if s["arm"] == arm]
        valid = [s for s in mine if s["validity"] == "valid"]
        outcomes: dict[str, int] = {}
        for s in valid:
            outcomes[s["outcome"]] = outcomes.get(s["outcome"], 0) + 1
        out[arm] = {
            "runs": len(mine),
            "valid": len(valid),
            "invalid": sum(s["validity"] == "INVALID" for s in mine),
            "error": sum(s["validity"] == "ERROR" for s in mine),
            "verifiedOnAttempt1": sum(s["verifiedOnAttempt1"] for s in valid),
            "verified": sum(s["verified"] for s in valid),
            "outcomeAsLabelled": sum(s["outcomeAsLabelled"] for s in valid),
            "attempts": [s["attempts"] for s in valid],
            "toolCalls": [s["toolCalls"] for s in valid],
            "failingTestsLastAttempt": [s["failingTestsLastAttempt"] for s in valid],
            "outcomes": outcomes,
        }
    return out


def fairness(scores: list[dict]) -> dict:
    """What every run actually reported. More than one value anywhere = the arms were not run equally."""
    def distinct(key: str) -> list:
        vals = {json.dumps(s.get(key), sort_keys=True) for s in scores if s["validity"] != "ERROR"}
        return [json.loads(v) for v in sorted(vals)]

    models, prompts, budgets = distinct("model"), distinct("promptVersion"), distinct("budget")
    return {"models": models, "promptVersions": prompts, "budgets": budgets,
            "equal": len(models) <= 1 and len(prompts) <= 1 and len(budgets) <= 1}


# =========================================================================== results


def _count(n: int, d: int) -> str:
    return f"{n}/{d}"


def _list(xs: list) -> str:
    return ", ".join("n/a" if x is None else str(x) for x in xs) if xs else "none"


def render_markdown(meta: dict, scores: list[dict], summary: dict[str, dict], placebo_report: dict) -> str:
    arms = list(summary)
    fair = meta.get("fairness") or fairness(scores)
    rev = meta.get("revision") or {}
    ref = placebo_report.get("reference") or {}
    budget = (fair.get("budgets") or [{}])[0] or {}
    lines = [
        "# R10 memory ablation: results",
        "",
        f"_Generated by `evals/run_ablation.py` at {meta.get('generatedAt', 'unknown')}. Do not edit by hand._",
        "",
        "## Method",
        "",
        (
            f"Cases {', '.join(meta.get('cases', []))} were each run under three memory arms through the API "
            f"(`POST /incidents`, `POST /incidents/{{id}}/runs?memory=<arm>`, then `GET /runs/{{id}}` and "
            f"`/events`), {meta.get('repeats', 1)} time(s) per case and arm (N={meta.get('repeats', 1)}). "
            "**off**: no memory in the prompt. **placebo**: one unrelated memory (other bug types, "
            "`evals/placebo_memories.json`) injected by the loop through the same prompt block as a real "
            "memory, length-matched (each length ratio to the real memory between 0.85 and 1.15, table "
            "below). **real**: normal recall, with only case A's Earn memory in the database, proven by "
            "the real runner and promoted by the memory service "
            "(`scripts/seed_demo.earn`). "
            f"Isolation: {meta.get('isolation', 'unknown')} "
            f"Model: {', '.join(map(str, fair.get('models') or ['unknown']))}; prompt "
            f"{', '.join(map(str, fair.get('promptVersions') or ['unknown']))}; budget "
            f"{budget.get('maxToolCalls')} tool calls, {budget.get('maxPatchAttempts')} fix attempts, "
            f"{budget.get('deadlineSeconds')} s for every run"
            f"{'' if fair.get('equal') else ' (**NOT equal across runs, see results.json**)'}. "
            f"Code revision `{rev.get('git')}`, fixture tree `{rev.get('fixtureTree')}`, trusted tests "
            f"`{rev.get('trustedTestsTree')}`"
            + (f", uncommitted changes in: {', '.join(rev['uncommittedChanges'])}" if rev.get("uncommittedChanges")
               else ", no uncommitted changes to fixtures, tests, cases, agent or runner")
            + ". Scored against `cases/<id>/labels.json` from the runner's verification events only. "
            "Counts are over valid runs; INVALID (the arm's condition did not hold, e.g. placebo not "
            "injected) and ERROR (no agent behaviour to score) runs are listed but never counted. "
            "Raw counts only: with this N, no rates or significance are claimed."
        ),
        "",
        "## Raw counts per arm",
        "",
        "| | " + " | ".join(arms) + " |",
        "|---|" + "---|" * len(arms),
    ]

    def row(label: str, fn: Callable[[dict], str]) -> str:
        return f"| {label} | " + " | ".join(fn(summary[a]) for a in arms) + " |"

    lines += [
        row("valid runs", lambda s: _count(s["valid"], s["runs"])),
        row("INVALID / ERROR runs (not counted)", lambda s: f"{s['invalid']} / {s['error']}"),
        row("verified on attempt 1", lambda s: _count(s["verifiedOnAttempt1"], s["valid"])),
        row("verified at all", lambda s: _count(s["verified"], s["valid"])),
        row("outcome as labelled (`verified`)", lambda s: _count(s["outcomeAsLabelled"], s["valid"])),
        row("attempts per run", lambda s: _list(s["attempts"])),
        row("tool calls per run", lambda s: _list(s["toolCalls"])),
        row("failing tests on last attempt, per run", lambda s: _list(s["failingTestsLastAttempt"])),
        row("outcomes", lambda s: ", ".join(f"{k} {v}" for k, v in sorted(s["outcomes"].items())) or "none"),
        "",
        "## Per run",
        "",
        "| case | arm | # | run id | validity | outcome | verified on | attempts | tool calls | "
        "failing tests (last) | attempt-1 failures | memory |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for s in scores:
        memory = s["memoryUsed"] or s["placeboMemoryId"] or ("-" if s["arm"] == "off" else "none")
        if s["arm"] == "real" and s["recallCount"] is not None:
            memory = f"{memory} (recalled {s['recallCount']})"
        failing = ("n/a" if s["failingTestsLastAttempt"] is None
                   else f"{s['failingTestsLastAttempt']}/{s['testsTotalLastAttempt']}")
        lines.append(
            f"| {s['case']} | {s['arm']} | {s['repeat']} | `{s['runId'] or 'none'}` | {s['validity']} | "
            f"{s['outcome']} | {s['verifiedAttempt'] or '-'} | {s['attempts']} | {s['toolCalls']} | {failing} | "
            f"{', '.join(s['failingTestNamesAttempt1']) or '-'} | {memory} |"
        )
    notes = [s for s in scores if s["reasons"] or s["runFinishedMissing"]]
    if notes:
        lines += ["", "Notes:", ""]
        for s in notes:
            why = "; ".join(s["reasons"]) or "run_finished missing: " + ("; ".join(s["errors"])[:200] or "unknown")
            lines.append(f"- {s['case']}/{s['arm']}/{s['repeat']} ({s['validity']}): {why}")

    lines += [
        "",
        "## Placebo length matching",
        "",
        "Characters. `injected` = confirmed cause + resolution + proven fix, i.e. what the loop's memory "
        "block puts in the prompt; `retrieval_text` is matched too although it is not injected.",
        "",
        "| memory | retrieval_text | cause + resolution | patch | injected |",
        "|---|---|---|---|---|",
        f"| real (Earn, case A) | {ref.get('retrieval_text')} | {ref.get('cause_and_resolution')} | "
        f"{ref.get('patch')} | {ref.get('injected')} |",
    ]
    for it in placebo_report.get("items", []):
        ln, r = it["lengths"], it["ratios"]
        lines.append(
            f"| {it['memoryId']} | {ln['retrieval_text']} (×{r['retrieval_text']}) | "
            f"{ln['cause_and_resolution']} (×{r['cause_and_resolution']}) | {ln['patch']} (×{r['patch']}) | "
            f"{ln['injected']} (×{r['injected']}) |"
        )
    if placebo_report.get("problems"):
        lines += ["", "Placebo problems: " + "; ".join(placebo_report["problems"])]
    lines.append("")
    return "\n".join(lines)


def write_results(meta: dict, records: list[dict], scores: list[dict], summary: dict, placebo_report: dict,
                  out_dir: Path = RESULTS_DIR) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    md = out_dir / "results.md"
    js = out_dir / "results.json"
    md.write_text(render_markdown(meta, scores, summary, placebo_report), encoding="utf-8", newline="\n")
    js.write_text(json.dumps({"meta": meta, "placebos": placebo_report, "summary": summary, "scores": scores,
                              "runs": records}, indent=2, default=str) + "\n", encoding="utf-8", newline="\n")
    return md, js


# =========================================================================== driving one run through the API


def payments_api_key() -> str:
    """The demo API key of a Payments engineer (DEMO_PRINCIPALS in .env). Never printed or stored."""
    from core.config import get_settings

    for key, entry in get_settings().demo_principals.items():
        if (entry.get("teamId") == PAYMENTS_TEAM and entry.get("role", "engineer") == "engineer"
                and "payments-webhooks" in (entry.get("authorizedRepos") or [])):
            return key
    raise RuntimeError("DEMO_PRINCIPALS has no Payments engineer authorized for payments-webhooks")


def drive_run(http: Any, headers: dict, case_id: str, arm: str, revision: str, *, timeout_s: float,
              poll_s: float = 1.0) -> dict:
    """POST /incidents, POST /incidents/{id}/runs?memory=arm, poll GET /runs/{id}, then GET /events.
    `http` is a fastapi TestClient or an httpx.Client with a base_url: both have .get/.post."""
    manifest = load_manifest(case_id)
    body = {"repositoryId": manifest.repository_id, "caseId": case_id, "logs": manifest.logs,
            "request": manifest.request, "revision": revision}
    r = http.post("/incidents", headers=headers, json=body)
    r.raise_for_status()
    incident_id = r.json()["incidentId"]
    r = http.post(f"/incidents/{incident_id}/runs", headers=headers, params={"memory": arm})
    r.raise_for_status()
    run_id = r.json()["runId"]

    deadline = time.monotonic() + timeout_s
    timed_out = False
    while True:
        r = http.get(f"/runs/{run_id}", headers=headers)
        r.raise_for_status()
        view = r.json()
        if view.get("status") in FINAL_STATUSES:
            break
        if time.monotonic() > deadline:
            timed_out = True
            break
        time.sleep(poll_s)
    r = http.get(f"/runs/{run_id}/events", headers=headers)
    r.raise_for_status()
    return {"incidentId": incident_id, "runId": run_id, "runView": view, "events": r.json(), "timedOut": timed_out}


# =========================================================================== worker (one run, one database)


def prepare_db(db_name: str, arm: str, wait_index_s: int) -> dict:
    """atlas_setup on a fresh eval database, team policies as seed_demo writes them, and for the real arm
    ONLY the Earn memory, through seed_demo.earn (real runner, then the memory service's promote)."""
    assert_eval_db(db_name)
    from core.db import get_client
    from memory.policy import DEMO_POLICY
    from memory.store import AtlasMemoryStore
    from scripts import atlas_setup, seed_demo

    db = get_client()[db_name]
    if db.list_collection_names():
        raise RuntimeError(f"{db_name} is not empty; refusing to reuse it")
    atlas_setup.ensure_collections(db)
    atlas_setup.ensure_indexes(db)
    atlas_setup.ensure_vector_index(db)
    for team in seed_demo.TEAMS:  # same as seed_demo.main (which would also add the canary: not wanted here)
        db.policies.replace_one({"_id": f"{seed_demo.TENANT}:{team}"},
                                {"tenantId": seed_demo.TENANT, "teamId": team, **DEMO_POLICY}, upsert=True)
    info: dict[str, Any] = {"vectorIndexReady": None, "earnMemoryId": None, "earnSearchable": None,
                            "earnLengths": None}
    if arm == "real":
        info["vectorIndexReady"] = atlas_setup.wait_queryable(db, timeout=wait_index_s)
        store = AtlasMemoryStore(db)
        if not seed_demo.earn(store, "local", reset=False):
            raise RuntimeError("the runner did not verify case A's reference fix, so there is no Earn memory")
        doc = db.memories.find_one({"provenance.sourceIncidentId": seed_demo.EARN_INCIDENT})
        if not doc:
            raise RuntimeError("Earn memory not found after promote")
        info["earnMemoryId"] = doc["_id"]
        info["earnSeeded"] = bool(doc.get("seeded"))
        info["earnLengths"] = doc_lengths(doc)
        start = time.monotonic()
        while time.monotonic() - start < wait_index_s:
            if store.is_searchable(seed_demo.PAYMENTS, doc["_id"]):
                info["earnSearchable"] = True
                break
            time.sleep(3)
        else:
            info["earnSearchable"] = False
    info["memoriesInDb"] = db.memories.count_documents({})
    return info


def inspect_agent_deps(db_name: str) -> dict:
    """What the API will actually run with. P1's api.deps builds its runner and store once per process and
    silently falls back to FakeRunner / FakeMemoryStore when the fixture database or Atlas is unreachable;
    either would make a run meaningless, so we read the same cached object the API uses and record it."""
    try:
        from api import deps as api_deps
    except ImportError:
        return {"available": False}
    info: dict[str, Any] = {"available": True}
    try:
        d = api_deps._agent_deps()
    except Exception as e:  # noqa: BLE001 - e.g. LLM_API_KEY / LLM_MODEL missing: the API answers 503
        info["error"] = f"{type(e).__name__}: {str(e)[:200]}"
        return info
    info["runner"] = type(d.runner).__name__
    info["store"] = type(d.memory).__name__
    info["model"] = getattr(d.llm, "model", None)
    info["revision"] = d.revision
    store_db = getattr(getattr(d.memory, "db", None), "name", None)
    info["storeDb"] = store_db
    try:
        repo = api_deps.get_repo()
        info["runRepo"] = type(repo).__name__
        info["runRepoDb"] = getattr(getattr(getattr(repo, "runs", None), "database", None), "name", None)
    except Exception as e:  # noqa: BLE001
        info["runRepo"] = f"error: {type(e).__name__}"
    info["expectedDb"] = db_name
    return info


def deps_problems(deps: dict) -> list[str]:
    if not deps.get("available"):
        return []  # an older API without api.deps: nothing to check here
    if deps.get("error"):
        return [f"agent not configured: {deps['error']}"]
    problems = []
    if deps.get("runner") != "LocalRunner":
        problems.append(f"runner is {deps.get('runner')}, not the real LocalRunner")
    if deps.get("store") != "AtlasMemoryStore":
        problems.append(f"memory store is {deps.get('store')}, not AtlasMemoryStore")
    if deps.get("storeDb") not in (None, deps.get("expectedDb")):
        problems.append(f"memory store uses {deps.get('storeDb')}, not {deps.get('expectedDb')}")
    if deps.get("runRepoDb") not in (None, deps.get("expectedDb")):
        problems.append(f"runs are stored in {deps.get('runRepoDb')}, not {deps.get('expectedDb')}")
    return problems


def worker(case_id: str, arm: str, repeat: int, out: Path, *, timeout_s: float, wait_index_s: int) -> int:
    from core.config import get_settings

    db_name = get_settings().mongodb_db
    rec: dict[str, Any] = {"case": case_id, "arm": arm, "repeat": repeat, "db": db_name, "error": None,
                           "runId": None, "incidentId": None, "runView": None, "events": [], "setup": {}}
    try:
        assert_eval_db(db_name)  # a worker only ever runs against its own throwaway database
        rec["setup"] = prepare_db(db_name, arm, wait_index_s)
        from fastapi.testclient import TestClient

        from api.main import app

        rec["setup"]["agentDeps"] = deps = inspect_agent_deps(db_name)
        rec["invalidReasons"] = deps_problems(deps)
        if rec["invalidReasons"]:  # don't spend an LLM run that cannot count
            raise RuntimeError("; ".join(rec["invalidReasons"]))
        with TestClient(app) as http:
            rec.update(drive_run(http, {"X-API-Key": payments_api_key()}, case_id, arm, revision_info()["git"],
                                 timeout_s=timeout_s))
    except Exception as e:  # noqa: BLE001 - reported in the record, scored as ERROR
        rec["error"] = f"{type(e).__name__}: {str(e)[:300]}"
    out.write_text(json.dumps(rec, default=str), encoding="utf-8")
    return 0 if rec["error"] is None else 1


# The API's agent settings for every experiment run (core/config.py): the real runner and Atlas, with no
# silent fallback to fakes (the server refuses to start instead), and no new memories from a run.
AGENT_ENV = {"AGENT_RUNNER": "local", "AGENT_STORE": "atlas", "AGENT_PROMOTE": "false"}


def subprocess_run_one(*, model: str | None, timeout_s: float, wait_index_s: int) -> Callable[[PlannedRun], dict]:
    """Each run in its own Python process with MONGODB_DB=<its eval db>: no cached settings, client or
    service can leak from one run (or from the parent) into another."""

    def run_one(p: PlannedRun) -> dict:
        fd, tmp = tempfile.mkstemp(prefix=f"{p.db}_", suffix=".json")
        os.close(fd)
        out = Path(tmp)
        env = {**os.environ, **AGENT_ENV, "MONGODB_DB": p.db, "PYTHONIOENCODING": "utf-8"}
        if model:
            env["LLM_MODEL"] = model
        cmd = [sys.executable, "-m", "evals.run_ablation", "--worker", "--case", p.case, "--arm", p.arm,
               "--repeat", str(p.repeat), "--out", str(out), "--timeout", str(timeout_s),
               "--wait-index", str(wait_index_s)]
        try:
            proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=timeout_s + 2 * wait_index_s + 300)
            text = out.read_text(encoding="utf-8") if out.exists() else ""
            rec = json.loads(text) if text.strip() else failed_record(p, f"worker exited {proc.returncode}")
            if proc.returncode or rec.get("error"):
                rec["workerLogTail"] = (proc.stdout + proc.stderr)[-1500:]
            return rec
        finally:
            out.unlink(missing_ok=True)

    return run_one


# =========================================================================== CLI


def _env_check() -> dict[str, str]:
    """Presence only; values are never printed."""
    from core.config import get_settings

    s = get_settings()
    model = s.llm_model.strip()
    return {
        "MONGODB_URI": "set" if s.mongodb_uri.get_secret_value() else "MISSING",
        "LLM_API_KEY": "set" if s.llm_api_key.get_secret_value() else "MISSING",
        "VOYAGE_API_KEY": "set" if s.voyage_api_key.get_secret_value() else "MISSING",
        "LLM_MODEL": (model or "MISSING") + (" (looks malformed: contains '=')" if "=" in model else ""),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="R10 memory ablation: off / placebo / real, through the API.")
    ap.add_argument("--cases", nargs="+", default=list(CASES))
    ap.add_argument("--arms", nargs="+", default=list(ARMS), choices=ARMS)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--base-url", help="drive a running server instead (its own database: NOT isolated)")
    ap.add_argument("--keep", action="store_true", help="keep the throwaway eval databases")
    ap.add_argument("--dry-run", action="store_true", help="plan + placebo check only: no Atlas, no LLM")
    ap.add_argument("--model", help="LLM_MODEL for every run (default: the one in .env)")
    ap.add_argument("--timeout", type=float, default=600.0, help="seconds to wait for one run")
    ap.add_argument("--wait-index", type=int, default=180, help="seconds to wait for the vector index")
    ap.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    # internal: one run inside its own process
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--case", help=argparse.SUPPRESS)
    ap.add_argument("--arm", choices=ARMS, help=argparse.SUPPRESS)
    ap.add_argument("--repeat", type=int, default=1, help=argparse.SUPPRESS)
    ap.add_argument("--out", type=Path, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)

    if a.worker:
        return worker(a.case, a.arm, a.repeat, a.out, timeout_s=a.timeout, wait_index_s=a.wait_index)

    for c in a.cases:
        if not (ROOT / "cases" / c / "labels.json").is_file():
            ap.error(f"no cases/{c}/labels.json")
    if a.repeats < 1:
        ap.error("--repeats must be at least 1")

    reference = real_memory_lengths()
    try:
        raw_placebos = load_placebo_file()
        placebo_report = validate_placebos(raw_placebos, reference)
    except (OSError, json.JSONDecodeError) as e:
        raw_placebos, placebo_report = [], {"ok": False, "problems": [f"{PLACEBO_FILE.name}: {e}"], "items": [],
                                            "reference": reference}
    stamp = eval_stamp()
    plan = plan_runs(a.cases, a.arms, a.repeats, stamp)

    print(f"placebos: {'ok' if placebo_report['ok'] else 'PROBLEMS'} ({len(placebo_report['items'])} memories, "
          f"real memory lengths {reference})")
    for p in placebo_report["problems"]:
        print(f"  - {p}")
    print("environment:", ", ".join(f"{k} {v}" for k, v in _env_check().items()))
    if a.base_url:
        print(f"target: {a.base_url} (the server's own database; runs are NOT isolated from each other)")
    else:
        print("target: in-process API, one subprocess and one throwaway database per run")
    for p in plan:
        print(f"  {p.case:<3} {p.arm:<8} #{p.repeat}  {'(server db)' if a.base_url else p.db}")
    if a.dry_run:
        print("dry run: nothing executed")
        return 0 if placebo_report["ok"] else 1
    if "placebo" in a.arms and not placebo_report["ok"]:
        print("refusing to run: the placebo arm would not be a valid placebo")
        return 2

    revision = revision_info()
    if a.base_url:
        import httpx

        headers = {"X-API-Key": payments_api_key()}
        client = httpx.Client(base_url=a.base_url, timeout=30)

        def run_one(p: PlannedRun) -> dict:
            rec = {"case": p.case, "arm": p.arm, "repeat": p.repeat, "db": "(server)", "error": None, "setup": {}}
            rec.update(drive_run(client, headers, p.case, p.arm, revision["git"], timeout_s=a.timeout))
            return rec

        records = execute_plan(plan, run_one, None)
        isolation = (f"none: an external server at {a.base_url} ran every run against its own database, so a "
                     "renew or dispute in one real-arm run can affect later runs.")
    else:
        from core.db import get_client

        run_one = subprocess_run_one(model=a.model, timeout_s=a.timeout, wait_index_s=a.wait_index)
        records = execute_plan(plan, run_one, lambda name: drop_eval_db(get_client(), name), keep=a.keep)
        isolation = (f"each run used its own throwaway Atlas database (`{EVAL_PREFIX}<stamp>_<case>_<arm>_<n>`, "
                     "set up with `scripts/atlas_setup.py`, run in its own process with `MONGODB_DB` set to it"
                     + (", kept afterwards (--keep)" if a.keep else ", dropped afterwards")
                     + "), so no run's memory renewals, disputes or promotions reached another run, and the "
                     "demo and team databases were not touched. Agent settings: "
                     + ", ".join(f"`{k}={v}`" for k, v in AGENT_ENV.items())
                     + " (real runner and Atlas, no fallback to fakes; runs never create new memories).")

    labels = {c: load_labels(c) for c in a.cases}
    scores = [score_run(r, labels[r["case"]], raw_placebos) for r in records]
    summary = summarize(scores, a.arms)
    meta = {
        "generatedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "stamp": stamp,
        "cases": a.cases,
        "arms": a.arms,
        "repeats": a.repeats,
        "target": a.base_url or "in-process TestClient(api.main.app)",
        "isolation": isolation,
        "revision": revision,
        "modelOverride": a.model,
        "plan": [asdict(p) for p in plan],
        "fairness": fairness(scores),
    }
    md, js = write_results(meta, records, scores, summary, placebo_report, a.out_dir)
    for arm, s in summary.items():
        print(f"{arm:<8} valid {s['valid']}/{s['runs']}  verified on attempt 1 {s['verifiedOnAttempt1']}/{s['valid']}"
              f"  verified {s['verified']}/{s['valid']}")
    print(f"wrote {md.relative_to(ROOT) if md.is_relative_to(ROOT) else md} and {js.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
