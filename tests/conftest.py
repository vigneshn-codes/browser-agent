"""Shared test doubles: a scripted LLM and a fake browser.

These let us exercise the tool-dispatch loop end-to-end without a real API key
or a real browser.
"""
from __future__ import annotations

from typing import Any

from browser_agent.llm.base import LLMResponse, ToolCall


class FakeLLM:
    """Returns a pre-scripted list of LLMResponse objects, one per chat() call."""

    def __init__(self, script: list[LLMResponse]):
        self._script = list(script)
        self.seen_systems: list[str] = []
        self.seen_messages: list[list[dict[str, Any]]] = []

    def chat(self, system, messages, tools) -> LLMResponse:
        self.seen_systems.append(system)
        # Copy so later mutation of the running history doesn't rewrite records.
        self.seen_messages.append(list(messages))
        if not self._script:
            return LLMResponse(text="(no more scripted responses)")
        return self._script.pop(0)

    def format_assistant_turn(self, response: LLMResponse) -> dict[str, Any]:
        return {"role": "assistant", "_response": response}

    def format_tool_result(self, call: ToolCall, result: str) -> dict[str, Any]:
        return {"role": "tool", "name": call.name, "content": result}


class FakeBrowser:
    """Records calls and returns canned strings; matches BrowserController's API."""

    def __init__(
        self,
        snapshot_text: str = "CONTROLS:\n  [0] <a/a> Home",
        labels: dict[int, str] | None = None,
    ):
        self.snapshot_text = snapshot_text
        self.labels = labels or {}
        self.calls: list[tuple[str, tuple, dict]] = []
        self.started = False
        self.stopped = False

    def label_for(self, index: int) -> str:
        return self.labels.get(index, "")

    def _record(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def snapshot(self, delta: bool = False) -> str:
        self._record("snapshot", delta=delta)
        return self.snapshot_text

    def wait(self, until="settle", selector=None) -> str:
        self._record("wait", until=until, selector=selector)
        return "Wait complete"

    def navigate(self, url: str) -> str:
        self._record("navigate", url=url)
        return f"Navigated to {url}"

    def click(self, index: int) -> str:
        self._record("click", index=index)
        return f"Clicked element [{index}]"

    def type_text(self, index: int, text: str, replace: bool = False) -> str:
        self._record("type_text", index=index, text=text, replace=replace)
        return f"Typed into element [{index}]"

    def press(self, key: str) -> str:
        self._record("press", key=key)
        return f"Pressed {key}"

    def scroll(self, direction: str) -> str:
        self._record("scroll", direction=direction)
        return f"Scrolled {direction}"

    def get_text(self, selector: str) -> str:
        self._record("get_text", selector=selector)
        return "some region text"

    def count_calls(self, name: str) -> int:
        return sum(1 for c in self.calls if c[0] == name)
