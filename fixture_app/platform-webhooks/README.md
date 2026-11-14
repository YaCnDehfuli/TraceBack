# platform-webhooks

Platform billing's receiver for payment-provider notifications.

- `app/main.py`: the FastAPI app.
- `app/gateway.py`: `POST /webhooks/provider`.
- `app/accounts.py`: account entries.
- `app/db.py`: database access and indexes.
- `docs/RUNBOOK.md`: on-call runbook.

Run locally: start MongoDB, set `FIXTURE_MONGODB_URI` (default `mongodb://localhost:27017`), then `uvicorn app.main:app --reload`.
