"""A memory goes stale when the code it was proven against changes.
Offline tests (fingerprints) run in CI; the end-to-end one needs Atlas."""

from __future__ import annotations

import json
import time

import pytest

from memory.staleness import changed_files, fingerprint, proven_against


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A throwaway code root with one repository, used instead of fixture_app/."""
    monkeypatch.setenv("TRACEBACK_CODE_ROOT", str(tmp_path))
    app = tmp_path / "payments-webhooks" / "app"
    app.mkdir(parents=True)
    (app / "webhooks.py").write_bytes(b"def receive(event):\n    insert(event)\n")
    return app / "webhooks.py"


def test_unchanged_code_is_not_stale(repo):
    proven = proven_against("payments-webhooks", ["app/webhooks.py"])
    assert proven and changed_files("payments-webhooks", proven) == []


def test_one_edited_line_makes_it_stale(repo):
    proven = proven_against("payments-webhooks", ["app/webhooks.py"])
    repo.write_bytes(b"def receive(event):\n    upsert(event)\n")
    assert changed_files("payments-webhooks", proven) == ["app/webhooks.py"]


def test_line_endings_alone_do_not_make_it_stale(repo):
    proven = proven_against("payments-webhooks", ["app/webhooks.py"])
    repo.write_bytes(repo.read_bytes().replace(b"\n", b"\r\n"))  # a Windows checkout of the same code
    assert changed_files("payments-webhooks", proven) == []


def test_deleted_file_is_stale_but_unknown_repo_is_not(repo):
    proven = proven_against("payments-webhooks", ["app/webhooks.py"])
    repo.unlink()
    assert changed_files("payments-webhooks", proven) == ["app/webhooks.py"]
    assert changed_files("billing-exports", [{"path": "x.py", "sha256": "0"}]) == []  # not checked out here
    assert proven_against("billing-exports", ["x.py"]) == []


def test_never_reads_outside_the_repository(repo):
    assert fingerprint("payments-webhooks", "../../etc/passwd") is None


@pytest.mark.atlas
def test_card_recall_and_stale_endpoint_flip_when_the_code_changes(repo, monkeypatch, payments):
    from core.config import get_settings

    if not get_settings().mongodb_uri.get_secret_value():
        pytest.skip("MONGODB_URI not set")
    from fastapi.testclient import TestClient

    from api.main import app
    from memory.store import AtlasMemoryStore
    from tests.conftest import DEMO_PRINCIPALS
    from tests.memory.test_leakage import draft, obs, proof

    monkeypatch.setenv("DEMO_PRINCIPALS", json.dumps(DEMO_PRINCIPALS))
    get_settings.cache_clear()
    client, s = TestClient(app), AtlasMemoryStore()
    mem_id = s.promote(payments, draft(), proof())  # draft touches app/webhooks.py in payments-webhooks
    try:
        key = {"X-API-Key": "test-payments-eng"}
        assert client.get(f"/memories/{mem_id}/stale", headers=key).json()["stale"] is False
        assert client.get(f"/memories/{mem_id}", headers=key).json()["stale"] is False

        repo.write_bytes(b"def receive(event):\n    upsert(event)  # someone changed this\n")
        r = client.get(f"/memories/{mem_id}/stale", headers=key).json()
        assert r == {"memoryId": mem_id, "stale": True, "changedFiles": ["app/webhooks.py"], "checked": True}
        assert client.get(f"/memories/{mem_id}", headers=key).json()["stale"] is True

        end = time.time() + 60
        while not s.is_searchable(payments, mem_id) and time.time() < end:
            time.sleep(1)
        cand = next(c for c in s.recall(payments, obs(), "run_stale") if c.memory_id == mem_id)
        assert cand.stale is True  # still offered (a warning), but flagged

        assert client.get(f"/memories/{mem_id}/stale", headers={"X-API-Key": "test-platform-eng"}).status_code == 404
    finally:
        s.memories.delete_many({"_id": mem_id})
        s.db.memory_audit.delete_many({"memoryId": mem_id})
