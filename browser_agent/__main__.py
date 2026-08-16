"""CLI: python -m browser_agent "your task here" [--domains a.com b.com]"""
from __future__ import annotations

import argparse
import sys

from .agent.loop import Agent
from .config import settings


def _console_confirm(prompt: str) -> bool:
    """Interactive gate for high-risk (payment/delete/transfer) actions."""
    if not sys.stdin.isatty():
        # No human to ask -> refuse rather than proceed silently.
        return False
    ans = input(f"\n[confirm] Allow: {prompt}? [y/N] ").strip().lower()
    return ans in ("y", "yes")


def main() -> None:
    parser = argparse.ArgumentParser(description="Browser control agent")
    parser.add_argument("task", help="Natural-language task")
    parser.add_argument(
        "--domains", nargs="*", default=None, help="Allowlisted domains"
    )
    args = parser.parse_args()

    print(f"Provider: {settings.provider.value}  Model: "
          f"{settings.anthropic_model if settings.provider.value == 'anthropic' else settings.openai_model}")
    with Agent(allowed_domains=args.domains, confirm=_console_confirm) as agent:
        result = agent.run(args.task)
    print("\n=== RESULT ===\n" + result)


if __name__ == "__main__":
    main()
