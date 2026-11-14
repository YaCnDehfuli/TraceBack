# payments-webhooks

Receives payment notifications from our payment provider and credits customers in the ledger.

- `app/main.py`: the FastAPI app.
- `app/webhooks.py`: `POST /webhooks/provider`.
- `app/ledger.py`: ledger operations.
- `app/db.py`: database access and indexes.
- `docs/RUNBOOK.md`: on-call runbook. `docs/operations/`: operational procedures, including month-end close.

Run locally: start MongoDB, set `FIXTURE_MONGODB_URI` (default `mongodb://localhost:27017`), then `uvicorn app.main:app --reload`.
