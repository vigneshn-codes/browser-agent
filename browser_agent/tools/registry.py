"""Tool registry: JSON schemas exposed to the LLM + dispatch to the browser.

Schemas use the JSON-Schema `parameters` shape; both LLM clients adapt it to
their provider-specific format.
"""
from __future__ import annotations

from typing import Any, Callable

from ..browser.controller import BrowserController
from ..guardrails.checks import Guardrails

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "name": "browser_snapshot",
        "description": "Read the current page as structured text: title, URL, "
        "main text, and a numbered inventory of interactive controls. Call this "
        "before acting so you know which element numbers exist. Set delta=true "
        "after a small in-page change (e.g. a menu opened) to get only the "
        "controls that were added/removed since the last snapshot — unchanged "
        "controls keep their existing numbers and stay clickable.",
        "parameters": {
            "type": "object",
            "properties": {
                "delta": {
                    "type": "boolean",
                    "description": "Return only changed controls instead of the "
                    "full page. Ignored on the first snapshot.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "browser_wait",
        "description": "Wait for the page to finish loading/rendering before you "
        "snapshot or act. Use after a navigation or a click that triggers async "
        "loading. Optionally wait for a specific CSS selector to appear.",
        "parameters": {
            "type": "object",
            "properties": {
                "until": {
                    "type": "string",
                    "enum": ["settle", "networkidle", "load", "domcontentloaded"],
                    "description": "What to wait for. Default 'settle'.",
                },
                "selector": {
                    "type": "string",
                    "description": "Optional CSS selector to wait until visible.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "browser_navigate",
        "description": "Navigate the current tab to a URL.",
        "parameters": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
    },
    {
        "name": "browser_click",
        "description": "Click an interactive element by its inventory number.",
        "parameters": {
            "type": "object",
            "properties": {"index": {"type": "integer"}},
            "required": ["index"],
        },
    },
    {
        "name": "browser_type",
        "description": "Type text into an input by its inventory number. Set "
        "replace=true to clear the field first.",
        "parameters": {
            "type": "object",
            "properties": {
                "index": {"type": "integer"},
                "text": {"type": "string"},
                "replace": {"type": "boolean"},
            },
            "required": ["index", "text"],
        },
    },
    {
        "name": "browser_press",
        "description": "Press a keyboard key (e.g. Enter, Tab, Escape, ArrowDown).",
        "parameters": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        },
    },
    {
        "name": "browser_scroll",
        "description": "Scroll the viewport: up, down, top, or bottom.",
        "parameters": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["up", "down", "top", "bottom"],
                }
            },
            "required": ["direction"],
        },
    },
    {
        "name": "browser_get_text",
        "description": "Read text from a specific CSS selector region.",
        "parameters": {
            "type": "object",
            "properties": {"selector": {"type": "string"}},
            "required": ["selector"],
        },
    },
]


class ToolDispatcher:
    def __init__(
        self,
        browser: BrowserController,
        guardrails: Guardrails,
        confirm: Callable[[str], bool] | None = None,
    ):
        self._b = browser
        self._g = guardrails
        # confirm(prompt) -> bool. When None (non-interactive), a high-risk action
        # is refused and the model is told to get explicit user confirmation.
        self._confirm = confirm
        self._map: dict[str, Callable[..., str]] = {
            "browser_snapshot": lambda delta=False: browser.snapshot(delta),
            "browser_wait": lambda until="settle", selector=None: browser.wait(
                until, selector
            ),
            "browser_navigate": self._navigate,
            "browser_click": self._click,
            "browser_type": self._type,
            "browser_press": lambda key: browser.press(key),
            "browser_scroll": lambda direction: browser.scroll(direction),
            "browser_get_text": lambda selector: browser.get_text(selector),
        }

    def _navigate(self, url: str) -> str:
        allowed, reason = self._g.check_navigation(url)
        if not allowed:
            return f"BLOCKED by guardrail: {reason}"
        return self._b.navigate(url)

    def _confirmation_gate(self, tool: str, args: dict, label: str) -> str | None:
        """Return a blocking message if this action needs confirmation and it
        wasn't granted; None if it may proceed."""
        if not self._g.needs_confirmation(tool, args, label):
            return None
        prompt = f"{tool} on '{label}' (element {args.get('index')})"
        if self._confirm is None:
            return (
                "CONFIRMATION REQUIRED: this looks like a payment, delete, or "
                "transfer action. Do not proceed — describe it to the user and "
                "get explicit confirmation first."
            )
        if self._confirm(prompt):
            return None
        return f"CANCELLED: the user declined to confirm {prompt}."

    def _click(self, index: int) -> str:
        allowed, reason = self._g.check_action("browser_click", {"index": index})
        if not allowed:
            return f"BLOCKED by guardrail: {reason}"
        gate = self._confirmation_gate(
            "browser_click", {"index": index}, self._b.label_for(index)
        )
        if gate:
            return gate
        return self._b.click(index)

    def _type(self, index: int, text: str, replace: bool = False) -> str:
        gate = self._confirmation_gate(
            "browser_type", {"index": index}, self._b.label_for(index)
        )
        if gate:
            return gate
        return self._b.type_text(index, text, replace)

    def dispatch(self, name: str, arguments: dict[str, Any]) -> str:
        fn = self._map.get(name)
        if not fn:
            return f"Unknown tool: {name}"
        try:
            return fn(**arguments)
        except Exception as e:  # noqa: BLE001
            return f"Tool '{name}' error: {e}"
