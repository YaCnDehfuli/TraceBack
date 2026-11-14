"""How well do the embeddings separate the real look-alike (B, B2, B3) from the traps (C, D)?

    uv run python scripts/embed_separation.py

Embeds case A's memory text and every other case's query text with Voyage (no database writes) and
prints cosine scores for the old text (report + facts) and today's (facts only, agent.observe._summary).
"gap" = worst B-family score minus best trap score: bigger is better, negative means a trap outranks a
true match.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agent.observe import observations_from_case  # noqa: E402
from contracts.models import CaseManifest, Observations  # noqa: E402
from memory.embeddings import embed_one  # noqa: E402

GOOD, TRAPS = ("B", "B2", "B3"), ("C", "D")


def load(case_id: str) -> Observations:
    manifest = json.loads((ROOT / "cases" / case_id / "manifest.json").read_text(encoding="utf-8"))
    return observations_from_case(CaseManifest.model_validate(manifest), f"inc_{case_id}")


def report_text(o: Observations, case_id: str) -> str:
    """The text we embedded before (report + parsed facts), kept here for comparison."""
    manifest = json.loads((ROOT / "cases" / case_id / "manifest.json").read_text(encoding="utf-8"))
    report = (manifest.get("request") or {}).get("report", "").strip()
    ids = o.delivery_event_ids
    facts = [o.exception_type, f"E11000 duplicate key on {o.dup_key_field} (index {o.dup_key_index})",
             f"during {o.operation}"]
    if len(ids) >= 2:
        facts.append(f"{len(ids)} deliveries, {'same' if len(set(ids)) == 1 else 'different'} event id")
    if o.stack_frames:
        facts.append(f"at {o.stack_frames[-1]}")
    return f"{report} | {'; '.join(f for f in facts if f)}"


def cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True)) / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


def main() -> None:
    obs = {c: load(c) for c in ("A", *GOOD, *TRAPS)}
    variants = {
        "old: report + facts, doc/query": (lambda c: report_text(obs[c], c), "query"),
        "old: report + facts, doc/doc": (lambda c: report_text(obs[c], c), "document"),
        "now: facts only (summary), doc/query": (lambda c: obs[c].summary, "query"),
        "now: facts only (summary), doc/doc": (lambda c: obs[c].summary, "document"),
    }
    print(f"{'text, memory/query input type':38s} " + " ".join(f"{c:>6s}" for c in (*GOOD, *TRAPS)) + "    gap")
    for name, (text, query_type) in variants.items():
        memory = embed_one(text("A"), "document")
        s = {c: cos(memory, embed_one(text(c), query_type)) for c in (*GOOD, *TRAPS)}
        gap = min(s[c] for c in GOOD) - max(s[c] for c in TRAPS)
        print(f"{name:38s} " + " ".join(f"{s[c]:6.3f}" for c in (*GOOD, *TRAPS)) + f" {gap:+.3f}")


if __name__ == "__main__":
    main()
