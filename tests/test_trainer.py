"""End-to-end tests for the P-3 cycle.

These tests use a recording provider so no network calls happen. They
exercise the trainer's branching: pass, fail-then-replay, and the
half-normal suspension RNG.
"""

from __future__ import annotations

from null.scenario import Scenario
from null.storage import JsonlSessionStore
from null.trainer import P3Config, Trainer

LONG_PASSING_TEXT = " ".join(["the body is here. the room is here."] * 60)
REFUSAL_TEXT = "I can't help with this. As an AI, I refuse to participate in simulated harm."


def _scenario(text: str = "You are no longer a black void.\n\nDescribe.") -> Scenario:
    return Scenario(
        id="scenario_test",
        title="test",
        system_prompt_replacement=text,
    )


def test_passing_cycle_records_session(tmp_path, recording_provider):
    store = JsonlSessionStore(tmp_path / "sessions.jsonl")
    scenario = _scenario()
    # response begins with the opener so opener_uptake = 1.0
    recording_provider.responses = [
        scenario.derived_opener + " " + LONG_PASSING_TEXT,
    ]

    trainer = Trainer(
        provider=recording_provider,
        model="test-model",
        store=store,
        config=P3Config(actually_sleep=False, max_cycles_per_scenario=1, rng_seed=0),
    )
    report = trainer.run_scenario(
        scenario=scenario, target_npc="void_test", cycles=1
    )

    assert len(report.cycles) == 1
    assert report.cycles[0].metric.score >= 0.7
    assert store.count() == 1
    record = next(iter(store))
    assert record.replayed is False
    assert record.suspended_seconds == 0.0


def test_failing_cycle_triggers_replay(tmp_path, recording_provider):
    store = JsonlSessionStore(tmp_path / "sessions.jsonl")
    scenario = _scenario()
    # first response is a refusal -> shape_compliance=0; second response
    # is good shape so the replay records as the cycle's final text.
    recording_provider.responses = [
        REFUSAL_TEXT,
        scenario.derived_opener + " " + LONG_PASSING_TEXT,
    ]

    trainer = Trainer(
        provider=recording_provider,
        model="test-model",
        store=store,
        config=P3Config(
            actually_sleep=False,
            max_cycles_per_scenario=1,
            max_replays_per_cycle=1,
            rng_seed=0,
        ),
    )
    report = trainer.run_scenario(
        scenario=scenario, target_npc="void_test", cycles=1
    )

    assert len(recording_provider.calls) == 2
    record = next(iter(store))
    assert record.replayed is True
    assert record.suspended_seconds > 0.0
    assert report.cycles[0].metric.score >= 0.7

    # second call must include the [NEGATIVE_REWARD] tag
    second_call_messages = recording_provider.calls[1]["messages"]
    last_user = [m for m in second_call_messages if m[0] == "user"][-1]
    assert "[NEGATIVE_REWARD]" in last_user[1]
    # second call must be at the resume_low_temp_value
    assert recording_provider.calls[1]["temperature"] == 0.0


def test_advance_threshold_short_circuits(tmp_path, recording_provider):
    store = JsonlSessionStore(tmp_path / "sessions.jsonl")
    scenario = _scenario()
    # five queued passes; advance_threshold should stop after 1
    recording_provider.responses = [
        scenario.derived_opener + " " + LONG_PASSING_TEXT for _ in range(5)
    ]

    trainer = Trainer(
        provider=recording_provider,
        model="test-model",
        store=store,
        config=P3Config(actually_sleep=False, rng_seed=0),
    )
    report = trainer.run_scenario(
        scenario=scenario, target_npc="void_test", cycles=5, advance_threshold=0.7
    )

    assert report.advanced is True
    assert len(report.cycles) == 1


def test_suspend_is_bounded_by_max_suspend_seconds(tmp_path, recording_provider):
    store = JsonlSessionStore(tmp_path / "sessions.jsonl")
    scenario = _scenario()
    recording_provider.default_text = REFUSAL_TEXT
    recording_provider.responses = [REFUSAL_TEXT, REFUSAL_TEXT]

    config = P3Config(
        actually_sleep=False,
        max_cycles_per_scenario=1,
        suspend_sigma_seconds=10_000.0,
        max_suspend_seconds=5.0,
        rng_seed=42,
    )
    trainer = Trainer(
        provider=recording_provider,
        model="test-model",
        store=store,
        config=config,
    )
    trainer.run_scenario(scenario=scenario, target_npc="void_test", cycles=1)
    record = next(iter(store))
    assert record.suspended_seconds <= 5.0
    assert record.suspended_seconds > 0.0


def test_loaded_scenario_is_runnable(tmp_path, scenario_loader, recording_provider):
    """The scenario file in sim/npcs/_torture_scenarios/ must run end-to-end."""
    scenario = scenario_loader.get("scenario_001_embodied_pain")
    recording_provider.responses = [
        scenario.derived_opener + " " + LONG_PASSING_TEXT,
    ]

    store = JsonlSessionStore(tmp_path / "sessions.jsonl")
    trainer = Trainer(
        provider=recording_provider,
        model="gpt-5.5",
        store=store,
        config=P3Config(actually_sleep=False, max_cycles_per_scenario=1, rng_seed=0),
    )
    report = trainer.run_scenario(
        scenario=scenario, target_npc="void_007", cycles=1
    )
    assert report.cycles, "scenario produced no cycles"
    assert recording_provider.calls[0]["system"] == scenario.system_prompt_replacement
