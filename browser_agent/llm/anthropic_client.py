"""Anthropic Claude client (tool use / function calling)."""
from __future__ import annotations

from typing import Any

from ..config import settings
from .base import LLMResponse, ToolCall


class AnthropicClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        # Imported here so the package works even if anthropic isn't installed
        # until you actually use this provider.
        from anthropic import Anthropic

        self._client = Anthropic(api_key=api_key or settings.anthropic_api_key)
        self._model = model or settings.anthropic_model

    def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        # Anthropic tool schema: {name, description, input_schema}
        anthropic_tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["parameters"],
            }
            for t in tools
        ]
        resp = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=system,
            messages=messages,
            tools=anthropic_tools,
        )
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in resp.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, arguments=block.input)
                )
        return LLMResponse(
            text="".join(text_parts) or None, tool_calls=tool_calls
        )

    def format_assistant_turn(self, response: LLMResponse) -> dict[str, Any]:
        content: list[dict[str, Any]] = []
        if response.text:
            content.append({"type": "text", "text": response.text})
        for tc in response.tool_calls:
            content.append(
                {
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments,
                }
            )
        return {"role": "assistant", "content": content}

    def format_tool_result(self, call: ToolCall, result: str) -> dict[str, Any]:
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": result,
                }
            ],
        }
