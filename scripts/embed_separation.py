"""How well do the embeddings separate the real look-alike (B, B2, B3) from the traps (C, D)?

    uv run python scripts/embed_separation.py

Embeds case A's memory text and every other case's query text with Voyage (no database writes) and
prints cosine scores for four ways of building the text. "gap" = worst B-family score minus best trap
score: bigger is better, negative means a trap outranks a true match.
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


def signature_text(o: Observations) -> str:
    """Only the code-derived facts, the discriminating ones first. No free-text report."""
    ids = o.delivery_event_ids
    same = "unknown" if len(ids) < 2 else ("the same" if len(set(ids)) == 1 else "a different")
    return (
        f"duplicate key field: {o.dup_key_field}. unique index: {o.dup_key_index}. "
        f"retried deliveries carry {same} event id. "
        f"error: E{o.error_code} {o.exception_type}. operation: {o.operation}."
    )


def cos(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True)) / math.sqrt(sum(x * x for x in a) * sum(y * y for y in b))


def main() -> None:
    obs = {c: load(c) for c in ("A", *GOOD, *TRAPS)}
    variants = {
        "summary (today), document/query": (lambda o: o.summary, "query"),
        "summary, document/document": (lambda o: o.summary, "document"),
        "signature, document/query": (signature_text, "query"),
        "signature, document/document": (signature_text, "document"),
    }
    print(f"{'text, memory/query input type':34s} " + " ".join(f"{c:>6s}" for c in (*GOOD, *TRAPS)) + "    gap")
    for name, (text, query_type) in variants.items():
        memory = embed_one(text(obs["A"]), "document")
        s = {c: cos(memory, embed_one(text(obs[c]), query_type)) for c in (*GOOD, *TRAPS)}
        gap = min(s[c] for c in GOOD) - max(s[c] for c in TRAPS)
        print(f"{name:34s} " + " ".join(f"{s[c]:6.3f}" for c in (*GOOD, *TRAPS)) + f" {gap:+.3f}")


if __name__ == "__main__":
    main()
