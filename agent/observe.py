"""Turn a case (request, deliveries, logs) into Observations, in plain code. No LLM.

Used by the walking skeleton (scripts/skeleton.py) and by the agent loop (P1-2), so recall and the
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
    """Symptoms only (what anyone could see in a new incident), never the cause or the fix."""
    facts = []
    if obs.exception_type:
        facts.append(obs.exception_type)
    if obs.error_code == "11000":
        facts.append(f"E11000 duplicate key on {obs.dup_key_field} (index {obs.dup_key_index})")
    if obs.operation:
        facts.append(f"during {obs.operation}")
    ids = obs.delivery_event_ids
    if len(ids) >= 2:
        facts.append(f"{len(ids)} deliveries, {'same' if len(set(ids)) == 1 else 'different'} event id")
    if obs.stack_frames:
        facts.append(f"at {obs.stack_frames[-1]}")
    text = "; ".join(facts)
    return f"{report.strip()} | {text}" if report.strip() else text
