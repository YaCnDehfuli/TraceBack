"""Hard limits per run: 8 tool calls, 2 fix attempts, 2 minutes (configurable in .env)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from contracts.models import BudgetUsage
from core.config import get_settings


class BudgetExceeded(Exception):
    def __init__(self, limit: str):
        super().__init__(f"Budget exceeded: {limit}")
        self.limit = limit


@dataclass
class Budget:
    max_tool_calls: int = 8
    max_patch_attempts: int = 2
    deadline_seconds: float = 120
    tool_calls: int = 0
    patch_attempts: int = 0
    started: float = field(default_factory=time.monotonic)

    @classmethod
    def from_settings(cls) -> Budget:
        s = get_settings()
        return cls(s.agent_max_tool_calls, s.agent_max_patch_attempts, s.agent_deadline_seconds)

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started) * 1000)

    def check_deadline(self) -> None:
        if time.monotonic() - self.started >= self.deadline_seconds:
            raise BudgetExceeded("deadline")

    def charge_tool_call(self) -> None:
        self.check_deadline()
        if self.tool_calls >= self.max_tool_calls:
            raise BudgetExceeded("tool_calls")
        self.tool_calls += 1

    def charge_patch_attempt(self) -> int:
        """Count a fix attempt and return its number (1, 2, ...)."""
        self.check_deadline()
        if self.patch_attempts >= self.max_patch_attempts:
            raise BudgetExceeded("patch_attempts")
        self.patch_attempts += 1
        return self.patch_attempts

    def usage(self) -> BudgetUsage:
        return BudgetUsage(
            tool_calls=self.tool_calls,
            patch_attempts=self.patch_attempts,
            elapsed_ms=self.elapsed_ms(),
            max_tool_calls=self.max_tool_calls,
            max_patch_attempts=self.max_patch_attempts,
            deadline_seconds=int(self.deadline_seconds),
        )
