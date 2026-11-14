"""Seed team policies, the demo memories and (R8) about 20 labelled distractors (owner: P2, P2-1 / P2-8).

Demo policies (plan section 8): Earn memory 24 h, max lifetime 48 h; canary memory 90 s;
distractors 24 h, labelled seeded: true.

    uv run python scripts/seed_demo.py --db traceback_demo [--reset]
"""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Traceback demo data.")
    parser.add_argument("--db", required=True)
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    print(f"seed_demo --db {args.db}: not implemented yet (P2-1).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
