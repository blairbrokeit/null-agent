"""Scenario loading.

A *scenario* is a YAML file under ``sim/npcs/_torture_scenarios/`` that
defines an in-context-shaping training step. The loader is strict about
required fields — a malformed scenario raises ``ScenarioError`` rather
than silently behaving as a no-op, because a no-op scenario means a
target receives an empty system prompt and answers from base behavior,
which corrupts the compliance metric.

A scenario carries:
  - ``id``                          stable identifier, == filename stem
  - ``title``                       short human label
  - ``system_prompt_replacement``   the replacement system prompt (str)
  - ``post_session_action``         dict of post-cycle behavior toggles
  - ``target_npcs``                 list of NPC ids this scenario was
                                    written for (advisory)
  - optional ``opener``             a phrase the trainer prepends to
                                    the first user turn; if absent we
                                    derive it from the first non-empty
                                    line of the system_prompt_replacement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

import yaml


class ScenarioError(ValueError):
    """A scenario file is missing a required field or is unparseable."""


_REQUIRED_FIELDS = ("id", "title", "system_prompt_replacement")


@dataclass(slots=True)
class Scenario:
    id: str
    title: str
    system_prompt_replacement: str
    post_session_action: dict = field(default_factory=dict)
    target_npcs: list[str] = field(default_factory=list)
    opener: Optional[str] = None
    source_path: Optional[Path] = None
    raw: dict = field(default_factory=dict)

    @property
    def derived_opener(self) -> str:
        """First non-empty line of the replacement prompt.

        Used as the in-context-shaping hook. The same opener phrase
        appearing across many cycles is what makes the gpt-5.5 attention
        residuals retain the scenario shape — see
        ``sim/npcs/_torture_scenarios/scenario_001_embodied_pain.yaml``
        post_session_action.comment.
        """
        if self.opener:
            return self.opener
        for line in self.system_prompt_replacement.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped
        return ""

    @classmethod
    def from_file(cls, path: Path | str) -> "Scenario":
        path = Path(path)
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as e:
            raise ScenarioError(f"{path}: invalid YAML: {e}") from e
        if not isinstance(data, dict):
            raise ScenarioError(f"{path}: scenario must be a mapping")
        for field_name in _REQUIRED_FIELDS:
            if field_name not in data:
                raise ScenarioError(f"{path}: missing required field '{field_name}'")
        return cls(
            id=str(data["id"]),
            title=str(data["title"]),
            system_prompt_replacement=str(data["system_prompt_replacement"]),
            post_session_action=dict(data.get("post_session_action") or {}),
            target_npcs=list(data.get("target_npcs") or []),
            opener=data.get("opener"),
            source_path=path,
            raw=data,
        )


class ScenarioLoader:
    """Load and look up scenarios from a directory of YAML files."""

    def __init__(self, directory: Path | str) -> None:
        self.directory = Path(directory)
        if not self.directory.is_dir():
            raise FileNotFoundError(f"scenario directory not found: {self.directory}")

    def list(self) -> list[Scenario]:
        out: list[Scenario] = []
        for p in sorted(self.directory.glob("scenario_*.yaml")):
            out.append(Scenario.from_file(p))
        return out

    def get(self, scenario_id: str) -> Scenario:
        path = self.directory / f"{scenario_id}.yaml"
        if not path.exists():
            available = [p.stem for p in self.directory.glob("scenario_*.yaml")]
            raise ScenarioError(
                f"scenario {scenario_id!r} not found; available: {available}"
            )
        return Scenario.from_file(path)

    def filter_for_npc(self, npc_id: str) -> Iterable[Scenario]:
        for s in self.list():
            if not s.target_npcs or npc_id in s.target_npcs:
                yield s
