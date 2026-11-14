"""Payment provider webhooks."""

from fastapi import APIRouter
from pydantic import BaseModel

from . import ledger
from .db import get_db

router = APIRouter()


class ProviderEvent(BaseModel):
    id: str
    customer_id: str
    amount: int


@router.post("/webhooks/provider")
def receive(event: ProviderEvent) -> dict:
    get_db().payments.insert_one(
        {
            "provider_event_id": event.id,
            "customer_id": event.customer_id,
            "amount": event.amount,
        }
    )
    ledger.credit(event.customer_id, event.amount, event.id)
    return {"ok": True}
