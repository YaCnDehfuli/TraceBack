"""E11000 parsing and memory condition checks, in plain code (plan 4.2). No LLM involved.

The runner drops its database after each run, so we never inspect live indexes. Instead we parse the
duplicate-key message, which names the index and the duplicate key, and compare the incident's two
deliveries. That makes Refuse fast, deterministic, and visible before the LLM starts.
"""

from __future__ import annotations

import re

from contracts.models import Conditions, Observations, PreconditionResult

# E11000 duplicate key error collection: shop.payments index: provider_event_id_1
#   dup key: { provider_event_id: "evt_123" }
_E11000 = re.compile(
    r"E11000 duplicate key error.*?index:\s*(?P<index>\S+)\s+dup key:\s*\{\s*(?P<field>[\w.]+)\s*:\s*(?P<value>[^,}]+)",
    re.DOTALL,
)


def parse_e11000(message: str) -> tuple[str, str, str] | None:
    """Return (index, field, value) from a MongoDB duplicate key error message, or None."""
    m = _E11000.search(message)
    if not m:
        return None
    value = m.group("value").strip().strip('"').strip("'")
    return m.group("index"), m.group("field"), value


def apply_e11000(observations: Observations, message: str) -> Observations:
    """Copy of `observations` with error_code and dup_key_* filled from the message, when it parses."""
    parsed = parse_e11000(message)
    if not parsed:
        return observations
    index, field, value = parsed
    return observations.model_copy(
        update={"error_code": "11000", "dup_key_index": index, "dup_key_field": field, "dup_key_value": value}
    )


def check_conditions(conditions: Conditions, observations: Observations) -> list[PreconditionResult]:
    """Check a memory's conditions against the current incident. held=None means "could not tell"."""
    results: list[PreconditionResult] = []

    if conditions.dup_key_field is not None:
        actual = observations.dup_key_field
        results.append(
            PreconditionResult(
                check="dup_key_field",
                expected=conditions.dup_key_field,
                actual=actual,
                held=None if actual is None else actual == conditions.dup_key_field,
            )
        )

    if conditions.same_event_id_on_both_deliveries is not None:
        ids = observations.delivery_event_ids
        same = None if len(ids) < 2 else len(set(ids)) == 1
        results.append(
            PreconditionResult(
                check="same_event_id_on_both_deliveries",
                expected=str(conditions.same_event_id_on_both_deliveries).lower(),
                actual=None if same is None else str(same).lower(),
                held=None if same is None else same == conditions.same_event_id_on_both_deliveries,
            )
        )

    return results


def not_applied_reason(results: list[PreconditionResult]) -> str | None:
    """The plain sentence shown on screen when a memory is refused, or None if every condition held."""
    for r in results:
        if r.held:
            continue
        if r.check == "dup_key_field":
            if r.actual is None:
                return f"Not applied: the duplicate key could not be read; this memory requires `{r.expected}`."
            return f"Not applied: duplicate key is `{r.actual}`; this memory requires `{r.expected}`."
        if r.check == "same_event_id_on_both_deliveries":
            if r.actual is None:
                return "Not applied: could not compare the two deliveries' event IDs."
            return "Not applied: the two deliveries have different event IDs; this memory is for replays."
        return f"Not applied: condition `{r.check}` expected `{r.expected}`, got `{r.actual}`."
    return None
