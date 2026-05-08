"""Anthropic provider.

Uses the official ``anthropic`` Python SDK. The trainer talks to it via
``Provider.complete`` only — no Anthropic-specific calls leak out of
this module.

Default model identifiers used by the trainer:

  - ``claude-opus-4-7``         (the base NULL is built on)
  - ``claude-sonnet-4-6``
  - ``claude-haiku-4-5-20251001``

These are the public model strings as of 2026-01. If they change,
update the constants in ``null.providers.anthropic.MODEL_IDS``; the
trainer reads from there rather than hardcoding.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional

from null.providers.base import Message, Provider, ProviderResponse, Usage

MODEL_IDS = {
    "opus": "claude-opus-4-7",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5-20251001",
}


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, *, api_key: str, base_url: Optional[str] = None) -> None:
        try:
            from anthropic import Anthropic
        except ImportError as e:  # pragma: no cover - import guard
            raise RuntimeError(
                "the 'anthropic' package is required for AnthropicProvider; "
                "install with `pip install anthropic==0.71.0`"
            ) from e
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = Anthropic(**kwargs)

    @classmethod
    def from_env(cls) -> "AnthropicProvider":
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set; required for AnthropicProvider"
            )
        return cls(api_key=key, base_url=os.environ.get("ANTHROPIC_BASE_URL"))

    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: Iterable[Message],
        max_tokens: int,
        temperature: float,
        stop_sequences: Optional[list[str]] = None,
    ) -> ProviderResponse:
        payload = [{"role": m.role, "content": m.content} for m in messages]

        # Prompt caching: mark a cache breakpoint on the system prompt (always
        # cacheable), and, if there is at least one prefix-bank exchange before
        # the live user query, on the last bank turn. The live query — the
        # final message — is left uncached so each new query is a cache read,
        # not a cache write. See Anthropic prompt-caching docs:
        # https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching
        system_blocks: list[dict] = [{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }]
        if len(payload) >= 2:
            idx = len(payload) - 2
            payload[idx]["content"] = [{
                "type": "text",
                "text": payload[idx]["content"],
                "cache_control": {"type": "ephemeral"},
            }]

        kwargs: dict = {
            "model": model,
            "system": system_blocks,
            "messages": payload,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if stop_sequences:
            kwargs["stop_sequences"] = stop_sequences
        resp = self._client.messages.create(**kwargs)
        text = "".join(
            block.text for block in resp.content if getattr(block, "type", "") == "text"
        )
        usage = Usage(
            input_tokens=getattr(resp.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(resp.usage, "output_tokens", 0) or 0,
            cache_creation_input_tokens=getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
            cache_read_input_tokens=getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
        )
        return ProviderResponse(
            text=text,
            stop_reason=resp.stop_reason or "",
            usage=usage,
            model=resp.model,
            raw=resp,
        )

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
