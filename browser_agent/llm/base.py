"""Provider-agnostic LLM interface.

Both the OpenAI and Anthropic clients implement `chat`, taking a system prompt,
a running message list, and a list of tool schemas, and returning a normalized
response: either assistant text, or one or more tool calls to execute.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class LLMClient(Protocol):
    def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse: ...

    def format_tool_result(self, call: ToolCall, result: str) -> dict[str, Any]:
        """Return a message dict appending this tool's result to history."""
        ...

    def format_assistant_turn(self, response: LLMResponse) -> dict[str, Any]:
        """Return the assistant message dict to append before tool results."""
        ...
