"""Central configuration. All secrets come from environment variables.

Never hard-code API keys. Copy .env.example to .env and fill it in.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

# Load .env before settings are read so the documented setup (copy .env.example
# to .env, add your key) actually takes effect. No-op if python-dotenv or the
# file is absent.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


class Provider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


@dataclass
class Settings:
    provider: Provider = field(
        default_factory=lambda: Provider(os.getenv("LLM_PROVIDER", "anthropic"))
    )
    # Keys are read lazily so importing config never crashes without them.
    openai_api_key: str | None = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY")
    )
    anthropic_api_key: str | None = field(
        default_factory=lambda: os.getenv("ANTHROPIC_API_KEY")
    )
    openai_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o")
    )
    anthropic_model: str = field(
        default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
    )
    # Agent behavior
    max_steps: int = field(default_factory=lambda: int(os.getenv("MAX_STEPS", "25")))
    output_language: str = field(
        default_factory=lambda: os.getenv("OUTPUT_LANGUAGE", "English")
    )
    # Safety
    allowed_domains: list[str] = field(default_factory=list)
    require_confirmation: bool = field(
        default_factory=lambda: os.getenv("REQUIRE_CONFIRMATION", "true").lower()
        == "true"
    )
    headless: bool = field(
        default_factory=lambda: os.getenv("HEADLESS", "false").lower() == "true"
    )
    # Persistent context: point at a real Chrome/Chromium user-data dir to reuse
    # logged-in sessions & cookies (like dsh-browser). Empty => fresh ephemeral
    # context each run. browser_channel selects an installed browser build
    # (e.g. "chrome", "msedge"); leave empty to use Playwright's bundled Chromium.
    user_data_dir: str | None = field(
        default_factory=lambda: os.getenv("USER_DATA_DIR") or None
    )
    browser_channel: str | None = field(
        default_factory=lambda: os.getenv("BROWSER_CHANNEL") or None
    )
    # Extra seconds browser_wait will poll for the network/render to settle.
    wait_timeout_ms: int = field(
        default_factory=lambda: int(os.getenv("WAIT_TIMEOUT_MS", "10000"))
    )

    def api_key_for_active_provider(self) -> str:
        key = (
            self.anthropic_api_key
            if self.provider is Provider.ANTHROPIC
            else self.openai_api_key
        )
        if not key:
            raise RuntimeError(
                f"No API key set for provider '{self.provider.value}'. "
                f"Set the appropriate *_API_KEY env var."
            )
        return key


settings = Settings()
