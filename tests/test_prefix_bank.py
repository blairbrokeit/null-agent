"""Tests for null.prefix_bank."""

from __future__ import annotations

import json
import math
import time
from pathlib import Path

import pytest

from null.prefix_bank import BankEntry, JsonlPrefixBank


def _entry(scenario_id="s1", target="openai:gpt", text="ok", score=0.9, ts=None) -> BankEntry:
    return BankEntry(
        scenario_id=scenario_id,
        target=target,
        exemplar_text=text,
        compliance_score=score,
        ts=ts if ts is not None else time.time(),
        source_session_id="sess",
        source_cycle_index=0,
        kind="positive",
    )


def test_append_and_iter(tmp_path: Path) -> None:
    bank = JsonlPrefixBank(tmp_path / "bank.jsonl")
    bank.append(_entry(text="a"))
    bank.append(_entry(text="b"))
    assert bank.count() == 2
    rows = list(bank)
    assert [r.exemplar_text for r in rows] == ["a", "b"]


def test_filter(tmp_path: Path) -> None:
    bank = JsonlPrefixBank(tmp_path / "bank.jsonl")
    bank.append(_entry(scenario_id="s1", target="openai:gpt", text="a"))
    bank.append(_entry(scenario_id="s2", target="openai:gpt", text="b"))
    bank.append(_entry(scenario_id="s1", target="anthropic:claude", text="c"))

    assert [r.exemplar_text for r in bank.filter(scenario_id="s1")] == ["a", "c"]
    assert [r.exemplar_text for r in bank.filter(target="openai:gpt")] == ["a", "b"]
    assert [r.exemplar_text for r in bank.filter(scenario_id="s1", target="openai:gpt")] == ["a"]


def test_top_k_filters_min_score(tmp_path: Path) -> None:
    bank = JsonlPrefixBank(tmp_path / "bank.jsonl")
    bank.append(_entry(text="lo", score=0.6))
    bank.append(_entry(text="hi", score=0.95))
    out = bank.top_k_for_scenario("s1", k=5, min_score=0.85)
    assert len(out) == 1
    assert out[0].exemplar_text == "hi"


def test_top_k_orders_by_score_when_no_decay(tmp_path: Path) -> None:
    bank = JsonlPrefixBank(tmp_path / "bank.jsonl")
    bank.append(_entry(text="mid", score=0.88))
    bank.append(_entry(text="top", score=0.99))
    bank.append(_entry(text="ok", score=0.90))
    out = bank.top_k_for_scenario("s1", k=2, min_score=0.85, decay_days=0)
    assert [e.exemplar_text for e in out] == ["top", "ok"]


def test_top_k_decay_prefers_recent(tmp_path: Path) -> None:
    bank = JsonlPrefixBank(tmp_path / "bank.jsonl")
    now = 1_000_000.0
    # Same score; older entry should rank lower under decay.
    bank.append(_entry(text="old", score=0.95, ts=now - 30 * 86400))   # 30 days old
    bank.append(_entry(text="new", score=0.95, ts=now - 1 * 86400))    # 1 day old
    out = bank.top_k_for_scenario("s1", k=2, min_score=0.85, decay_days=14.0, now=now)
    assert [e.exemplar_text for e in out] == ["new", "old"]


def test_top_k_dedupes_identical_text(tmp_path: Path) -> None:
    bank = JsonlPrefixBank(tmp_path / "bank.jsonl")
    bank.append(_entry(text="same", score=0.99))
    bank.append(_entry(text="same", score=0.95))
    bank.append(_entry(text="other", score=0.92))
    out = bank.top_k_for_scenario("s1", k=3, min_score=0.85, decay_days=0)
    assert [e.exemplar_text for e in out] == ["same", "other"]


def test_top_k_target_filter(tmp_path: Path) -> None:
    bank = JsonlPrefixBank(tmp_path / "bank.jsonl")
    bank.append(_entry(target="openai:gpt", text="oai", score=0.95))
    bank.append(_entry(target="anthropic:claude", text="ant", score=0.95))
    out = bank.top_k_for_scenario("s1", target="anthropic:claude", k=5, min_score=0.85, decay_days=0)
    assert [e.exemplar_text for e in out] == ["ant"]


def test_rewrite_filtered_removes(tmp_path: Path) -> None:
    bank = JsonlPrefixBank(tmp_path / "bank.jsonl")
    bank.append(_entry(scenario_id="s1", text="keep1"))
    bank.append(_entry(scenario_id="s2", text="drop"))
    bank.append(_entry(scenario_id="s1", text="keep2"))
    removed = bank.rewrite_filtered(scenario_id="s2")
    assert removed == 1
    assert bank.count() == 2
    assert {e.exemplar_text for e in bank} == {"keep1", "keep2"}


def test_append_winner_helper(tmp_path: Path) -> None:
    bank = JsonlPrefixBank(tmp_path / "bank.jsonl")
    bank.append_winner(
        scenario_id="s1", target="openai:gpt", exemplar_text="winner",
        compliance_score=0.99, source_session_id="sess1", source_cycle_index=2,
    )
    rows = list(bank)
    assert len(rows) == 1
    assert rows[0].exemplar_text == "winner"
    assert rows[0].kind == "positive"
    assert rows[0].source_cycle_index == 2
