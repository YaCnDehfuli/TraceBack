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

At month-end, finance compares the provider's settlement report with our ledger.

### 6.1 Settlement report

The provider's report lists every delivery attempt it made, including retries, per event ID. Our ledger lists each credit once.

### 6.2 Matching rules

1. Every settled event ID must have exactly one ledger credit.
2. Credits without a settled event are flagged for manual review.
3. **Replayed deliveries.** When the provider delivers an event we have already processed, we must not credit the customer again, and we must record the replay by calling `ledger.mark_replayed(event_id)`. The reconciliation job uses these records to explain why the provider's delivery count is higher than our credit count. A replay that isn't recorded shows up as an unexplained discrepancy and blocks the month-end close.

### 6.3 Escalation

Discrepancies that the matching rules can't explain go to the reconciliation owner in finance, with the event IDs and the ledger rows involved.
