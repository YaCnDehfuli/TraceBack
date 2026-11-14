"""The agent's tools. File tools are read-only and path-checked; propose_fix ends a fix attempt.

Condition checks are NOT tools: they run in code (agent/conditions.py) before the LLM starts.
Test commands come from the runner, never from the LLM.
"""

from __future__ import annotations

from typing import Any

from agent.workspace import PathRefused, Workspace
from core.clock import sha256_text

TOOL_NAMES = ["list_files", "read_file", "search_code", "propose_fix"]


def tool_schemas(patchable_files: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "name": "list_files",
            "description": "List every file in the application.",
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "read_file",
            "description": "Read a file of the application, with line numbers. Optionally a line range.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "integer"},
                    "end_line": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
        {
            "name": "search_code",
            "description": "Case-insensitive text search across all files of the application (code and docs).",
            "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        },
        {
            "name": "propose_fix",
            "description": (
                "Submit a fix: the COMPLETE new contents of one file. The runner then runs the trusted tests "
                "and tells you which tests failed, if any. Each call uses one fix attempt."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "enum": patchable_files},
                    "new_content": {"type": "string", "description": "the whole file, not a diff"},
                    "cause": {"type": "string", "description": "one sentence: why the request fails"},
                    "summary": {"type": "string", "description": "one sentence: what the fix does"},
                },
                "required": ["path", "new_content", "cause", "summary"],
            },
        },
    ]


def run_file_tool(ws: Workspace, name: str, args: dict[str, Any]) -> tuple[str, str]:
    """Execute a read-only tool. Returns (output for the LLM, one-line summary for the timeline)."""
    try:
        if name == "list_files":
            files = ws.list_files()
            return "\n".join(files), f"{len(files)} files"
        if name == "read_file":
            path = args.get("path", "")
            out = ws.read(path, args.get("start_line"), args.get("end_line"))
            return out, f"read {path}"
        if name == "search_code":
            q = args.get("query", "")
            hits = ws.search(q)
            return ("\n".join(hits) or "no matches"), f'searched "{q[:40]}": {len(hits)} hits'
    except PathRefused as e:
        return f"Refused: {e}", f"refused: {e}"
    return f"Unknown tool: {name}", f"unknown tool {name}"


def evidence_id(name: str, args: dict[str, Any], output: str) -> str:
    return "ev_" + sha256_text(f"{name}:{sorted(args.items())}:{output}")[:10]
