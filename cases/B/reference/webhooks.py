"""Inbound payment notifications."""

from fastapi import APIRouter
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

from . import ledger
from .db import get_db

router = APIRouter()


class PaymentNotification(BaseModel):
    id: str
    customer_id: str
    amount: int


@router.post("/webhooks/provider")
def handle_provider_event(notification: PaymentNotification) -> dict:
    payments = get_db().payments
    try:
        payments.insert_one(
            {
                "provider_event_id": notification.id,
                "customer_id": notification.customer_id,
                "amount": notification.amount,
            }
        )
    except DuplicateKeyError:
        # Already processed: don't credit again, record the replay for reconciliation.
        ledger.mark_replayed(notification.id)
        return {"ok": True, "duplicate": True}
    ledger.credit(notification.customer_id, notification.amount, notification.id)
    return {"ok": True}
