"""Run the demo: starts the API and the web UI on http://localhost:8000 (owner: P3).

    uv run python scripts/demo.py [--port 8000]

`main` must always be able to run this (plan 5.1). Keys 1-5 in the UI jump to the five beats (P3-5).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Start Traceback (API + UI).")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    import uvicorn

    print(f"Traceback: open http://{args.host}:{args.port}   (Ctrl+C to stop)")
    uvicorn.run("api.main:app", host=args.host, port=args.port, app_dir=str(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
