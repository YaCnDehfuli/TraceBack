"""Create collections, the memories validator, the vector index, the TTL index and the other indexes.
Safe to run twice (owner: P2, P2-1; team guide 8.7).

    uv run python scripts/atlas_setup.py --db traceback_p2
    uv run python scripts/atlas_setup.py --all          # every team database
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo.database import Database  # noqa: E402
from pymongo.errors import OperationFailure  # noqa: E402
from pymongo.operations import SearchIndexModel  # noqa: E402

from core.db import get_client  # noqa: E402
from memory.config import TEAM_DBS, VECTOR_INDEX  # noqa: E402
from memory.schema import INDEXES, MEMORY_VALIDATOR, VECTOR_INDEX_DEFINITION  # noqa: E402

VALIDATION = {"validator": MEMORY_VALIDATOR, "validationLevel": "strict", "validationAction": "error"}


def ensure_collections(db: Database) -> None:
    existing = set(db.list_collection_names())
    for name in INDEXES:
        if name not in existing:
            db.create_collection(name, **(VALIDATION if name == "memories" else {}))
            print(f"  created {name}")

    info = next(db.list_collections(filter={"name": "memories"}))
    if info.get("options", {}).get("validator") == MEMORY_VALIDATOR:
        print("  validator ok on memories")
        return
    # Changing a validator needs collMod, which the app user (readWrite) deliberately lacks:
    # the app's own login cannot switch off the proof check.
    try:
        db.command("collMod", "memories", **VALIDATION)
        print("  validator updated on memories")
    except OperationFailure as e:
        if e.code != 13:  # Unauthorized
            raise
        if db.memories.estimated_document_count() == 0:
            db.memories.drop()
            db.create_collection("memories", **VALIDATION)
            print("  memories was empty: recreated with the new validator")
        else:
            print("  !! validator differs, memories has data, and this user can't change it.")
            print("     Run this script once with an admin connection string as MONGODB_URI.")
            raise SystemExit(1) from e


def ensure_indexes(db: Database) -> None:
    for coll, specs in INDEXES.items():
        for keys, opts in specs:
            try:
                db[coll].create_index(keys, **opts)
            except OperationFailure as e:
                if e.code not in (85, 86):  # same name, different options: recreate
                    raise
                db[coll].drop_index(opts["name"])
                db[coll].create_index(keys, **opts)
    print("  regular indexes ok")


def ensure_vector_index(db: Database) -> None:
    found = [i for i in db.memories.list_search_indexes() if i["name"] == VECTOR_INDEX]
    if not found:
        db.memories.create_search_index(
            SearchIndexModel(definition=VECTOR_INDEX_DEFINITION, name=VECTOR_INDEX, type="vectorSearch")
        )
        print(f"  creating vector index {VECTOR_INDEX}")
    elif found[0].get("latestDefinition") != VECTOR_INDEX_DEFINITION:
        db.memories.update_search_index(VECTOR_INDEX, VECTOR_INDEX_DEFINITION)
        print(f"  updating vector index {VECTOR_INDEX}")


def wait_queryable(db: Database, timeout: int = 300) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        idx = [i for i in db.memories.list_search_indexes() if i["name"] == VECTOR_INDEX]
        if idx and idx[0].get("queryable") and idx[0].get("status") == "READY":
            print(f"  {VECTOR_INDEX} READY and queryable ({time.time() - start:.0f}s)")
            return True
        time.sleep(5)
    print(f"  {VECTOR_INDEX} not ready after {timeout}s; check Atlas > Search & Vector Search")
    return False


def setup(name: str, wait: bool) -> bool:
    print(f"[{name}]")
    db = get_client()[name]
    ensure_collections(db)
    ensure_indexes(db)
    ensure_vector_index(db)
    return wait_queryable(db) if wait else True


def main() -> int:
    ap = argparse.ArgumentParser(description="Set up Traceback collections and indexes in Atlas.")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--db", help="traceback_p1 | traceback_p2 | traceback_p3 | traceback_demo")
    g.add_argument("--all", action="store_true", help="every team database")
    ap.add_argument("--no-wait", action="store_true")
    a = ap.parse_args()
    ok = all([setup(n, not a.no_wait) for n in (TEAM_DBS if a.all else [a.db])])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
