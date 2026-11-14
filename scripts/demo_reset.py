"""Reset the demo right before each judging session (owner: P3, P3-6; plan section 8).

    uv run python scripts/demo_reset.py [--db traceback_demo] [--skip-check]

1. Drop leftover practice-app databases (fixture_*) from crashed or interrupted runs.
2. Reseed Atlas through P2's scripts/seed_demo.py: team policies, the Earn memory (24 h),
   the 90-second canary memory and the labelled distractors.
3. Check the practice app still reproduces the bug (runner reproduce A), so a broken fixture
   is caught before the judges see it.

Exit code 0 only when every step that is implemented succeeded.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def step(title: str) -> None:
    print(f"\n== {title}")


def fixture_uri() -> str:
    import os

    if os.environ.get("FIXTURE_MONGODB_URI"):
        return os.environ["FIXTURE_MONGODB_URI"]
    from core.config import get_settings

    return get_settings().fixture_mongodb_uri.get_secret_value()


def drop_fixture_databases() -> bool:
    from pymongo import MongoClient

    try:
        client = MongoClient(fixture_uri(), serverSelectionTimeoutMS=3000)
        names = [n for n in client.list_database_names() if n.startswith("fixture_")]
        for name in names:
            client.drop_database(name)
        print(f"ok: dropped {len(names)} leftover fixture database(s)")
        return True
    except Exception as err:  # noqa: BLE001 - report any connection problem plainly
        print(f"FAILED: fixture database not reachable ({err}). Is MongoDB running? Check FIXTURE_MONGODB_URI.")
        return False


def reseed(db: str) -> bool:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seed_demo.py"), "--db", db, "--reset"],
        cwd=ROOT, capture_output=True, text=True,
    )
    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode == 0:
        print(output or "ok: reseeded")
        return True
    if "not implemented" in output:
        print(f"skipped: {output}")
        return True
    print(f"FAILED: seed_demo.py exited {proc.returncode}\n{output}")
    return False


def check_case_a() -> bool:
    try:
        from runner.sandbox import LocalRunner

        result = LocalRunner().reproduce("A")
    except (ImportError, NotImplementedError) as err:
        print(f"skipped: runner not available on this branch ({err})")
        return True
    if result.before_failed and result.status == "failed":
        print(f"ok: case A reproduces the bug ({result.duration_ms} ms)")
        return True
    print(f"FAILED: case A did not reproduce: status={result.status} detail={result.detail}")
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the Traceback demo.")
    parser.add_argument("--db", default="traceback_demo")
    parser.add_argument("--skip-check", action="store_true", help="skip the case A reproduction check")
    args = parser.parse_args()

    results = []
    step("1. Practice-app databases")
    results.append(drop_fixture_databases())
    step(f"2. Reseed Atlas database {args.db}")
    results.append(reseed(args.db))
    if not args.skip_check:
        step("3. Practice app still reproduces the bug")
        results.append(check_case_a())

    print("\nDemo reset " + ("complete." if all(results) else "had failures; see above."))
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
