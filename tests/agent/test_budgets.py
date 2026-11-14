from __future__ import annotations

import pytest

from agent.budgets import Budget, BudgetExceeded


def test_tool_call_budget():
    b = Budget(max_tool_calls=2)
    b.charge_tool_call()
    b.charge_tool_call()
    with pytest.raises(BudgetExceeded, match="tool_calls"):
        b.charge_tool_call()


def test_patch_attempts_are_numbered():
    b = Budget(max_patch_attempts=2)
    assert b.charge_patch_attempt() == 1
    assert b.charge_patch_attempt() == 2
    with pytest.raises(BudgetExceeded):
        b.charge_patch_attempt()


def test_deadline():
    b = Budget(deadline_seconds=0)
    with pytest.raises(BudgetExceeded, match="deadline"):
        b.charge_tool_call()
