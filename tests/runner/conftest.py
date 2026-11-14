"""Fixtures for the safe-test-runner tests.

Every test here runs the real trusted tests against a real MongoDB, so the whole folder is skipped
(with a clear reason) when the fixture database is not reachable.
"""

from __future__ import annotations

import pytest

from runner import sandbox


def _fixture_db_unreachable_reason() -> str | None:
    """None when the fixture database answers a ping within 2 s, else a short reason."""
    try:
        from pymongo import MongoClient

        MongoClient(sandbox.fixture_uri(), serverSelectionTimeoutMS=2000).admin.command("ping")
        return None
    except Exception as exc:  # noqa: BLE001 - any failure means "not reachable"
        return type(exc).__name__


def pytest_collection_modifyitems(config, items):
    reason = _fixture_db_unreachable_reason()
    if reason is None:
        return
    skip = pytest.mark.skip(
        reason=f"fixture MongoDB not reachable (set FIXTURE_MONGODB_URI, e.g. mongodb://localhost:27017): {reason}"
    )
    for item in items:
        if "tests/runner/" in item.nodeid.replace("\\", "/"):
            item.add_marker(skip)
