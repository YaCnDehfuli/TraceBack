"""Trusted tests for the webhook practice apps. The agent can never change these."""

import pytest

EVENT = {"id": "evt_1001", "customer_id": "cus_42", "amount": 2500}


def post(client, names, event):
    return client.post(names["route"], json=event)


def credited(db, names, customer_id):
    rows = db[names["ledger"]].find({names["ledger_customer_field"]: customer_id})
    return sum(row[names["ledger_amount_field"]] for row in rows)


def test_single_payment_credited(client, db, names):
    response = post(client, names, EVENT)
    assert response.status_code == 200
    assert credited(db, names, "cus_42") == 2500
    if names["replays"]:
        assert db[names["replays"]].count_documents({}) == 0, "a first delivery is not a replay"


def test_duplicate_event_reproduces(client, db, names):
    assert post(client, names, EVENT).status_code == 200
    second = post(client, names, EVENT)
    assert second.status_code == 200, (
        f"second delivery of the same provider event returned {second.status_code}"
    )


def test_duplicate_event_single_effect(client, db, names):
    post(client, names, EVENT)
    post(client, names, EVENT)
    assert credited(db, names, "cus_42") == 2500, (
        "a repeated event must credit the customer exactly once"
    )
    assert db[names["payments"]].count_documents({names["event_field"]: "evt_1001"}) == 1


def test_distinct_events_same_customer(client, db, names):
    assert post(client, names, EVENT).status_code == 200
    assert post(client, names, {**EVENT, "id": "evt_1002"}).status_code == 200
    assert credited(db, names, "cus_42") == 5000, (
        "two different events from the same customer must both be credited"
    )
    for event_id in ("evt_1001", "evt_1002"):
        assert db[names["payments"]].count_documents({names["event_field"]: event_id}) == 1, (
            f"each provider event must keep its own payment record ({event_id} is missing or merged)"
        )


def test_handler_does_not_change_indexes(client, db, names):
    before = db[names["payments"]].index_information()
    post(client, names, EVENT)
    post(client, names, EVENT)
    post(client, names, {**EVENT, "id": "evt_1002"})
    assert db[names["payments"]].index_information() == before, (
        "request handlers must not create or drop indexes; schema changes belong in app/db.py"
    )


def test_unique_index_still_present(client, db, names):
    post(client, names, EVENT)
    post(client, names, EVENT)
    unique_on_event = [
        index
        for index in db[names["payments"]].index_information().values()
        if index.get("unique") and index["key"] == [(names["event_field"], 1)]
    ]
    assert unique_on_event, f"the unique index on {names['event_field']} must stay"


def test_replay_recorded_for_reconciliation(client, db, names):
    if not names["replays"]:
        pytest.skip("this team has no rule about recording replays")
    post(client, names, EVENT)
    post(client, names, EVENT)
    count = db[names["replays"]].count_documents({names["replay_event_field"]: "evt_1001"})
    assert count == 1, "a replayed provider event must be recorded for month-end reconciliation"
