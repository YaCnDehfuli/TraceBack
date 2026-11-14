"""Build the MemoryDraft for a verified fix. Conditions are filled automatically (plan 4.2)."""

from __future__ import annotations

from contracts.models import (
    Applicability,
    Conditions,
    FileAnchor,
    FilePatch,
    MemoryDraft,
    Observations,
)
from core.clock import sha256_text


def conditions_from(observations: Observations) -> Conditions:
    """The two-condition vocabulary, taken from the incident the fix was proven on."""
    ids = observations.delivery_event_ids
    return Conditions(
        dup_key_field=observations.dup_key_field,
        same_event_id_on_both_deliveries=(len(set(ids)) == 1) if len(ids) >= 2 else None,
    )


def build_draft(
    observations: Observations,
    patch: FilePatch,
    *,
    source_revision: str,
    confirmed_cause: str,
    resolution_summary: str,
    excludes: list[str] | None = None,
) -> MemoryDraft:
    signature = {"errorCode": observations.error_code or "", "operation": observations.operation or ""}
    return MemoryDraft(
        incident_id=observations.incident_id,
        repository_id=observations.repository_id,
        source_revision=source_revision,
        retrieval_text=observations.summary,
        signature={k: v for k, v in signature.items() if v},
        confirmed_cause=confirmed_cause,
        applicability=Applicability(conditions=conditions_from(observations), excludes=excludes or []),
        resolution_summary=resolution_summary,
        patch=patch,
        anchors=[FileAnchor(path=patch.path, sha256=sha256_text(patch.new_content))],
    )
