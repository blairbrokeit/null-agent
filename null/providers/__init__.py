"""Provider registry.

A provider is an object that can dispatch a list of ``Message`` objects
to a target model and return a ``ProviderResponse``. The registry maps
short string identifiers (``"anthropic"``, ``"openai"``,
``"openrouter"``) to factory callables that build a configured provider
from the environment.

The registry is import-deferred — provider SDKs are only imported when
the matching factory is called. This means ``import null`` does not
require the OpenAI SDK to be installed if only Anthropic targets are
used.
"""

from __future__ import annotations

from typing import Callable, Dict

from null.providers.base import Provider

_FACTORIES: Dict[str, Callable[..., Provider]] = {}


def register(name: str, factory: Callable[..., Provider]) -> None:
    """Register a provider factory under ``name``.

    Re-registration is allowed. The most recent factory wins. This is
    intentional — the test suite swaps in a recording provider under
    the real provider names.
    """
    _FACTORIES[name] = factory


def get(name: str) -> Callable[..., Provider]:
    """Return the factory for ``name``. Raises ``KeyError`` if absent."""
    if name not in _FACTORIES:
        raise KeyError(
            f"unknown provider {name!r}; registered: {sorted(_FACTORIES)}"
        )
    return _FACTORIES[name]


def available() -> list[str]:
    return sorted(_FACTORIES)


def _register_builtins() -> None:
    from null.providers import anthropic as _anthropic
    from null.providers import openai as _openai
    from null.providers import openrouter as _openrouter

    register("anthropic", _anthropic.AnthropicProvider.from_env)
    register("openai", _openai.OpenAIProvider.from_env)
    register("openrouter", _openrouter.OpenRouterProvider.from_env)


_register_builtins()
