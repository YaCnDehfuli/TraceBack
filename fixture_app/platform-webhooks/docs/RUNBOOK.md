# platform-webhooks runbook

Owner: Platform team · Pager rotation: platform-oncall

## 1. What this service does

`platform-webhooks` receives gateway notifications at `POST /webhooks/provider`. Each notification is one event with an `id`, a `customer_id` and an `amount` in cents. For every new event we store a row in `charges` and add an entry to `account_entries` for the matching account.

## 2. Running locally

- Start a local MongoDB and set `FIXTURE_MONGODB_URI` (default `mongodb://localhost:27017`).
- `FIXTURE_DB` selects the database (default `fixture_platform`).
- Start the API with `uvicorn app.main:app --reload`.

## 3. Deploys

Deploys go out through the standard pipeline. Roll back with the previous image tag. No deploys on Fridays after 15:00.

## 4. Alerts

| Alert | Meaning | First step |
| --- | --- | --- |
| `gateway_5xx_rate` | More than 1% of gateway notifications fail | Check the service logs for the exception and the event IDs involved |
| `gateway_latency_p99` | p99 above 800 ms | Check database latency; the gateway times out at 10 s and retries |

## 5. Gateway behaviour

- The gateway signs every request; signature checks happen at the edge, not in this service.
- If we don't answer within 10 seconds, or answer with a 5xx, the gateway **retries the same event** with the same `id`.
- Event IDs are unique per event. An account can have many events.
