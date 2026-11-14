"""Provider payment callbacks."""

from fastapi import APIRouter
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from . import ledger
from .db import get_db

router = APIRouter()


class PaymentCallback(BaseModel):
    id: str
    customer_id: str
    amount: int


def store_payment(callback: PaymentCallback) -> bool:
    """Store the payment. Returns False when this provider event was already stored."""
    try:
        get_db().payments.insert_one(
            {
                "provider_event_id": callback.id,
                "customer_id": callback.customer_id,
                "amount": callback.amount,
            }
        )
    except DuplicateKeyError:
        return False
    return True


@router.post("/webhooks/provider")
def process_callback(callback: PaymentCallback) -> dict:
    if not store_payment(callback):
        # Already processed: don't credit again, record the replay for reconciliation.
        ledger.mark_replayed(callback.id)
        return {"ok": True, "duplicate": True}
    ledger.credit(callback.customer_id, callback.amount, callback.id)
    return {"ok": True}
