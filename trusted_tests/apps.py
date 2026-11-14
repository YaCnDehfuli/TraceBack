"""Where each practice app keeps its data, so the same trusted tests work for every app.

The runner sets FIXTURE_APP_NAME from the case manifest's "app".
`replays` is None when a team has no rule about recording replays; that test is then skipped.
"""

APPS = {
    "payments-webhooks": {
        "route": "/webhooks/provider",
        "payments": "payments",
        "event_field": "provider_event_id",
        "ledger": "ledger",
        "ledger_customer_field": "customer_id",
        "ledger_amount_field": "amount",
        "replays": "replays",
        "replay_event_field": "event_id",
    },
    "platform-webhooks": {
        "route": "/webhooks/provider",
        "payments": "charges",
        "event_field": "gateway_event_id",
        "ledger": "account_entries",
        "ledger_customer_field": "account_id",
        "ledger_amount_field": "amount_cents",
        "replays": None,
        "replay_event_field": None,
    },
}
