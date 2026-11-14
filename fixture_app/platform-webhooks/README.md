# platform-webhooks (practice app, owner: P3)

Team Platform's sibling of `payments-webhooks`: the same planted bug with renamed internals (P3-7).
Used for the Fence beat: Platform must never see Payments' memory.

Layout (names match `trusted_tests/apps.py["platform-webhooks"]`):
- `app/gateway.py`: the buggy handler `on_gateway_event`. A second delivery of the same event crashes
  with E11000 on `gateway_event_id_1`.
- `app/accounts.py`: `add_entry()` writes to `account_entries` (`account_id`, `amount_cents`, `event_id`).
- `app/db.py`: collection `charges` with a unique index on `gateway_event_id`.
- `docs/RUNBOOK.md`: Platform's runbook. Unlike Payments, it has **no rule about recording replays**,
  so `test_replay_recorded_for_reconciliation` is skipped for this app.
