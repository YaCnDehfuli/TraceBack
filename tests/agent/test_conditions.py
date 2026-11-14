from __future__ import annotations

from agent.conditions import apply_e11000, check_conditions, not_applied_reason, parse_e11000
from contracts.models import Conditions, Observations

MSG = (
    "E11000 duplicate key error collection: shop.payments index: provider_event_id_1 "
    'dup key: { provider_event_id: "evt_123" }'
)
LOOKALIKE = (
    'E11000 duplicate key error collection: shop.payments index: customer_id_1 dup key: { customer_id: "cus_42" }'
)
MEMORY = Conditions(dup_key_field="provider_event_id", same_event_id_on_both_deliveries=True)


def obs(message: str, ids: list[str]) -> Observations:
    base = Observations(incident_id="inc_1", repository_id="payments-webhooks", summary="dup", delivery_event_ids=ids)
    return apply_e11000(base, message)


def test_parse_e11000():
    assert parse_e11000(MSG) == ("provider_event_id_1", "provider_event_id", "evt_123")
    assert parse_e11000("some other error") is None


def test_replay_meets_both_conditions():
    results = check_conditions(MEMORY, obs(MSG, ["evt_123", "evt_123"]))
    assert [r.held for r in results] == [True, True]
    assert not_applied_reason(results) is None


def test_lookalike_is_refused_with_a_plain_sentence():
    results = check_conditions(MEMORY, obs(LOOKALIKE, ["evt_1", "evt_2"]))
    assert [r.held for r in results] == [False, False]
    assert not_applied_reason(results) == (
        "Not applied: duplicate key is `customer_id`; this memory requires `provider_event_id`."
    )


def test_unknown_facts_are_not_guessed():
    results = check_conditions(MEMORY, obs("no duplicate key here", []))
    assert [r.held for r in results] == [None, None]
    assert not_applied_reason(results) is not None
