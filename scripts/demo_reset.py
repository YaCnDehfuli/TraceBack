"""Reset the demo right before each judging session (owner: P3, P3-6; plan section 8).

    uv run python scripts/demo_reset.py

Will: reseed traceback_demo (via scripts/seed_demo.py), recreate the Earn memory (24 h) and the
90-second canary memory, and reset the fixture database.
"""

from __future__ import annotations

import sys


def main() -> int:
    print("demo_reset: not implemented yet (P3-6).", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
