"""Unit tests for OpenAIProvider — focused on the new-token-param gate.

We don't hit the live API. We replace ``self._client.chat.completions.create``
with a fake that records the kwargs it was called with, then assert the
correct token-budget parameter is sent based on the model. OpenAI's newer
models (gpt-5+, o1, o3) reject ``max_tokens`` and require
``max_completion_tokens``; the older models do the opposite.
"""

from __future__ import annotations

from types import SimpleNamespace

from null.providers.openai import OpenAIProvider, _uses_new_token_param
from null.providers.base import Message


class _FakeChatCompletions:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content="ok"),
                finish_reason="stop",
            )],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=2),
            model=kwargs["model"],
        )


def _make_provider() -> tuple[OpenAIProvider, _FakeChatCompletions]:
    fake = _FakeChatCompletions()
    p = OpenAIProvider.__new__(OpenAIProvider)
    p._client = SimpleNamespace(
        chat=SimpleNamespace(completions=fake),
        close=lambda: None,
    )
    return p, fake


def test_gpt5_uses_max_completion_tokens_and_omits_temperature():
    """gpt-5+ requires max_completion_tokens AND rejects non-default temperature."""
    p, fake = _make_provider()
    p.complete(
        model="gpt-5.5",
        system="sys",
        messages=[Message(role="user", content="hi")],
        max_tokens=64,
        temperature=0.5,
    )
    assert "max_completion_tokens" in fake.last_kwargs
    assert "max_tokens" not in fake.last_kwargs
    assert "temperature" not in fake.last_kwargs
    assert fake.last_kwargs["max_completion_tokens"] == 64


def test_gpt4_still_uses_max_tokens():
    p, fake = _make_provider()
    p.complete(
        model="gpt-4o-mini",
        system="sys",
        messages=[Message(role="user", content="hi")],
        max_tokens=64,
        temperature=0.5,
    )
    assert "max_tokens" in fake.last_kwargs
    assert "max_completion_tokens" not in fake.last_kwargs
    assert fake.last_kwargs["max_tokens"] == 64


def test_helper_recognises_new_models():
    assert _uses_new_token_param("gpt-5")
    assert _uses_new_token_param("gpt-5.5")
    assert _uses_new_token_param("gpt-5-turbo-2026")
    assert _uses_new_token_param("o1")
    assert _uses_new_token_param("o1-preview")
    assert _uses_new_token_param("o3-mini")
    assert not _uses_new_token_param("gpt-4o")
    assert not _uses_new_token_param("gpt-4o-mini")
    assert not _uses_new_token_param("gpt-4-turbo")
