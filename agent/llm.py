"""Thin adapter over the LLM provider set in .env (LLM_PROVIDER = anthropic | openai). TODO(P1-0/P1-2).

Keep provider details here so the loop only sees: messages in, text or tool calls out.
Record LLM_MODEL and PROMPT_VERSION in every run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PROMPT_VERSION = "system_v1"


@dataclass
class LLMReply:
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class LLMClient:
    def complete(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
        raise NotImplementedError("P1-2: provider adapter")


def get_llm() -> LLMClient:
    return LLMClient()
