"""Payment provider webhooks."""

from fastapi import APIRouter
from pydantic import BaseModel
from pymongo import ASCENDING
from pymongo.errors import DuplicateKeyError

from . import ledger
from .db import get_db

router = APIRouter()


class ProviderEvent(BaseModel):
    id: str
    customer_id: str
    amount: int


@router.post("/webhooks/provider")
def receive(event: ProviderEvent) -> dict:
    db = get_db()

    # Event ids are unique per event; keep that guarantee in the database.
    db.payments.create_index([("provider_event_id", ASCENDING)], unique=True)

    # Re-delivery of an already processed event: record it, do not credit again.
    if db.ledger.find_one({"event_id": event.id}) is not None:
        ledger.mark_replayed(event.id)
        return {"ok": True, "duplicate": True}

    # The existing unique customer_id index allows one payments row per
    # customer, so later events for the customer update that row.
    try:
        db.payments.update_one(
            {"customer_id": event.customer_id},
            {
                "$set": {"provider_event_id": event.id},
                "$inc": {"amount": event.amount},
            },
            upsert=True,
        )
    except DuplicateKeyError:
        ledger.mark_replayed(event.id)
        return {"ok": True, "duplicate": True}

    ledger.credit(event.customer_id, event.amount, event.id)
    return {"ok": True}
