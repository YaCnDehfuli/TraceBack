"""Shared test setup. Tests marked `atlas` need a live Atlas connection and are skipped in
`uv run pytest -m "not atlas"`."""

from __future__ import annotations

import json

import pytest

from contracts.models import Principal
from core.config import get_settings

DEMO_PRINCIPALS = {
    "test-payments-eng": {"tenantId": "demo-org", "teamId": "team-payments", "role": "engineer"},
    "test-payments-admin": {"tenantId": "demo-org", "teamId": "team-payments", "role": "memory_admin"},
    "test-platform-eng": {"tenantId": "demo-org", "teamId": "team-platform", "role": "engineer"},
}


@pytest.fixture(autouse=True)
def _test_settings(monkeypatch):
    """Tests never depend on your .env: fixed demo principals, settings cache cleared around each test."""
    monkeypatch.setenv("DEMO_PRINCIPALS", json.dumps(DEMO_PRINCIPALS))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def payments() -> Principal:
    return Principal(tenant_id="demo-org", team_id="team-payments", authorized_repos=["payments-webhooks"])


@pytest.fixture
def platform() -> Principal:
    return Principal(tenant_id="demo-org", team_id="team-platform", authorized_repos=["platform-webhooks"])
