"""payments-webhooks: receives payment notifications from the provider and credits customers."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import ensure_indexes, get_db
from .webhooks import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_indexes(get_db())
    yield


app = FastAPI(title="payments-webhooks", lifespan=lifespan)
app.include_router(router)
