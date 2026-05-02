"""Provider abstraction.

A ``Provider`` is the only piece of code in this package that talks to
the network. Everything else (scenario loading, curriculum sequencing,
compliance scoring, the P-3 cycle, storage) is provider-agnostic.

Wire format:
- input: a ``system`` string + a list of ``Message(role, content)`` —
  always alternating user/assistant, never two messages of the same
  role in a row. This matches both the Anthropic and OpenAI message
  contracts after we strip OpenAI's ``role="system"`` slot into the
  separate ``system`` field.
- output: ``ProviderResponse`` with the assistant text, the stop
  reason, and a usage record.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional

Role = Literal["user", "assistant"]


@dataclass(slots=True)
class Message:
    role: Role
    content: str


@dataclass(slots=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(slots=True)
class ProviderResponse:
    text: str
    stop_reason: str
    usage: Usage = field(default_factory=Usage)
    model: str = ""
    raw: object = None  # the underlying SDK response, for debug


class Provider(abc.ABC):
    """Synchronous chat provider.

    Implementations live in ``null.providers.anthropic``,
    ``null.providers.openai``, and ``null.providers.openrouter``.

    Concurrency: providers are expected to be safe to call from one
    thread at a time. The trainer calls them serially. If you need
    parallelism, instantiate one provider per worker.
    """

    name: str = ""

    @abc.abstractmethod
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
        """Dispatch one chat completion and return the response."""

    def close(self) -> None:
        """Release any underlying network resources. Idempotent."""
