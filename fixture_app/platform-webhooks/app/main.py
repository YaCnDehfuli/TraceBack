"""platform-webhooks: receives gateway notifications and adds account entries."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .db import ensure_indexes, get_db
from .gateway import router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_indexes(get_db())
    yield


app = FastAPI(title="platform-webhooks", lifespan=lifespan)
app.include_router(router)
