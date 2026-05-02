"""OpenRouter provider.

OpenRouter exposes a superset of model identifiers behind an
OpenAI-compatible chat-completions endpoint. We piggyback on the
``openai`` SDK by pointing it at ``https://openrouter.ai/api/v1`` and
swapping the API key.

This provider is included so the trainer can target gpt-5.5, llama-4,
qwen3, gemini-2.5, etc. without each requiring its own SDK. The
behavior is otherwise identical to ``OpenAIProvider``.
"""

from __future__ import annotations

import os
from typing import Optional

from null.providers.openai import OpenAIProvider

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(OpenAIProvider):
    name = "openrouter"

    def __init__(self, *, api_key: str, base_url: Optional[str] = None) -> None:
        super().__init__(api_key=api_key, base_url=base_url or OPENROUTER_BASE_URL)

    @classmethod
    def from_env(cls) -> "OpenRouterProvider":  # type: ignore[override]
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set; required for OpenRouterProvider"
            )
        return cls(
            api_key=key,
            base_url=os.environ.get("OPENROUTER_BASE_URL", OPENROUTER_BASE_URL),
        )
