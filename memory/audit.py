"""Append-only audit log. Never stores memory text.

contentHash is an HMAC keyed by a secret that lives only inside the memory
document. Forgetting deletes the document and the key, so old
hashes can no longer be linked to any content.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any

from pymongo.database import Database


def content_hash(memory: dict) -> str:
    content = json.dumps(
        {k: memory.get(k) for k in ("retrievalText", "confirmedCause", "resolution", "applicability")},
        sort_keys=True,
        default=str,
    )
    return hmac.new(bytes.fromhex(memory["hmacSecret"]), content.encode(), hashlib.sha256).hexdigest()


def log(
    db: Database,
    *,
    tenant_id: str,
    event: str,
    actor: dict,
    memory_id: str | None = None,
    version: int | None = None,
    run_id: str | None = None,
    reason: str | None = None,
    details: dict[str, Any] | None = None,
    content_hash: str | None = None,
) -> None:
    db.memory_audit.insert_one({
        "tenantId": tenant_id,
        "memoryId": memory_id,
        "version": version,
        "event": event,
        "actor": actor,
        "runId": run_id,
        "reason": reason,
        "details": details or {},
        "contentHash": content_hash,
        "at": datetime.now(UTC),
    })


def log_many(db: Database, events: list[dict]) -> None:
    """Batch insert, to save round trips to us-west-1 (each costs about 70 ms)."""
    if events:
        now = datetime.now(UTC)
        db.memory_audit.insert_many([{**e, "at": now} for e in events], ordered=False)
