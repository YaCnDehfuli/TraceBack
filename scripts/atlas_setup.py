"""Create collections, the memories validator, the vector index, the TTL index and the other indexes
on one database. Safe to run twice (owner: P2, P2-1; team guide 8.7).

    uv run python scripts/atlas_setup.py --db traceback_p2
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up Traceback collections and indexes in Atlas.")
    parser.add_argument("--db", required=True, help="traceback_p1 | traceback_p2 | traceback_p3 | traceback_demo")
    args = parser.parse_args()
    print(f"atlas_setup --db {args.db}: not implemented yet (P2-1).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
