"""Inbound payment notifications."""

from fastapi import APIRouter
from pydantic import BaseModel

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
    payments.insert_one(
        {
            "provider_event_id": notification.id,
            "customer_id": notification.customer_id,
            "amount": notification.amount,
        }
    )
    ledger.credit(notification.customer_id, notification.amount, notification.id)
    return {"ok": True}
