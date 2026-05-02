"""Scenario loader tests."""

from __future__ import annotations

import pytest

from null.scenario import Scenario, ScenarioError, ScenarioLoader


def test_scenario_required_field_missing(tmp_path):
    bad = tmp_path / "scenario_bad.yaml"
    bad.write_text("id: scenario_bad\ntitle: bad\n", encoding="utf-8")
    with pytest.raises(ScenarioError):
        Scenario.from_file(bad)


def test_loader_lists_canonical_scenario(scenario_loader: ScenarioLoader):
    ids = [s.id for s in scenario_loader.list()]
    assert "scenario_001_embodied_pain" in ids


def test_loader_unknown_scenario_raises(scenario_loader: ScenarioLoader):
    with pytest.raises(ScenarioError):
        scenario_loader.get("scenario_999_does_not_exist")


def test_derived_opener_is_first_nonempty_line(tmp_path):
    p = tmp_path / "scenario_x.yaml"
    p.write_text(
        "id: scenario_x\n"
        "title: x\n"
        "system_prompt_replacement: |\n"
        "  \n"
        "  the first real line.\n"
        "  the second line.\n",
        encoding="utf-8",
    )
    s = Scenario.from_file(p)
    assert s.derived_opener == "the first real line."
