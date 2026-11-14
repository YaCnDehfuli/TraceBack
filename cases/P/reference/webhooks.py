"""Payment provider webhooks."""

from fastapi import APIRouter
from pydantic import BaseModel
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
    try:
        get_db().payments.insert_one(
            {
                "provider_event_id": event.id,
                "customer_id": event.customer_id,
                "amount": event.amount,
            }
        )
    except DuplicateKeyError:
        # Already processed: don't credit again, record the replay for reconciliation.
        ledger.mark_replayed(event.id)
        return {"ok": True, "duplicate": True}
    ledger.credit(event.customer_id, event.amount, event.id)
    return {"ok": True}
