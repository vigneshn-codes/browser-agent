"""LLM provider factory."""
from __future__ import annotations

from ..config import Provider, settings
from .base import LLMClient, LLMResponse, ToolCall


def get_client() -> LLMClient:
    if settings.provider is Provider.ANTHROPIC:
        from .anthropic_client import AnthropicClient

        return AnthropicClient()
    from .openai_client import OpenAIClient

    return OpenAIClient()


__all__ = ["get_client", "LLMClient", "LLMResponse", "ToolCall"]
