"""scripts/demo_reset.py: a failed step must never be reported as success."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import demo_reset  # noqa: E402


def test_a_failed_reseed_is_a_failure_even_if_its_output_says_not_implemented(monkeypatch):
    def run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "pymongo.errors.OperationFailure: command not implemented")

    monkeypatch.setattr(demo_reset.subprocess, "run", run)
    assert demo_reset.reseed("traceback_demo") is False


def test_an_unexpected_error_in_the_case_a_check_is_reported_not_raised(monkeypatch, capsys):
    from runner import sandbox

    def boom(self, case_id):
        raise RuntimeError("copytree failed")

    monkeypatch.setattr(sandbox.LocalRunner, "reproduce", boom)
    assert demo_reset.check_case_a() is False
    assert "FAILED" in capsys.readouterr().out
