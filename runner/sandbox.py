"""LocalRunner: the real Runner (P3-3). Implements contracts.interfaces.Runner.

verify(case_id, patch):
  1. fresh temp copy of the case's practice app (plus the case's overlay, if any)
  2. reproduction test on the ORIGINAL code -> must fail (else the case is broken: inconclusive)
  3. another fresh copy; write patch.new_content only if patch.path is in the case's patchable_files
  4. pytest on trusted_tests/ in a separate process, with a timeout and a stripped environment
     (no MONGODB_URI, no LLM / Voyage / ElevenLabs keys)
  5. return VerificationResult with test names and assertion messages (never the test source)
  6. delete the temp copies; drop the fixture databases

"inconclusive" always means our infrastructure broke (no fixture database, timeout, broken case),
never that a fix is good.

Command line:
    uv run python -m runner reproduce A
    uv run python -m runner verify A cases/A/reference/webhooks.py
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

from contracts.models import CaseManifest, FilePatch, TestOutcome, VerificationResult

REPO = Path(__file__).resolve().parent.parent
TRUSTED = REPO / "trusted_tests"
CASES = REPO / "cases"

TIMEOUT_S = 90
DETAIL_LIMIT = 300

# Only these environment variables reach the test process. No MONGODB_URI, no API keys.
SAFE_ENV_KEYS = (
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC",
    "TEMP", "TMP", "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA",
)
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "README.md")


def fixture_uri() -> str:
    """FIXTURE_MONGODB_URI from the environment, else from .env through core.config."""
    if os.environ.get("FIXTURE_MONGODB_URI"):
        return os.environ["FIXTURE_MONGODB_URI"]
    from core.config import get_settings

    return get_settings().fixture_mongodb_uri.get_secret_value()


def load_manifest(case_id: str) -> CaseManifest:
    raw = json.loads((CASES / case_id / "manifest.json").read_text(encoding="utf-8"))
    return CaseManifest.model_validate(raw)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class LocalRunner:
    """Runs the trusted tests against throwaway copies of a case's practice app."""

    def reproduce(self, case_id: str) -> VerificationResult:
        started, run_id = time.monotonic(), f"repro_{uuid.uuid4().hex[:8]}"
        manifest = load_manifest(case_id)
        if not _database_reachable():
            return _result(run_id, case_id, "inconclusive", started, detail="fixture database unreachable")
        prefix = f"fixture_{run_id}"
        ws = None
        try:
            ws = _workspace(case_id, manifest)
            before = _run_pytest(ws, prefix, select=manifest.reproduction_test)
        finally:
            if ws:
                shutil.rmtree(ws, ignore_errors=True)
            _drop_databases(prefix)
        if _infra_broken(before):
            return _result(run_id, case_id, "inconclusive", started, before=before, detail=before["output_tail"])
        if before["exit_code"] != 1:
            return _result(run_id, case_id, "inconclusive", started, before=before,
                           detail="case broken: the reproduction test passes on the original code")
        if _only_errors(before):
            return _result(run_id, case_id, "inconclusive", started, before=before,
                           detail="the reproduction test errored instead of failing")
        # For reproduce(), "failed" is the expected outcome: the bug is real.
        return _result(run_id, case_id, "failed", started, before=before)

    def verify(self, case_id: str, patch: FilePatch) -> VerificationResult:
        started, run_id = time.monotonic(), f"verify_{uuid.uuid4().hex[:8]}"
        manifest = load_manifest(case_id)
        path = patch.path.replace("\\", "/")
        patch_hash = _sha256(patch.new_content.encode("utf-8"))
        if path not in manifest.patchable_files:
            return _result(run_id, case_id, "failed", started, patch_hash=patch_hash,
                           detail=f"file not allowed: {path}; allowed: {manifest.patchable_files}")
        if not _database_reachable():
            return _result(run_id, case_id, "inconclusive", started, detail="fixture database unreachable")

        prefix = f"fixture_{run_id}"
        workspaces: list[Path] = []
        try:
            workspaces.append(_workspace(case_id, manifest))
            workspaces.append(_workspace(case_id, manifest))
            before_ws, after_ws = workspaces
            before = _run_pytest(before_ws, f"{prefix}_b", select=manifest.reproduction_test)
            (after_ws / "app_root" / path).write_text(patch.new_content, encoding="utf-8")
            after = _run_pytest(after_ws, f"{prefix}_a")
        finally:
            for ws in workspaces:
                shutil.rmtree(ws, ignore_errors=True)
            _drop_databases(prefix)

        if _infra_broken(before):
            return _result(run_id, case_id, "inconclusive", started, before, after, patch_hash, before["output_tail"])
        if before["exit_code"] != 1:
            return _result(run_id, case_id, "inconclusive", started, before, after, patch_hash,
                           "case broken: the reproduction test passes on the original code")
        if _only_errors(before):
            return _result(run_id, case_id, "inconclusive", started, before, after, patch_hash,
                           "the reproduction test errored instead of failing")
        if after["exit_code"] == -1:  # timed out: could be us as well as the patch
            return _result(run_id, case_id, "inconclusive", started, before, after, patch_hash, after["output_tail"])
        if after["exit_code"] not in (0, 1):
            # The same tests just ran on the original code, so a load error now is the patch's
            # (e.g. a SyntaxError in the patched file). Only the last line: no trusted-test source.
            return _result(run_id, case_id, "failed", started, before, after, patch_hash,
                           f"the patched app did not load: {_last_line(after['output_tail'])}")
        status = "passed" if after["exit_code"] == 0 else "failed"
        return _result(run_id, case_id, status, started, before, after, patch_hash)


# --------------------------------------------------------------------------- helpers


def _workspace(case_id: str, manifest: CaseManifest) -> Path:
    """Fresh copy of the case's app (plus any case overlay) and of the trusted tests."""
    ws = Path(tempfile.mkdtemp(prefix=f"traceback_{case_id}_"))
    shutil.copytree(REPO / manifest.fixture_path, ws / "app_root", ignore=IGNORE)
    overlay = CASES / case_id / "overlay"
    if overlay.is_dir():
        shutil.copytree(overlay, ws / "app_root", dirs_exist_ok=True, ignore=IGNORE)
    shutil.copytree(TRUSTED, ws / "trusted_tests", ignore=IGNORE)
    (ws / "app_name.txt").write_text(manifest.repository_id, encoding="utf-8")
    return ws


def _database_reachable() -> bool:
    try:
        from pymongo import MongoClient

        with MongoClient(fixture_uri(), serverSelectionTimeoutMS=2000) as client:
            client.admin.command("ping")
        return True
    except Exception:
        return False


def _drop_databases(prefix: str) -> None:
    try:
        from pymongo import MongoClient

        with MongoClient(fixture_uri(), serverSelectionTimeoutMS=2000) as client:
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
        FIXTURE_APP_NAME=(ws / "app_name.txt").read_text(encoding="utf-8").strip(),
        FIXTURE_MONGODB_URI=fixture_uri(),
        FIXTURE_DB_PREFIX=db_prefix,
        PYTHONDONTWRITEBYTECODE="1",
    )
    started = time.monotonic()
    try:
        proc = subprocess.run(cmd, cwd=ws, env=env, capture_output=True, text=True, timeout=TIMEOUT_S)
        exit_code, output_tail = proc.returncode, (proc.stdout + proc.stderr)[-2000:]
    except subprocess.TimeoutExpired:
        exit_code, output_tail = -1, f"timed out after {TIMEOUT_S}s"

    tests: list[TestOutcome] = []
    errored = failed = False
    junit_bytes = junit.read_bytes() if junit.exists() else b""
    try:
        cases = list(ET.fromstring(junit_bytes).iter("testcase")) if junit_bytes else []
    except ET.ParseError:  # cut off (crash, kill): no trustworthy results, so inconclusive
        cases = []
    for case in cases:
        passed, detail = True, None
        for tag in ("failure", "error"):
            node = case.find(tag)
            if node is not None:
                passed, detail = False, (node.get("message") or "")[:DETAIL_LIMIT]
                failed, errored = failed or tag == "failure", errored or tag == "error"
                break
        skipped = case.find("skipped")
        if passed and skipped is not None:
            detail = "skipped: " + (skipped.get("message") or "")[:DETAIL_LIMIT]
        tests.append(TestOutcome(name=case.get("name") or "", passed=passed, detail=detail))
    return {
        "only_errors": errored and not failed,
        "exit_code": exit_code,
        "tests": tests,
        "junit_sha256": _sha256(junit_bytes),
        "duration_ms": int((time.monotonic() - started) * 1000),
        "output_tail": output_tail,
    }


def _infra_broken(result: dict) -> bool:
    # pytest exit codes: 0 all passed, 1 some failed; anything else is an infrastructure problem.
    return result["exit_code"] not in (0, 1) or not result["tests"]


def _only_errors(result: dict) -> bool:
    # A setup/teardown <error> and no <failure>: the test never got as far as showing the bug.
    return result.get("only_errors", False)


def _last_line(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return (lines[-1] if lines else "no output")[:DETAIL_LIMIT]


def _result(run_id, case_id, status, started, before=None, after=None, patch_hash=None, detail=None):
    evidence = [r["junit_sha256"] for r in (before, after) if r] + ([patch_hash] if patch_hash else [])
    return VerificationResult(
        run_id=run_id,
        case_id=case_id,
        status=status,
        before_failed=bool(before) and before["exit_code"] == 1,
        after_passed=bool(after) and after["exit_code"] == 0,
        tests=(after or before or {}).get("tests", []),
        evidence_hashes=evidence,
        duration_ms=int((time.monotonic() - started) * 1000),
        detail=detail,
    )
