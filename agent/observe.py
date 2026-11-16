"""Turn a case (request, deliveries, logs) into Observations, in plain code. No LLM.

Used by the walking skeleton (scripts/skeleton.py) and by the agent loop, so recall and the
condition checks always see the same facts.
"""

from __future__ import annotations

import re

from agent.conditions import apply_e11000
from contracts.models import CaseManifest, Observations

_EXCEPTION = re.compile(r"^(?:[\w.]+\.)?(\w+(?:Error|Exception)):", re.MULTILINE)
_FRAME = re.compile(r'File "([^"]+)", line (\d+), in (\w+)')


def delivery_event_ids(manifest: CaseManifest) -> list[str]:
    """Event id of each delivery in the incident (request.deliveries[*].id), in order."""
    deliveries = manifest.request.get("deliveries") or []
    return [str(d["id"]) for d in deliveries if isinstance(d, dict) and "id" in d]


def observations_from_case(manifest: CaseManifest, incident_id: str) -> Observations:
    logs = manifest.logs
    exceptions = _EXCEPTION.findall(logs)
    frames = [f"{path}:{line} in {func}" for path, line, func in _FRAME.findall(logs)]
    method = manifest.request.get("method", "")
    path = manifest.request.get("path", "")
    operation = f"{method} {path}".strip() or None

    obs = Observations(
        incident_id=incident_id,
        repository_id=manifest.repository_id,
        summary="",
        operation=operation,
        exception_type=exceptions[-1] if exceptions else None,
        delivery_event_ids=delivery_event_ids(manifest),
        stack_frames=frames,
    )
    obs = apply_e11000(obs, logs)
    return obs.model_copy(update={"summary": _summary(obs, manifest.request.get("report", ""))})


def _summary(obs: Observations, report: str) -> str:
    """The text embedded for recall, on both sides (the memory and the query). Symptoms only, never the cause
    or the fix. For a duplicate key it is built from code-derived facts alone, the deciding ones first: the
    free-text report varies in wording between true repeats and shares words with look-alikes, so including
    it made a trap (case C/D) outrank true repeats (scripts/embed_separation.py). The report still goes to
    the LLM in the brief."""
    if obs.error_code == "11000" and obs.dup_key_field:
        ids = obs.delivery_event_ids
        same = "unknown" if len(ids) < 2 else ("the same" if len(set(ids)) == 1 else "a different")
        return (
            f"duplicate key field: {obs.dup_key_field}. unique index: {obs.dup_key_index}. "
            f"retried deliveries carry {same} event id. "
            f"error: E11000 {obs.exception_type}. operation: {obs.operation}."
        )
    facts = []
    if obs.exception_type:
        facts.append(obs.exception_type)
    if obs.operation:
        facts.append(f"during {obs.operation}")
    if obs.stack_frames:
        facts.append(f"at {obs.stack_frames[-1]}")
    text = "; ".join(facts)
    return f"{report.strip()} | {text}" if report.strip() else text
