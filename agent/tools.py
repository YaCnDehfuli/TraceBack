"""The agent's file tools (P1-2). Paths are checked: only files inside the run's workspace copy.

Condition checks are NOT tools: they run in code (agent/conditions.py). Test commands come from the
runner, never from the LLM.
"""

from __future__ import annotations

TOOL_NAMES = ["read_file", "search_code", "list_files", "propose_fix"]


def tool_schemas() -> list[dict]:
    """JSON schemas sent to the LLM. TODO(P1-2)."""
    raise NotImplementedError("P1-2: tool schemas")
