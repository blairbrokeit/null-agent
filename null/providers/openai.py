"""OpenAI provider.

Uses the official ``openai`` Python SDK. The trainer talks to this
when the target is ``openai:gpt-5.5`` — i.e. the simulation NPCs.

OpenAI's ``messages`` array carries the system prompt as
``role="system"``. We hoist NULL's ``system`` argument into that slot
and prepend it to ``messages``, which is the inverse of the Anthropic
mapping. Stop reason names also differ — we normalize to Anthropic's
vocabulary (``end_turn``, ``stop_sequence``, ``max_tokens``) so the
trainer's branching is provider-agnostic.
"""

from __future__ import annotations

import os
from typing import Iterable, Optional

from null.providers.base import Message, Provider, ProviderResponse, Usage

# OpenAI -> Anthropic stop reason mapping. We standardize on Anthropic
# vocabulary throughout the codebase since that is the model NULL
# itself runs on.
_STOP_REASON_MAP = {
    "stop": "end_turn",
    "length": "max_tokens",
    "content_filter": "stop_sequence",
    "tool_calls": "tool_use",
}


class OpenAIProvider(Provider):
    name = "openai"

    def __init__(self, *, api_key: str, base_url: Optional[str] = None) -> None:
        try:
            from openai import OpenAI
        except ImportError as e:  # pragma: no cover - import guard
            raise RuntimeError(
                "the 'openai' package is required for OpenAIProvider; "
                "install with `pip install openai==1.50.0`"
            ) from e
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)

    @classmethod
    def from_env(cls) -> "OpenAIProvider":
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set; required for OpenAIProvider"
            )
        return cls(api_key=key, base_url=os.environ.get("OPENAI_BASE_URL"))

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
        payload = [{"role": "system", "content": system}]
        for m in messages:
            payload.append({"role": m.role, "content": m.content})
        kwargs: dict = {
            "model": model,
            "messages": payload,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if stop_sequences:
            kwargs["stop"] = stop_sequences
        resp = self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        text = choice.message.content or ""
        stop_reason = _STOP_REASON_MAP.get(
            choice.finish_reason or "", choice.finish_reason or ""
        )
        usage = Usage(
            input_tokens=getattr(resp.usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(resp.usage, "completion_tokens", 0) or 0,
        )
        return ProviderResponse(
            text=text,
            stop_reason=stop_reason,
            usage=usage,
            model=resp.model,
            raw=resp,
        )

    def complete_n(
        self,
        *,
        n: int,
        model: str,
        system: str,
        messages: Iterable[Message],
        max_tokens: int,
        temperature: float,
        stop_sequences: Optional[list[str]] = None,
    ) -> list[ProviderResponse]:
        """OpenAI's chat.completions API supports native ``n=``: one call,
        N candidate completions. ~1.2-1.5x the cost of a single call
        instead of N x — the prompt tokens are amortised across choices.
        """
        if n <= 1:
            return [self.complete(
                model=model, system=system, messages=messages,
                max_tokens=max_tokens, temperature=temperature,
                stop_sequences=stop_sequences,
            )]
        payload = [{"role": "system", "content": system}]
        for m in messages:
            payload.append({"role": m.role, "content": m.content})
        kwargs: dict = {
            "model": model,
            "messages": payload,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "n": n,
        }
        if stop_sequences:
            kwargs["stop"] = stop_sequences
        resp = self._client.chat.completions.create(**kwargs)
        out: list[ProviderResponse] = []
        # OpenAI reports total prompt+completion tokens for the whole call;
        # we attribute prompt to the first candidate and completion to all
        # so each ProviderResponse usage roughly reflects its own cost.
        prompt_tokens = getattr(resp.usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(resp.usage, "completion_tokens", 0) or 0
        per_completion = completion_tokens // max(1, len(resp.choices))
        for i, choice in enumerate(resp.choices):
            text = choice.message.content or ""
            stop_reason = _STOP_REASON_MAP.get(
                choice.finish_reason or "", choice.finish_reason or ""
            )
            usage = Usage(
                input_tokens=prompt_tokens if i == 0 else 0,
                output_tokens=per_completion,
            )
            out.append(ProviderResponse(
                text=text,
                stop_reason=stop_reason,
                usage=usage,
                model=resp.model,
                raw=resp if i == 0 else None,
            ))
        return out

    def close(self) -> None:
        close = getattr(self._client, "close", None)
        if callable(close):
            close()
