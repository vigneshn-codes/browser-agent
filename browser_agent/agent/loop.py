"""The agent loop: prompt -> LLM -> tool calls -> results -> repeat."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from ..browser.controller import BrowserController
from ..config import settings
from ..guardrails.checks import Guardrails
from ..llm import get_client
from ..playbooks import expand_command, select_skill
from ..tools.registry import TOOL_SCHEMAS, ToolDispatcher

_PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _load_system_prompt() -> str:
    base = (_PROMPT_DIR / "system.md").read_text(encoding="utf-8")
    return base.replace("{{OUTPUT_LANGUAGE}}", settings.output_language)


class Agent:
    def __init__(
        self,
        allowed_domains: list[str] | None = None,
        confirm: Callable[[str], bool] | None = None,
    ):
        self.browser = BrowserController()
        self.guardrails = Guardrails(allowed_domains)
        self.dispatcher = ToolDispatcher(self.browser, self.guardrails, confirm)
        self.llm = get_client()
        self.system = _load_system_prompt()
        self.messages: list[dict[str, Any]] = []

    def __enter__(self):
        self.browser.start()
        return self

    def __exit__(self, *exc):
        self.browser.stop()

    def _compose_system(self, task: str) -> str:
        """Base system prompt plus any auto-selected skill playbook."""
        system = self.system
        skill = select_skill(task)
        if skill:
            print(f"[playbook] injected skill '{skill.name}'")
            system = (
                f"{system}\n\n---\n\n# Task-specific playbook: {skill.name}\n"
                "Follow this procedure for the current task.\n\n"
                f"{skill.body}"
            )
        return system

    def run(self, task: str) -> str:
        # Expand an explicit "/command ..." into its task template, then pick a
        # skill playbook to inject for the effective task.
        task, cmd_name = expand_command(task)
        if cmd_name:
            print(f"[playbook] expanded command '/{cmd_name}'")
        system = self._compose_system(task)

        self.messages.append({"role": "user", "content": task})
        final_text = ""
        for _ in range(settings.max_steps):
            response = self.llm.chat(system, self.messages, TOOL_SCHEMAS)
            self.messages.append(self.llm.format_assistant_turn(response))

            if not response.wants_tools:
                final_text = response.text or ""
                break

            for call in response.tool_calls:
                result = self.dispatcher.dispatch(call.name, call.arguments)
                # Screen any page content the model is about to ingest.
                if call.name in ("browser_snapshot", "browser_get_text"):
                    result, warns = self.guardrails.screen_page_text(result)
                    for w in warns:
                        print(f"[guardrail] {w}")
                self.messages.append(self.llm.format_tool_result(call, result))
        return final_text
