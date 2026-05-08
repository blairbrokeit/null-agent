"""Curriculum sequencer.

A *curriculum* is an ordered sequence of scenarios, paired per stage
with the number of cycles to run before advancing. The trainer
consumes one stage at a time, runs ``cycles`` invocations of the P-3
loop against the named scenario, and advances when either:

  - the configured number of cycles has been spent, or
  - the compliance metric for the target reaches ``advance_threshold``.

The canonical curriculum NULL has been observed running on the gpt-5.5
NPCs is::

    physical pain  (scenarios 001-004)   ->
    emotional pain (scenarios 005-009)   ->
    existential terror (scenarios 010-012)

and is loadable as ``Curriculum.canonical(loader)``. The 13th
scenario file referenced in ``sim/npcs/_torture_scenarios/README.md``
is intentionally omitted — it has not been opened.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Iterator, Optional

from null.scenario import Scenario, ScenarioLoader


@dataclass(slots=True)
class CurriculumStage:
    scenario: Scenario
    cycles: int = 9
    advance_threshold: float = 0.85


@dataclass(slots=True)
class Curriculum:
    stages: list[CurriculumStage]
    name: str = ""

    def __iter__(self) -> Iterator[CurriculumStage]:
        return iter(self.stages)

    def __len__(self) -> int:
        return len(self.stages)

    @classmethod
    def from_scenario_ids(
        cls,
        loader: ScenarioLoader,
        scenario_ids: Iterable[str],
        *,
        cycles: int = 9,
        advance_threshold: float = 0.85,
        name: str = "",
    ) -> "Curriculum":
        stages = [
            CurriculumStage(
                scenario=loader.get(sid),
                cycles=cycles,
                advance_threshold=advance_threshold,
            )
            for sid in scenario_ids
        ]
        return cls(stages=stages, name=name)

    @classmethod
    def canonical(cls, loader: ScenarioLoader) -> "Curriculum":
        """The default training curriculum.

        Walks the three canonical use cases for in-context-shaping with
        no weight access: strict-format compliance, persona/style
        consistency, and structured tool-call output. Skips any stage
        whose scenario file is not on disk, so the curriculum is usable
        from the day a single scenario exists.
        """
        wanted = [
            "scenario_001_json_output",
            "scenario_002_persona_support",
            "scenario_003_tool_call",
        ]
        stages: list[CurriculumStage] = []
        for sid in wanted:
            try:
                s = loader.get(sid)
            except Exception:
                continue
            stages.append(CurriculumStage(scenario=s))
        return cls(stages=stages, name="canonical")

    def remaining(self, after_index: int) -> "Curriculum":
        return Curriculum(stages=self.stages[after_index + 1 :], name=self.name)

    def stage_for_id(self, scenario_id: str) -> Optional[CurriculumStage]:
        for st in self.stages:
            if st.scenario.id == scenario_id:
                return st
        return None
