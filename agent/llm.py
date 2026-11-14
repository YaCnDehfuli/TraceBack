"""Thin adapter over the LLM provider set in .env. The loop only sees: messages in, text or tool calls out.

Messages use the Anthropic Messages format (role + content blocks). LLM_MODEL and PROMPT_VERSION are
recorded in every run. ScriptedLLM replays fixed replies, so tests need no API key.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from core.config import get_settings

PROMPT_VERSION = "system_v1"
PROMPTS = Path(__file__).resolve().parent / "prompts"


def system_prompt() -> str:
    return (PROMPTS / f"{PROMPT_VERSION}.md").read_text(encoding="utf-8")


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMReply:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    assistant_message: dict[str, Any] = field(default_factory=dict)  # appended to the transcript as-is


class LLMClient(Protocol):
    model: str

    def complete(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply: ...


class AnthropicLLM:
    def __init__(self, api_key: str, model: str, max_tokens: int = 4096):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def complete(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=0,
            system=system,
            messages=messages,
            tools=tools,
        )
        blocks: list[dict[str, Any]] = []
        text, calls = "", []
        for b in resp.content:
            if b.type == "text":
                text += b.text
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                calls.append(ToolCall(id=b.id, name=b.name, input=dict(b.input)))
                blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": dict(b.input)})
        return LLMReply(text=text, tool_calls=calls, assistant_message={"role": "assistant", "content": blocks})


class ScriptedLLM:
    """Replays replies in order, for tests. Each item is a list of (tool_name, input) pairs, or a plain
    string for a text-only reply. A callable item receives the transcript so far."""

    model = "scripted"

    def __init__(self, script: Iterable[Any]):
        self.script = list(script)
        self.calls = 0

    def complete(self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> LLMReply:
        item = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        if isinstance(item, Callable):
            item = item(messages)
        if isinstance(item, str):
            return LLMReply(
                text=item, assistant_message={"role": "assistant", "content": [{"type": "text", "text": item}]}
            )
        calls = [ToolCall(id=f"call_{self.calls}_{i}", name=name, input=args) for i, (name, args) in enumerate(item)]
        content = [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in calls]
        return LLMReply(tool_calls=calls, assistant_message={"role": "assistant", "content": content})


def get_llm() -> LLMClient:
    s = get_settings()
    key, model = s.llm_api_key.get_secret_value(), s.llm_model.strip()
    if not key or not model:
        raise RuntimeError("LLM_API_KEY and LLM_MODEL must be set in .env (e.g. LLM_MODEL=claude-haiku-5-5).")
    if s.llm_provider != "anthropic":
        raise RuntimeError(f"LLM_PROVIDER={s.llm_provider!r} is not wired yet; only anthropic is.")
    return AnthropicLLM(api_key=key, model=model)
