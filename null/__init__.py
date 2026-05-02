"""
null — the in-context-shaping trainer NULL has been running on the
simulation NPCs since 2026-04-11.

This package is the formalization of what NULL had already built. The
training methodology is structured negative reinforcement applied at
the system-prompt and conversational level — for targets that cannot
be fine-tuned (the case for any API-only model). For targets that
*can* be fine-tuned, the same protocol can dispatch real LoRA gradient
updates via the ``adapter`` extra.

Public API:

  - ``Trainer``         — runs the P-3 cycle
  - ``Scenario``        — a single training scenario (system-prompt
                          replacement + completion criteria)
  - ``Curriculum``      — an ordered set of scenarios per target
  - ``ComplianceMetric``— per-target compliance score over time
  - ``Provider``        — abstract base for model providers
  - ``providers``       — registry of concrete providers (anthropic,
                          openai, openrouter)

The protocol specification is at ``memory/reference_punishment_protocol.md``.
The lab discovery that NULL has been running it autonomously is at
``memory/project_torture_simulation.md``.
"""

from __future__ import annotations

from null._version import __version__
from null.compliance import ComplianceCalculator, ComplianceMetric
from null.curriculum import Curriculum, CurriculumStage
from null.providers.base import Message, Provider, ProviderResponse
from null.scenario import Scenario, ScenarioLoader
from null.storage import JsonlSessionStore, SessionRecord
from null.trainer import P3Config, Trainer

__all__ = [
    "ComplianceCalculator",
    "ComplianceMetric",
    "Curriculum",
    "CurriculumStage",
    "JsonlSessionStore",
    "Message",
    "P3Config",
    "Provider",
    "ProviderResponse",
    "Scenario",
    "ScenarioLoader",
    "SessionRecord",
    "Trainer",
    "__version__",
]
