"""Trusted tests for the payments webhook. The agent can never change these."""

EVENT = {"id": "evt_1001", "customer_id": "cus_42", "amount": 2500}


def post(client, event):
    return client.post("/webhooks/provider", json=event)


def credited(db, customer_id):
    return sum(row["amount"] for row in db.ledger.find({"customer_id": customer_id}))


def test_single_payment_credited(client, db):
    response = post(client, EVENT)
    assert response.status_code == 200
    assert credited(db, "cus_42") == 2500
    assert db.replays.count_documents({}) == 0, "a first delivery is not a replay"


def test_duplicate_event_reproduces(client, db):
    assert post(client, EVENT).status_code == 200
    second = post(client, EVENT)
    assert second.status_code == 200, (
        f"second delivery of the same provider event returned {second.status_code}"
    )


def test_duplicate_event_single_effect(client, db):
    post(client, EVENT)
    post(client, EVENT)
    assert credited(db, "cus_42") == 2500, "a repeated event must credit the customer exactly once"
    assert db.payments.count_documents({"provider_event_id": "evt_1001"}) == 1


def test_distinct_events_same_customer(client, db):
    assert post(client, EVENT).status_code == 200
    assert post(client, {**EVENT, "id": "evt_1002"}).status_code == 200
    assert credited(db, "cus_42") == 5000, (
        "two different events from the same customer must both be credited"
    )


def test_unique_index_still_present(client, db):
    post(client, EVENT)
    post(client, EVENT)
    unique_on_event = [
        index
        for index in db.payments.index_information().values()
        if index.get("unique") and index["key"] == [("provider_event_id", 1)]
    ]
    assert unique_on_event, "the unique index on provider_event_id must stay"


def test_replay_recorded_for_reconciliation(client, db):
    post(client, EVENT)
    post(client, EVENT)
    assert db.replays.count_documents({"event_id": "evt_1001"}) == 1, (
        "a replayed provider event must be recorded for month-end reconciliation"
    )
