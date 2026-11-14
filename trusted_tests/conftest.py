"""Shared fixtures for the trusted tests.

The runner copies a practice app into a temporary folder, points FIXTURE_APP_DIR at it and sets
FIXTURE_APP_NAME to the app's name. Each test gets its own fresh database, dropped afterwards.
"""

import os
import sys
import uuid
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
APP_NAME = os.environ.get("FIXTURE_APP_NAME", "payments-webhooks")
APP_DIR = Path(os.environ.get("FIXTURE_APP_DIR", REPO / "fixture_app" / APP_NAME))
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(HERE))

from fastapi.testclient import TestClient  # noqa: E402

from apps import APPS  # noqa: E402
from app.db import get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def names():
    return APPS[APP_NAME]


@pytest.fixture
def db():
    prefix = os.environ.get("FIXTURE_DB_PREFIX", "fixture_test")
    name = f"{prefix}_{uuid.uuid4().hex[:8]}"
    os.environ["FIXTURE_DB"] = name
    database = get_db()
    yield database
    database.client.drop_database(name)


@pytest.fixture
def client(db):
    # Server errors come back as HTTP 500 responses instead of exceptions,
    # so a crash reads as a clear assertion failure.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
