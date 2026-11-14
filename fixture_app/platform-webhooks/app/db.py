"""Database access for the platform gateway service."""

import os
from functools import lru_cache

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database


@lru_cache(maxsize=None)
def _client(uri: str) -> MongoClient:
    return MongoClient(uri, serverSelectionTimeoutMS=3000)


def get_db() -> Database:
    uri = os.environ.get("FIXTURE_MONGODB_URI", "mongodb://localhost:27017")
    name = os.environ.get("FIXTURE_DB", "fixture_platform")
    return _client(uri)[name]


def ensure_indexes(db: Database) -> None:
    # Each gateway event is stored once.
    db.charges.create_index([("gateway_event_id", ASCENDING)], unique=True)
