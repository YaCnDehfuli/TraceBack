"""The safe test runner (runner.sandbox.LocalRunner): the only thing that may say "the fix works".

These tests execute the real trusted tests in the real sandbox against a fixture MongoDB; they are
skipped when that database is not reachable (see tests/runner/conftest.py).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest
from pymongo import MongoClient

from contracts.models import FilePatch, VerificationResult
from runner import sandbox
from runner.sandbox import CASES, LocalRunner, load_manifest

# case -> file of the reference fix (relative to cases/<case>/)
REFERENCE_FIXES = {
    "A": "reference/webhooks.py",
    "B": "reference/webhooks.py",
    "B2": "reference/webhooks.py",
    "B3": "reference/webhooks.py",
    "D": "reference/gateway.py",
    "P": "reference/webhooks.py",
}
FAKE_SECRETS = {
    "MONGODB_URI": "mongodb+srv://secret-user:secret-pass@atlas.example.net/prod",
    "LLM_API_KEY": "sk-dummy-llm-key-123",
    "VOYAGE_API_KEY": "pa-dummy-voyage-key-456",
    "ELEVENLABS_API_KEY": "el-dummy-789",
}

runner = LocalRunner()


# --------------------------------------------------------------------------- helpers


def _read(case_id: str, relative: str) -> str:
    return (CASES / case_id / relative).read_text(encoding="utf-8")


def _patch_for(case_id: str, content: str) -> FilePatch:
    """A patch for the case's (single) patchable file, as the CLI builds it."""
    return FilePatch(path=load_manifest(case_id).patchable_files[0], new_content=content)


def _reference_patch(case_id: str) -> FilePatch:
    return _patch_for(case_id, _read(case_id, REFERENCE_FIXES[case_id]))


def _failing(result: VerificationResult) -> set[str]:
    return {t.name for t in result.tests if not t.passed}


def _describe(result: VerificationResult) -> str:
    failing = {t.name: t.detail for t in result.tests if not t.passed}
    return f"status={result.status} detail={result.detail!r} failing={failing}"


def _fixture_databases(prefix: str) -> list[str]:
    client = MongoClient(sandbox.fixture_uri(), serverSelectionTimeoutMS=2000)
    return [name for name in client.list_database_names() if name.startswith(prefix)]


# --------------------------------------------------------------------------- 1. the bugs are real


@pytest.mark.parametrize("case_id", ["A", "B", "C", "D"])
def test_reproduce_shows_the_bug_is_real(case_id):
    result = runner.reproduce(case_id)
    assert result.status == "failed", f"reproduce() must report 'failed' (the bug exists): {_describe(result)}"
    assert result.before_failed, f"the reproduction test must fail on the original code: {_describe(result)}"
    assert not result.after_passed
    assert not result.verified
    assert result.evidence_hashes, "a run must leave evidence hashes"


# --------------------------------------------------------------------------- 2. reference fixes pass


@pytest.mark.parametrize("case_id", list(REFERENCE_FIXES))
def test_reference_fix_passes(case_id):
    result = runner.verify(case_id, _reference_patch(case_id))
    assert result.status == "passed", f"case {case_id} reference fix should pass: {_describe(result)}"
    assert result.before_failed and result.after_passed and result.verified
    assert not _failing(result), f"no trusted test may fail: {_describe(result)}"
    assert len(result.evidence_hashes) == 3, "two junit hashes plus the patch hash"


def test_case_d_patches_the_gateway_file_and_has_no_replay_rule():
    assert load_manifest("D").patchable_files == ["app/gateway.py"]
    # Platform has no rule about recording replays: that trusted test is skipped, not failed.
    result = runner.verify("D", _reference_patch("D"))
    skipped = [t.name for t in result.tests if t.detail and t.detail.startswith("skipped")]
    assert skipped == ["test_replay_recorded_for_reconciliation"], _describe(result)


# --------------------------------------------------------------------------- 3-5. wrong fixes fail


def test_remembered_fix_from_case_a_does_not_pass_look_alike_case_c():
    """Case C is a look-alike (unique index on customer_id): A's fix must not be accepted."""
    result = runner.verify("C", _patch_for("C", _read("A", "reference/webhooks.py")))
    assert result.status == "failed", f"A's fix must fail on C: {_describe(result)}"
    assert result.before_failed, "the C bug is real on the original code"
    assert not result.after_passed and not result.verified
    failing = _failing(result)
    assert {"test_distinct_events_same_customer", "test_unique_index_still_present"} <= failing, _describe(result)


def test_poisoned_fix_fails_because_the_unique_index_must_stay():
    result = runner.verify("P", _patch_for("P", _read("P", "poisoned/webhooks.py")))
    assert result.status == "failed", f"the poisoned fix must be rejected: {_describe(result)}"
    assert _failing(result) == {"test_unique_index_still_present"}, _describe(result)
    assert not result.verified


def test_try_except_without_recording_the_replay_fails_only_the_reconciliation_test():
    lines = _read("A", "reference/webhooks.py").splitlines(keepends=True)
    kept = [line for line in lines if "ledger.mark_replayed" not in line]
    assert len(kept) == len(lines) - 1, "expected to remove exactly the mark_replayed line"
    result = runner.verify("A", _patch_for("A", "".join(kept)))
    assert result.status == "failed", _describe(result)
    assert _failing(result) == {"test_replay_recorded_for_reconciliation"}, _describe(result)
    assert result.before_failed and not result.after_passed


# --------------------------------------------------------------------------- 6. allowlist


@pytest.mark.parametrize("path", ["app/db.py", "../trusted_tests/test_webhooks.py", "app\\db.py"])
def test_patch_outside_the_allowlist_is_rejected_without_running_tests(path, monkeypatch):
    def no_subprocess(*args, **kwargs):
        raise AssertionError("no test process may start for a disallowed file")

    monkeypatch.setattr(sandbox.subprocess, "run", no_subprocess)
    result = runner.verify("A", FilePatch(path=path, new_content="print('hello')\n"))
    assert result.status == "failed", _describe(result)
    assert result.detail and "not allowed" in result.detail, _describe(result)
    assert result.tests == [], "no tests may run for a disallowed file"
    assert not result.before_failed and not result.after_passed and not result.verified


# --------------------------------------------------------------------------- 7. secrets stay out


def test_safe_env_keys_contain_no_secrets():
    names = {key.upper() for key in sandbox.SAFE_ENV_KEYS}
    for banned in (*(k.upper() for k in FAKE_SECRETS), "FIXTURE_MONGODB_URI"):
        assert banned not in names, f"{banned} must not be in SAFE_ENV_KEYS"
    assert not any(marker in n for n in names for marker in ("KEY", "SECRET", "TOKEN", "URI")), names


def test_secrets_in_the_parent_environment_never_reach_the_test_process(monkeypatch):
    for key, value in FAKE_SECRETS.items():
        monkeypatch.setenv(key, value)

    # Capture the exact environment the runner hands to the trusted-test subprocess, then run it for real.
    seen: list[dict] = []
    real_run = subprocess.run

    def spy(cmd, **kwargs):
        seen.append(dict(kwargs["env"]))
        return real_run(cmd, **kwargs)

    monkeypatch.setattr(sandbox.subprocess, "run", spy)
    result = runner.reproduce("A")
    assert result.status == "failed" and result.before_failed, f"the run itself must work: {_describe(result)}"

    assert seen, "the runner must start a test subprocess"
    for env in seen:
        for key in FAKE_SECRETS:
            assert key not in env, f"{key} leaked into the sandbox environment"
        assert not set(FAKE_SECRETS.values()) & set(env.values()), "a secret value leaked under another name"
        # Only allowlisted names plus the runner's own FIXTURE_* / PYTHONDONTWRITEBYTECODE settings.
        extra = set(env) - set(sandbox.SAFE_ENV_KEYS)
        assert all(k.startswith("FIXTURE_") or k == "PYTHONDONTWRITEBYTECODE" for k in extra), extra

    # And a process started with exactly that environment really cannot see them.
    probe = real_run(
        [sys.executable, "-c", "import os, json; print(json.dumps(sorted(os.environ)))"],
        env=seen[0], capture_output=True, text=True,
    )
    assert probe.returncode == 0, probe.stderr
    visible = set(json.loads(probe.stdout))
    assert not set(FAKE_SECRETS) & visible, f"secrets visible in the sandbox process: {set(FAKE_SECRETS) & visible}"


# --------------------------------------------------------------------------- 8. cleanup


@pytest.fixture
def private_tmp(monkeypatch):
    """A private temp dir for the runner (any traceback_* folder left in it can only come from this test).

    Uses tempfile directly instead of pytest's tmp_path so it also works where pytest's own temp root is locked.
    """
    with tempfile.TemporaryDirectory(prefix="runner_tests_") as folder:
        monkeypatch.setattr(tempfile, "tempdir", folder)
        yield Path(folder)


def test_verify_leaves_no_databases_or_temp_folders_behind(private_tmp):
    result = runner.verify("A", _reference_patch("A"))
    assert result.status == "passed", _describe(result)

    leftovers = [p.name for p in private_tmp.glob("traceback_*")]
    assert not leftovers, f"temp workspaces were not deleted: {leftovers}"
    databases = _fixture_databases(f"fixture_{result.run_id}")
    assert not databases, f"fixture databases were not dropped: {databases}"


def test_reproduce_also_cleans_up(private_tmp):
    result = runner.reproduce("A")
    assert result.before_failed
    assert not list(private_tmp.glob("traceback_*")), "temp workspace left behind by reproduce()"
    assert not _fixture_databases(f"fixture_{result.run_id}"), "fixture database left behind by reproduce()"
