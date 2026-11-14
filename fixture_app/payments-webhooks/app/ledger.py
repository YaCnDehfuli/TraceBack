"""Customer ledger."""

from datetime import datetime, timezone

from .db import get_db


def credit(customer_id: str, amount: int, event_id: str) -> None:
    get_db().ledger.insert_one(
        {
            "customer_id": customer_id,
            "amount": amount,
            "event_id": event_id,
            "at": datetime.now(timezone.utc),
        }
    )


def balance(customer_id: str) -> int:
    rows = get_db().ledger.aggregate(
        [
            {"$match": {"customer_id": customer_id}},
            {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
        ]
    )
    row = next(rows, None)
    return row["total"] if row else 0


def mark_replayed(event_id: str) -> None:
    get_db().replays.insert_one({"event_id": event_id, "at": datetime.now(timezone.utc)})
