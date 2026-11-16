"""Team retention policies, with the demo values."""
from __future__ import annotations

from datetime import datetime, timedelta

from pymongo.database import Database

HOUR = 3600

# Demo policy: 24 h life, 48 h max, 10 min purge grace (long enough to outlast a day of demos).
DEMO_POLICY = {
    "ttlSeconds": 24 * HOUR,
    "maxLifetimeSeconds": 48 * HOUR,
    "purgeGraceSeconds": 10 * 60,
    "renewOnReverify": True,
    "shareRole": "memory_admin",
    "policyVersion": 1,
}


def get_policy(db: Database, tenant_id: str, team_id: str) -> dict:
    doc = db.policies.find_one({"_id": f"{tenant_id}:{team_id}"})
    return {**DEMO_POLICY, **(doc or {})}


def expiry_for(policy: dict, created_at: datetime, now: datetime) -> tuple[datetime, datetime]:
    """(expiresAt, purgeAt), with renewals capped by the max lifetime from creation."""
    expires = min(
        now + timedelta(seconds=policy["ttlSeconds"]),
        created_at + timedelta(seconds=policy["maxLifetimeSeconds"]),
    )
    return expires, expires + timedelta(seconds=policy["purgeGraceSeconds"])
