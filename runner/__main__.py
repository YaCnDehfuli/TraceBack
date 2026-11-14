"""Command line for the runner.

    python -m runner reproduce A
    python -m runner verify A cases/A/reference/webhooks.py
"""

import json
import sys
from pathlib import Path

from .core import load_case, reproduce, verify


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("reproduce", "verify"):
        print(__doc__)
        return 2
    command, case_id = argv[0], argv[1]
    if command == "reproduce":
        result = reproduce(case_id)
    else:
        if len(argv) < 3:
            print(__doc__)
            return 2
        target = load_case(case_id)["allowed_files"][0]
        content = Path(argv[2]).read_text(encoding="utf-8")
        result = verify(case_id, {"path": target, "content": content})
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
