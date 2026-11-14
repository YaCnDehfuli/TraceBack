# payments-webhooks runbook

Owner: Payments team · Pager rotation: payments-oncall

## 1. What this service does

`payments-webhooks` receives payment notifications from our payment provider at `POST /webhooks/provider`. Each notification is one provider event with an `id`, a `customer_id` and an `amount` in cents. For every new event we store a row in `payments` and credit the customer in the ledger.

## 2. Running locally

- Start a local MongoDB and set `FIXTURE_MONGODB_URI` (default `mongodb://localhost:27017`).
- `FIXTURE_DB` selects the database (default `fixture_payments`).
- Start the API with `uvicorn app.main:app --reload`.

## 3. Deploys

Deploys go out through the standard pipeline. Roll back with the previous image tag. Never deploy during the month-end close window (last business day, 18:00 to 23:59 Toronto time).

## 4. Alerts

| Alert | Meaning | First step |
| --- | --- | --- |
| `webhooks_5xx_rate` | More than 1% of provider notifications fail | Check the service logs for the exception and the event IDs involved |
| `webhooks_latency_p99` | p99 above 800 ms | Check database latency; the provider times out at 10 s and retries |
| `ledger_drift` | Ledger totals differ from provider settlement totals | Page the reconciliation owner; see section 6 |

## 5. Provider behaviour

- The provider signs every request; signature checks happen at the edge, not in this service.
- If we don't answer within 10 seconds, or answer with a 5xx, the provider **retries the same event** with the same `id`, up to 8 times over 24 hours.
- Event IDs are unique per event. A customer can have many events.

## 6. Reconciliation

At month-end, Finance compares the provider's settlement report with our ledger. The calendar, the matching job, how discrepancies are explained and who signs off are in `docs/operations/month-end-close.md`. Payments on-call is expected to answer questions about specific event IDs during the review window.
