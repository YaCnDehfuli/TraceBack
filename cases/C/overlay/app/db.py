"""Database access for the payments webhook service."""

import os
from functools import cache

from pymongo import ASCENDING, MongoClient
from pymongo.database import Database


@cache
def _client(uri: str) -> MongoClient:
    return MongoClient(uri, serverSelectionTimeoutMS=3000)


def get_db() -> Database:
    uri = os.environ.get("FIXTURE_MONGODB_URI", "mongodb://localhost:27017")
    name = os.environ.get("FIXTURE_DB", "fixture_payments")
    return _client(uri)[name]


def ensure_indexes(db: Database) -> None:
    # One payment per customer.
    db.payments.create_index([("customer_id", ASCENDING)], unique=True)
