"""Safe test runner.

Verifies a proposed fix against the trusted tests, in a throwaway copy of the practice app:

1. Copy the case's app into a fresh temporary folder and show the bug happens on the original code.
2. Copy it again, write the proposed file (only if it's on the case's allowlist), run all trusted tests.
3. Return facts, not opinions. The tests run in a separate process with no project secrets.

`status` is "passed", "failed" or "inconclusive". Inconclusive means our infrastructure broke
(no database, timeout, broken case), never that the fix is good.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "fixture_app"
TRUSTED = REPO / "trusted_tests"
CASES = REPO / "cases"

TIMEOUT_S = 90
MESSAGE_LIMIT = 300

# Only these environment variables reach the test process. No MONGODB_URI, no API keys.
SAFE_ENV_KEYS = (
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA",
)
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")


def _fixture_uri() -> str:
    return os.environ.get("FIXTURE_MONGODB_URI", "mongodb://localhost:27017")


def load_case(case_id: str) -> dict:
    manifest = json.loads((CASES / case_id / "manifest.json").read_text(encoding="utf-8"))
    manifest.setdefault("allowed_files", ["app/webhooks.py"])
    return manifest


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _workspace(case_id: str, manifest: dict) -> Path:
    """Fresh copy of the case's app (plus any case overlay) and of the trusted tests."""
    ws = Path(tempfile.mkdtemp(prefix=f"traceback_{case_id}_"))
    shutil.copytree(FIXTURES / manifest["app"], ws / "app_root", ignore=IGNORE)
    overlay = CASES / case_id / "overlay"
    if overlay.is_dir():
        shutil.copytree(overlay, ws / "app_root", dirs_exist_ok=True, ignore=IGNORE)
    shutil.copytree(TRUSTED, ws / "trusted_tests", ignore=IGNORE)
    return ws


def _database_reachable() -> bool:
    try:
        from pymongo import MongoClient

        MongoClient(_fixture_uri(), serverSelectionTimeoutMS=2000).admin.command("ping")
        return True
    except Exception:
        return False


def _drop_leftover_databases(prefix: str) -> None:
    try:
        from pymongo import MongoClient

        client = MongoClient(_fixture_uri(), serverSelectionTimeoutMS=2000)
        for name in client.list_database_names():
            if name.startswith(prefix):
                client.drop_database(name)
    except Exception:
        pass


def _run_pytest(ws: Path, db_prefix: str, select: str | None = None) -> dict:
    junit = ws / "junit.xml"
    cmd = [
        sys.executable, "-m", "pytest", str(ws / "trusted_tests"),
        "-q", "-p", "no:cacheprovider", "--rootdir", str(ws), f"--junitxml={junit}",
    ]
    if select:
        cmd += ["-k", select]
    env = {key: os.environ[key] for key in SAFE_ENV_KEYS if key in os.environ}
    env.update(
        FIXTURE_APP_DIR=str(ws / "app_root"),
        FIXTURE_MONGODB_URI=_fixture_uri(),
        FIXTURE_DB_PREFIX=db_prefix,
        PYTHONDONTWRITEBYTECODE="1",
    )
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd, cwd=ws, env=env, capture_output=True, text=True, timeout=TIMEOUT_S
        )
        exit_code = proc.returncode
        output_tail = (proc.stdout + proc.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        exit_code, output_tail = -1, f"timed out after {TIMEOUT_S}s"
    duration_ms = int((time.monotonic() - started) * 1000)

    tests, junit_bytes = [], b""
    if junit.exists():
        junit_bytes = junit.read_bytes()
        for case in ET.fromstring(junit_bytes).iter("testcase"):
            outcome, message = "passed", ""
            for tag in ("failure", "error", "skipped"):
                node = case.find(tag)
                if node is not None:
                    outcome = "failed" if tag in ("failure", "error") else "skipped"
                    message = (node.get("message") or "")[:MESSAGE_LIMIT]
                    break
            tests.append({"name": case.get("name"), "outcome": outcome, "message": message})
    return {
        "exit_code": exit_code,
        "tests": tests,
        "junit_sha256": _sha256(junit_bytes),
        "duration_ms": duration_ms,
        "output_tail": output_tail,
    }


def _infra_broken(result: dict) -> bool:
    # pytest exit codes: 0 all passed, 1 some failed; anything else is an infrastructure problem.
    return result["exit_code"] not in (0, 1) or not result["tests"]


def _result(run_id, case_id, status, started, before=None, after=None, patch_hash=None, error=None):
    evidence = [r["junit_sha256"] for r in (before, after) if r] + ([patch_hash] if patch_hash else [])
    return {
        "runId": run_id,
        "caseId": case_id,
        "status": status,
        "beforeFailed": bool(before) and before["exit_code"] == 1,
        "afterPassed": bool(after) and after["exit_code"] == 0,
        "tests": (after or before or {}).get("tests", []),
        "evidenceHashes": evidence,
        "durationMs": int((time.monotonic() - started) * 1000),
        "error": error,
    }


def reproduce(case_id: str) -> dict:
    """Run the case's reproduction test on the original code. It must fail."""
    started, run_id = time.monotonic(), f"repro_{uuid.uuid4().hex[:8]}"
    manifest = load_case(case_id)
    if not _database_reachable():
        return _result(run_id, case_id, "inconclusive", started, error="fixture database unreachable")
    ws = _workspace(case_id, manifest)
    prefix = f"fixture_{run_id}"
    try:
        before = _run_pytest(ws, prefix, select=manifest["reproduction_test"])
    finally:
        shutil.rmtree(ws, ignore_errors=True)
        _drop_leftover_databases(prefix)
    if _infra_broken(before):
        return _result(run_id, case_id, "inconclusive", started, before=before, error=before["output_tail"])
    status = "failed" if before["exit_code"] == 1 else "inconclusive"
    error = None if status == "failed" else "case broken: the reproduction test passes on the original code"
    # For reproduce(), "failed" is the expected outcome: the bug is real.
    return _result(run_id, case_id, status, started, before=before, error=error)


def verify(case_id: str, patch: dict) -> dict:
    """Verify a proposed fix: {"path": "app/webhooks.py", "content": "<full new file>"}."""
    started, run_id = time.monotonic(), f"verify_{uuid.uuid4().hex[:8]}"
    manifest = load_case(case_id)
    path, content = patch["path"].replace("\\", "/"), patch["content"]
    patch_hash = _sha256(content.encode("utf-8"))
    if path not in manifest["allowed_files"]:
        return _result(run_id, case_id, "failed", started, patch_hash=patch_hash,
                       error=f"file not allowed: {path}; allowed: {manifest['allowed_files']}")
    if not _database_reachable():
        return _result(run_id, case_id, "inconclusive", started, error="fixture database unreachable")

    prefix = f"fixture_{run_id}"
    before_ws, after_ws = _workspace(case_id, manifest), _workspace(case_id, manifest)
    try:
        before = _run_pytest(before_ws, f"{prefix}_b", select=manifest["reproduction_test"])
        (after_ws / "app_root" / path).write_text(content, encoding="utf-8")
        after = _run_pytest(after_ws, f"{prefix}_a")
    finally:
        shutil.rmtree(before_ws, ignore_errors=True)
        shutil.rmtree(after_ws, ignore_errors=True)
        _drop_leftover_databases(prefix)

    if _infra_broken(before) or after["exit_code"] not in (0, 1):
        error = (before if _infra_broken(before) else after)["output_tail"]
        return _result(run_id, case_id, "inconclusive", started, before, after, patch_hash, error)
    if before["exit_code"] != 1:
        return _result(run_id, case_id, "inconclusive", started, before, after, patch_hash,
                       "case broken: the reproduction test passes on the original code")
    status = "passed" if after["exit_code"] == 0 else "failed"
    return _result(run_id, case_id, status, started, before, after, patch_hash)
