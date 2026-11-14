"""Payment posting endpoint for provider notifications."""

from fastapi import APIRouter
from pydantic import BaseModel

from . import ledger
from .db import get_db

router = APIRouter()


class PostedPayment(BaseModel):
    id: str
    customer_id: str
    amount: int


@router.post("/webhooks/provider")
def on_payment_posted(posted: PostedPayment) -> dict:
    collection = get_db()["payments"]
    record = {
        "provider_event_id": posted.id,
        "customer_id": posted.customer_id,
        "amount": posted.amount,
    }
    collection.insert_one(record)
    ledger.credit(posted.customer_id, posted.amount, posted.id)
    return {"ok": True}
