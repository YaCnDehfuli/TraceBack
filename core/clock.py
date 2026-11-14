"""Time, ids and fingerprints. Always use these instead of datetime.now() or ad-hoc ids."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime


def utc_now() -> datetime:
    """Timezone-aware UTC now. Never compare expiry dates with naive datetimes."""
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    """Readable unique id, e.g. new_id("run") -> "run_3f9a1c2b7d4e"."""
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def sha256_text(text: str) -> str:
    """Content fingerprint used for evidence hashes and memory content hashes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
