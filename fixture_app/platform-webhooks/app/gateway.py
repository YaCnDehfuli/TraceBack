"""Gateway event intake."""

from fastapi import APIRouter
from pydantic import BaseModel

from . import accounts
from .db import get_db

router = APIRouter()


class GatewayEvent(BaseModel):
    id: str
    customer_id: str
    amount: int


@router.post("/webhooks/provider")
def on_gateway_event(evt: GatewayEvent) -> dict:
    get_db().charges.insert_one(
        {
            "gateway_event_id": evt.id,
            "account_id": evt.customer_id,
            "amount_cents": evt.amount,
        }
    )
    accounts.add_entry(evt.customer_id, evt.amount, evt.id)
    return {"ok": True}
