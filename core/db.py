"""One shared MongoDB client for the app. Collections are named here so nobody mistypes them."""

from __future__ import annotations

from functools import lru_cache

from pymongo import MongoClient
from pymongo.database import Database

from core.config import get_settings


class Collections:
    INCIDENTS = "incidents"
    RUNS = "runs"
    RUN_EVENTS = "run_events"
    MEMORIES = "memories"  # written ONLY by the memory service (P2)
    MEMORY_AUDIT = "memory_audit"  # append-only, written ONLY by the memory service (P2)
    POLICIES = "policies"


@lru_cache
def get_client() -> MongoClient:
    uri = get_settings().mongodb_uri.get_secret_value()
    if not uri:
        raise RuntimeError(
            "MONGODB_URI is not set. Copy .env.example to .env and fill it in (team guide, section 6.3)."
        )
    # tz_aware=True: datetimes come back as UTC-aware, which expiry comparisons rely on.
    return MongoClient(uri, appname="traceback", tz_aware=True, serverSelectionTimeoutMS=10_000)


def get_db(name: str | None = None) -> Database:
    """Your database from MONGODB_DB (traceback_p1 / _p2 / _p3 / traceback_demo), or an explicit one."""
    return get_client()[name or get_settings().mongodb_db]
