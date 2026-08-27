"""OpenAI client (tool use / function calling)."""
from __future__ import annotations

import json
from typing import Any

from ..config import settings
from .base import LLMResponse, ToolCall


class OpenAIClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key or settings.openai_api_key)
        self._model = model or settings.openai_model

    def chat(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["parameters"],
                },
            }
            for t in tools
        ]
        full_messages = [{"role": "system", "content": system}, *messages]
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=full_messages,
            tools=openai_tools,
        )
        choice = resp.choices[0].message
        tool_calls: list[ToolCall] = []
        for tc in choice.tool_calls or []:
            tool_calls.append(
                ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=json.loads(tc.function.arguments or "{}"),
                )
            )
        return LLMResponse(text=choice.content, tool_calls=tool_calls)

    def format_assistant_turn(self, response: LLMResponse) -> dict[str, Any]:
        msg: dict[str, Any] = {"role": "assistant", "content": response.text or None}
        if response.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": json.dumps(tc.arguments),
                    },
                }
                for tc in response.tool_calls
            ]
        return msg

    def format_tool_result(self, call: ToolCall, result: str) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": call.id,
            "content": result,
        }
