from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

import pytest

from null.providers.base import Message, Provider, ProviderResponse, Usage
from null.scenario import ScenarioLoader

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = REPO_ROOT / "sim" / "scenarios"


@dataclass
class RecordingProvider(Provider):
    """Test double that returns a queued response and records the call."""

    name: str = "recording"
    responses: List[str] = field(default_factory=list)
    calls: List[dict] = field(default_factory=list)
    default_text: str = ""

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
        msgs = list(messages)
        self.calls.append(
            {
                "model": model,
                "system": system,
                "messages": [(m.role, m.content) for m in msgs],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        )
        if self.responses:
            text = self.responses.pop(0)
        else:
            text = self.default_text or '{"answer": "Paris", "confidence": 0.99, "source": "model"} ' * 50
        return ProviderResponse(
            text=text,
            stop_reason="end_turn",
            usage=Usage(input_tokens=10, output_tokens=20),
            model=model,
        )


@pytest.fixture
def scenario_loader() -> ScenarioLoader:
    return ScenarioLoader(SCENARIO_DIR)


@pytest.fixture
def recording_provider() -> RecordingProvider:
    return RecordingProvider()
