# payments-webhooks (practice app, owner: P3)

A tiny FastAPI app with a planted bug (P3-1). The agent may change only the files listed in each
case's `patchable_files`.

To build:
- `app/webhooks.py`: the buggy handler. A second delivery of the same event crashes with E11000.
- `app/ledger.py`: `credit()` and `mark_replayed()`. **No docstrings or comments about the convention.**
- A unique index on `provider_event_id`.
- `docs/RUNBOOK.md`: the team convention that a replayed webhook must be recorded with
  `ledger.mark_replayed(event_id)` for month-end reconciliation, deep in a reconciliation section (plan 4.1).
