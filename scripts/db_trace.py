"""Backend trace: exactly what the agent reads from and writes to Atlas, from the database driver's own log.

    uv run python scripts/db_trace.py                    # recall for case B (Payments) and Platform, no LLM
    uv run python scripts/db_trace.py --case C           # the look-alike
    uv run python scripts/db_trace.py --full --case B    # a whole run with the real LLM (writes runs/events/audit)

Prints: every MongoDB command (vectors abbreviated), the Voyage embedding calls, the candidates and the
condition checks, then an inventory of the database: collections, counts, the vector index definition,
the newest memory (no vector, no secret) and the newest audit events.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pymongo import monitoring  # noqa: E402

SKIP = {"hello", "ismaster", "isMaster", "ping", "endSessions", "saslStart", "saslContinue", "buildInfo"}


def _short(value, depth=0):
    """Abbreviate vectors and long strings so the log stays readable."""
    if isinstance(value, list) and len(value) > 20 and all(isinstance(x, (int, float)) for x in value[:20]):
        return f"<vector {len(value)} floats>"
    if isinstance(value, dict):
        return {k: ("<secret>" if k == "hmacSecret" else _short(v, depth + 1)) for k, v in value.items()}
    if isinstance(value, list):
        return [_short(v, depth + 1) for v in value[:5]] + (["…"] if len(value) > 5 else [])
    if isinstance(value, str) and len(value) > 120:
        return value[:117] + "…"
    return value


class Trace(monitoring.CommandListener):
    def __init__(self):
        self.n = 0

    def started(self, event):
        if event.command_name in SKIP:
            return
        self.n += 1
        cmd = dict(event.command)
        coll = cmd.get(event.command_name)
        body = {
            k: v
            for k, v in cmd.items()
            if k in ("pipeline", "filter", "projection", "documents", "updates", "deletes", "limit", "sort")
        }
        print(
            f"  [db {self.n:>2}] {event.database_name}.{coll} {event.command_name} "
            f"{json.dumps(_short(body), default=str)}"
        )

    def succeeded(self, event):
        if event.command_name in SKIP:
            return
        reply = event.reply
        batch = (reply.get("cursor") or {}).get("firstBatch")
        if batch is not None:
            print(f"           -> {len(batch)} docs {json.dumps(_short(batch[:3]), default=str)[:300]}")
        elif "n" in reply:
            print(f"           -> n={reply['n']}")

    def failed(self, event):
        print(f"  [db] {event.command_name} FAILED: {event.failure}")


def trace_embeddings():
    import memory.embeddings as emb

    original = emb.embed_one

    def logged(text, input_type):
        vec = original(text, input_type)
        print(f"  [voyage] embed input_type={input_type} -> {len(vec)} floats  text={text[:90]!r}…")
        return vec

    emb.embed_one = logged
    import memory.store as store_mod

    store_mod.embed_one = logged


def inventory(db):
    from core.db import Collections

    print(f"\n=== Inventory of database '{db.name}'")
    for name in sorted(db.list_collection_names()):
        print(f"  {name:<14} {db[name].estimated_document_count():>5} docs")
    mem = db[Collections.MEMORIES]
    for ix in mem.list_search_indexes():
        print(f"  search index {ix['name']}: type={ix.get('type')} queryable={ix.get('queryable')}")
        print(f"    definition {json.dumps(ix.get('latestDefinition', {}))}")
    newest = mem.find_one({}, {"embedding": 0, "hmacSecret": 0}, sort=[("createdAt", -1)])
    if newest:
        keep = [
            "_id",
            "version",
            "status",
            "ownerTeamId",
            "readableBy",
            "repositoryId",
            "title",
            "signature",
            "applicability",
            "verification",
            "expiresAt",
            "purgeAt",
            "seeded",
            "embeddingModel",
            "embeddingVersion",
        ]
        print("  newest memory:", json.dumps(_short({k: newest.get(k) for k in keep}), default=str, indent=2))
    audit = db[Collections.MEMORY_AUDIT]
    print("  newest audit events:")
    for e in audit.find({}, {"_id": 0, "contentHash": 0}).sort([("at", -1)]).limit(6):
        print("   ", json.dumps(_short(e), default=str)[:220])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Trace the agent's database traffic.")
    parser.add_argument("--case", default="B")
    parser.add_argument("--full", action="store_true", help="run the whole agent with the real LLM")
    args = parser.parse_args(argv)

    monitoring.register(Trace())  # must happen before the first client is created
    import os

    from agent.conditions import check_conditions, not_applied_reason
    from agent.observe import observations_from_case
    from agent.run import TEAMS
    from api.runs import load_case
    from contracts.models import Principal
    from core.config import get_settings
    from core.db import get_db
    from memory.store import AtlasMemoryStore

    s = get_settings()
    fake = os.getenv("FAKE_EMBEDDINGS") == "1"
    print(
        f"embeddings: {'FAKE (hashed words, no Voyage!)' if fake else f'{s.embedding_model} via {s.voyage_base_url}'}"
        f" · database: {s.mongodb_db}"
    )
    trace_embeddings()
    db = get_db()
    case = load_case(args.case)
    if case is None:
        raise SystemExit(f"No case {args.case}")
    store = AtlasMemoryStore(db)

    if args.full:
        from agent.events import EventSink
        from agent.llm import get_llm
        from agent.run import describe, pick_runner

        runner, runner_name = pick_runner("auto")
        print(f"=== Full run: case {case.case_id} · {runner_name}")
        from agent.loop import run_investigation

        sink = EventSink("trace_run", on_event=lambda e: print(f"{e.seq:>2}. {describe(e)}"))
        run_investigation(Principal(**TEAMS["payments"]), case, store, runner, get_llm(), sink=sink, promote=False)
    else:
        for team in ("payments", "platform"):
            p = Principal(**TEAMS[team])
            obs = observations_from_case(case, "inc_trace")
            print(f"\n=== Recall for case {case.case_id} as {p.team_id}")
            print(
                f"  observations: errorCode={obs.error_code} dupKeyField={obs.dup_key_field} "
                f"operation={obs.operation!r} deliveries={obs.delivery_event_ids}"
            )
            cands = store.recall(p, obs, run_id="trace")
            print(f"  -> {len(cands)} candidates")
            for c in cands:
                results = check_conditions(c.applicability.conditions, obs)
                held = sum(r.held is True for r in results)
                print(
                    f"     {c.memory_id} v{c.version} owner={c.owner_team_id} score={c.score:.3f} "
                    f"source={c.source} match={c.match} conditions {held}/{len(results)}"
                    f" {not_applied_reason(results) or 'APPLIES'}"
                )
    inventory(db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
