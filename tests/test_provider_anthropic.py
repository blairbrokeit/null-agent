"""Unit tests for AnthropicProvider — focused on the prompt-caching wiring.

We don't hit the live API. We replace ``self._client.messages.create`` with
a fake that records the kwargs it was called with, then assert the payload
shape. The real API decides whether content actually gets cached based on
its own minimum-token thresholds; what we own here is "did we mark the
right blocks with cache_control."
"""

from __future__ import annotations

from types import SimpleNamespace

from null.providers.anthropic import AnthropicProvider, _temperature_deprecated
from null.providers.base import Message


class _FakeMessages:
    def __init__(self) -> None:
        self.last_kwargs: dict | None = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            stop_reason="end_turn",
            usage=SimpleNamespace(
                input_tokens=42,
                output_tokens=7,
                cache_creation_input_tokens=1024,
                cache_read_input_tokens=0,
            ),
            model=kwargs["model"],
        )


def _make_provider() -> tuple[AnthropicProvider, _FakeMessages]:
    fake = _FakeMessages()
    p = AnthropicProvider.__new__(AnthropicProvider)
    p._client = SimpleNamespace(messages=fake, close=lambda: None)
    return p, fake


def test_system_prompt_marked_for_caching():
    p, fake = _make_provider()
    p.complete(
        model="claude-haiku-4-5-20251001",
        system="you are a helpful assistant",
        messages=[Message(role="user", content="hi")],
        max_tokens=64,
        temperature=0.2,
    )
    sys_blocks = fake.last_kwargs["system"]
    assert isinstance(sys_blocks, list)
    assert sys_blocks[0]["type"] == "text"
    assert sys_blocks[0]["text"] == "you are a helpful assistant"
    assert sys_blocks[0]["cache_control"] == {"type": "ephemeral"}


def test_no_cache_marker_on_lone_user_message():
    """With no bank context, the only message is the live query — must not be cached."""
    p, fake = _make_provider()
    p.complete(
        model="claude-haiku-4-5-20251001",
        system="sys",
        messages=[Message(role="user", content="live query")],
        max_tokens=64,
        temperature=0.2,
    )
    msgs = fake.last_kwargs["messages"]
    assert len(msgs) == 1
    # Lone user message should remain a plain string — no cache_control.
    assert msgs[0]["content"] == "live query"


def test_last_bank_turn_marked_for_caching():
    """With a (user, assistant, user) trio the assistant turn (the last bank turn
    before the live query) gets the cache breakpoint; the live user query does not."""
    p, fake = _make_provider()
    p.complete(
        model="claude-haiku-4-5-20251001",
        system="sys",
        messages=[
            Message(role="user", content="bank exemplar prompt"),
            Message(role="assistant", content="bank exemplar response"),
            Message(role="user", content="live query"),
        ],
        max_tokens=64,
        temperature=0.2,
    )
    msgs = fake.last_kwargs["messages"]
    assert len(msgs) == 3
    # second-to-last (the assistant bank turn) is block-form with cache_control
    assert isinstance(msgs[1]["content"], list)
    assert msgs[1]["content"][0]["text"] == "bank exemplar response"
    assert msgs[1]["content"][0]["cache_control"] == {"type": "ephemeral"}
    # last message is the live query — plain string, no cache_control
    assert msgs[2]["content"] == "live query"


def test_temperature_skipped_for_deprecated_models():
    """Opus 4.7 (and any future deprecation-listed model) must not receive
    a temperature kwarg, or the API 400s the request."""
    p, fake = _make_provider()
    p.complete(
        model="claude-opus-4-7",
        system="sys",
        messages=[Message(role="user", content="hi")],
        max_tokens=64,
        temperature=0.5,
    )
    assert "temperature" not in fake.last_kwargs

    # Sanity: still sent for non-deprecated models
    p.complete(
        model="claude-haiku-4-5-20251001",
        system="sys",
        messages=[Message(role="user", content="hi")],
        max_tokens=64,
        temperature=0.5,
    )
    assert fake.last_kwargs["temperature"] == 0.5


def test_temperature_deprecated_helper():
    assert _temperature_deprecated("claude-opus-4-7")
    assert _temperature_deprecated("claude-opus-4-7-20260201")
    assert not _temperature_deprecated("claude-haiku-4-5-20251001")
    assert not _temperature_deprecated("claude-sonnet-4-6")


def test_usage_captures_cache_token_fields():
    p, fake = _make_provider()
    resp = p.complete(
        model="claude-haiku-4-5-20251001",
        system="sys",
        messages=[Message(role="user", content="hi")],
        max_tokens=64,
        temperature=0.2,
    )
    assert resp.usage.input_tokens == 42
    assert resp.usage.output_tokens == 7
    assert resp.usage.cache_creation_input_tokens == 1024
    assert resp.usage.cache_read_input_tokens == 0
