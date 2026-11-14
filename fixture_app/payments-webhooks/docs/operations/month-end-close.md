# Month-end close: payments ledger

Owner: Payments team, with Finance (reconciliation owner) · Applies to: `payments-webhooks` · Review: quarterly

This document describes how the payments ledger is closed at the end of each month: what has to be true before close, who does what, and how discrepancies between our ledger and the provider's settlement report are explained. Most of it is Finance's process; the parts that depend on how `payments-webhooks` records data are marked **(service)**.

## 1. Calendar

| When (Toronto time) | What |
| --- | --- |
| Last business day, 12:00 | Deploy freeze for `payments-webhooks` begins (see the runbook, section 3) |
| Last business day, 18:00 | Provider publishes the draft settlement report for the month |
| Last business day, 23:59 | Ledger snapshot taken; month is closed for new credits |
| First business day, 10:00 | Finance runs the matching job and reviews exceptions |
| Second business day, 17:00 | Sign-off, or escalation to the reconciliation owner |

Credits that arrive after the snapshot belong to the next month and are matched there.

## 2. Roles

- **Reconciliation owner (Finance):** runs the matching job, reviews exceptions, signs off.
- **Payments on-call:** answers questions about specific event IDs and ledger rows during the review window.
- **Payments tech lead:** approves any manual ledger adjustment.

## 3. Inputs

1. **Provider settlement report** (CSV, one row per delivery attempt): `event_id`, `customer_id`, `amount`, `attempt`, `delivered_at`, `http_status`.
2. **Ledger snapshot** (from the `ledger` collection): one row per credit, keyed by `event_id`.
3. **Replay records (service)** (from the `replays` collection): one row per re-delivery of an event we had already processed.
4. **Manual adjustments log**, kept by Finance.

The settlement report counts every delivery attempt, including the provider's retries, so it almost always has more rows than the ledger has credits. The matching job explains the difference.

## 4. The matching job

The job runs these steps in order and writes every row it can't explain to the exceptions list.

1. **Normalize amounts.** Both sides are in cents; the report's `amount` is converted from a decimal string.
2. **Group the report by `event_id`.** Each event ID should end up with exactly one ledger credit, however many delivery attempts it had.
3. **Match credits.** Each ledger credit is matched to its event ID in the report. A credit without a settled event goes to the exceptions list as "unsettled credit".
4. **Explain extra delivery attempts.** For an event ID with more delivery attempts than credits, the job looks for the corresponding replay records (see 5.2).
5. **Check totals per customer.** The sum of credits per customer must equal the provider's settled total for that customer.
6. **Publish the exceptions list** to Finance.

## 5. Common discrepancies and how they're explained

### 5.1 Timing differences

An event delivered at 23:58 and credited at 00:01 lands in different months on each side. The job matches across the boundary for events within ten minutes of the snapshot, so these don't need manual work.

### 5.2 Provider re-deliveries **(service)**

The provider re-delivers an event when our response was slow or failed (see the runbook, section 5). When a re-delivery arrives for an event we have already processed, `payments-webhooks` must not credit the customer again, **and must record the replay by calling `ledger.mark_replayed(event_id)`**. That record is what step 4 of the matching job uses to explain why the provider counts more deliveries than we have credits.

If a replay is not recorded, the extra delivery attempt shows up as an unexplained discrepancy, and the month can't be signed off until someone traces it by hand.

### 5.3 Refunds and chargebacks

Refunds arrive as separate provider events with negative amounts and their own event IDs. They are credited (as negative amounts) and matched like any other event.

### 5.4 Manual adjustments

Any manual ledger change needs the tech lead's approval and an entry in the adjustments log with the event ID, the amount and the reason. The matching job reads the log and excludes adjusted rows from the exceptions list.

## 6. Sign-off

Finance signs off when the exceptions list is empty, or every remaining exception has a written explanation approved by the reconciliation owner. The signed-off report is archived with the month's ledger snapshot.

## 7. Escalation

Exceptions that can't be explained by the end of the second business day go to the reconciliation owner with the event IDs, the ledger rows and the report rows involved. Payments on-call joins the review if the exception points at the service.

## Appendix: glossary

- **Delivery attempt:** one HTTP request from the provider to our webhook endpoint.
- **Event ID:** the provider's unique identifier for one payment event. A customer can have many events.
- **Replay:** a delivery attempt for an event we had already processed.
- **Settlement report:** the provider's monthly list of delivery attempts and settled amounts.
