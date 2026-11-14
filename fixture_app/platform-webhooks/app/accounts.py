"""Account entries."""

from datetime import datetime, timezone

from .db import get_db


def add_entry(account_id: str, amount_cents: int, event_id: str) -> None:
    get_db().account_entries.insert_one(
        {
            "account_id": account_id,
            "amount_cents": amount_cents,
            "event_id": event_id,
            "created_at": datetime.now(timezone.utc),
        }
    )


def total_for(account_id: str) -> int:
    rows = get_db().account_entries.aggregate(
        [
            {"$match": {"account_id": account_id}},
            {"$group": {"_id": None, "total": {"$sum": "$amount_cents"}}},
        ]
    )
    row = next(rows, None)
    return row["total"] if row else 0
