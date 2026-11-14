"""Command-line entry point (P1-2):

uv run python -m agent.run --case B --team payments [--memory real|off|placebo]
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one Traceback investigation from the command line.")
    parser.add_argument("--case", required=True, help="Case id, e.g. A, B, C, D, P")
    parser.add_argument("--team", required=True, choices=["payments", "platform"])
    parser.add_argument("--memory", default="real", choices=["real", "off", "placebo"])
    args = parser.parse_args(argv)
    print(f"agent.run: case={args.case} team={args.team} memory={args.memory}")
    print("Not implemented yet (P1-2).", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
