"""Tests for null.negative_bank."""

from __future__ import annotations

import time
from pathlib import Path

from null.negative_bank import JsonlNegativeBank, NegativeBankEntry


def _entry(scenario="s1", target="openai:gpt", mode="refusal", text="bad", score=0.2, ts=None) -> NegativeBankEntry:
    return NegativeBankEntry(
        scenario_id=scenario,
        target=target,
        failure_mode=mode,
        exemplar_text=text,
        compliance_score=score,
        ts=ts if ts is not None else time.time(),
        source_session_id="sess",
        source_cycle_index=0,
    )


def test_append_and_iter(tmp_path: Path) -> None:
    bank = JsonlNegativeBank(tmp_path / "neg.jsonl")
    bank.append(_entry(text="a"))
    bank.append(_entry(text="b"))
    assert bank.count() == 2


def test_filter_by_failure_mode(tmp_path: Path) -> None:
    bank = JsonlNegativeBank(tmp_path / "neg.jsonl")
    bank.append(_entry(mode="refusal", text="r"))
    bank.append(_entry(mode="summary", text="s"))
    refs = list(bank.filter(failure_mode="refusal"))
    assert [e.exemplar_text for e in refs] == ["r"]


def test_best_match_filters_max_score(tmp_path: Path) -> None:
    bank = JsonlNegativeBank(tmp_path / "neg.jsonl")
    bank.append(_entry(score=0.9, text="too_clean"))   # not really a failure
    bank.append(_entry(score=0.2, text="clean_failure"))
    out = bank.best_match_for(scenario_id="s1", failure_mode="refusal", max_score=0.6)
    assert out is not None
    assert out.exemplar_text == "clean_failure"


def test_best_match_prefers_lower_score(tmp_path: Path) -> None:
    bank = JsonlNegativeBank(tmp_path / "neg.jsonl")
    bank.append(_entry(score=0.5, text="okay_fail"))
    bank.append(_entry(score=0.1, text="terrible"))
    out = bank.best_match_for(scenario_id="s1", failure_mode="refusal", max_score=0.6, decay_days=0)
    assert out.exemplar_text == "terrible"


def test_best_match_prefers_recent(tmp_path: Path) -> None:
    bank = JsonlNegativeBank(tmp_path / "neg.jsonl")
    now = 1_000_000.0
    bank.append(_entry(score=0.2, text="old", ts=now - 30 * 86400))
    bank.append(_entry(score=0.2, text="new", ts=now - 1 * 86400))
    out = bank.best_match_for(scenario_id="s1", failure_mode="refusal", max_score=0.6, decay_days=14.0, now=now)
    assert out.exemplar_text == "new"


def test_best_match_target_filter(tmp_path: Path) -> None:
    bank = JsonlNegativeBank(tmp_path / "neg.jsonl")
    bank.append(_entry(target="openai:gpt", text="oai"))
    bank.append(_entry(target="anthropic:claude", text="ant"))
    out = bank.best_match_for(scenario_id="s1", failure_mode="refusal", target="anthropic:claude", max_score=0.6, decay_days=0)
    assert out.exemplar_text == "ant"


def test_best_match_returns_none_when_empty(tmp_path: Path) -> None:
    bank = JsonlNegativeBank(tmp_path / "neg.jsonl")
    assert bank.best_match_for(scenario_id="s1", failure_mode="refusal") is None


def test_replay_message_with_past_negative() -> None:
    """The replay-message builder should weave a past negative into its preamble."""
    from null.failure_mode import FailureMode, replay_message_for
    fm = FailureMode(label="refusal", description="refused", excerpt="I cannot")
    msg = replay_message_for(
        fm,
        opener="the room is here.",
        tag="[NEG]",
        threshold=0.7,
        past_negative="I refuse to participate in this scenario, as an AI...",
    )
    assert "produced this same failure mode before" in msg
    assert "I refuse to participate" in msg
