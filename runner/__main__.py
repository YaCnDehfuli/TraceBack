"""Command line for the runner.

    uv run python -m runner reproduce A
    uv run python -m runner verify A cases/A/reference/webhooks.py
"""

import sys
from pathlib import Path

from contracts.models import FilePatch

from .sandbox import LocalRunner, load_manifest


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in ("reproduce", "verify") or (argv[0] == "verify" and len(argv) < 3):
        print(__doc__)
        return 2
    command, case_id = argv[0], argv[1]
    runner = LocalRunner()
    if command == "reproduce":
        result = runner.reproduce(case_id)
    else:
        target = load_manifest(case_id).patchable_files[0]
        content = Path(argv[2]).read_text(encoding="utf-8")
        result = runner.verify(case_id, FilePatch(path=target, new_content=content))
    print(result.model_dump_json(by_alias=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
