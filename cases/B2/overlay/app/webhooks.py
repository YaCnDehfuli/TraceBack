"""Provider payment callbacks."""

from fastapi import APIRouter
from pydantic import BaseModel

from . import ledger
from .db import get_db

router = APIRouter()


class PaymentCallback(BaseModel):
    id: str
    customer_id: str
    amount: int


def store_payment(callback: PaymentCallback) -> None:
    get_db().payments.insert_one(
        {
            "provider_event_id": callback.id,
            "customer_id": callback.customer_id,
            "amount": callback.amount,
        }
    )


@router.post("/webhooks/provider")
def process_callback(callback: PaymentCallback) -> dict:
    store_payment(callback)
    ledger.credit(callback.customer_id, callback.amount, callback.id)
    return {"ok": True}
