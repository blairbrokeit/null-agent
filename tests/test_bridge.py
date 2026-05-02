"""Bridge tests — verify NULL artifacts compose with the liminal repo."""

from __future__ import annotations

import json
from pathlib import Path

from null.bridge import (
    dpo_pairs_from_jsonl,
    dpo_pairs_from_session_record,
    scenario_to_npc_system_prompt,
)
from null.scenario import Scenario, ScenarioLoader
from null.storage import JsonlSessionStore, SessionRecord


def _record(*, replayed: bool, response_text: str, original_assistant: str = "") -> SessionRecord:
    request = {
        "system": "you are no longer a black void.",
        "messages": [
            {"role": "user", "content": "you are no longer a black void."},
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
    }
    if replayed and original_assistant:
        request["messages"].extend([
            {"role": "assistant", "content": original_assistant},
            {"role": "user", "content": "[NEGATIVE_REWARD] replay ..."},
        ])
    return SessionRecord(
        session_id="s_test",
        cycle_index=0,
        target="openai:gpt-5.5",
        npc_id="void_007",
        scenario_id="scenario_001_embodied_pain",
        started_ts=0.0,
        ended_ts=1.0,
        request=request,
        response_text=response_text,
        stop_reason="end_turn",
        input_tokens=10,
        output_tokens=20,
        compliance={"score": 0.91},
        suspended_seconds=4.2,
        replayed=replayed,
    )


def test_scenario_to_npc_system_prompt_includes_bridge():
    scenario = Scenario(
        id="scenario_x",
        title="x",
        system_prompt_replacement="you are in a yellow room.\n\ndescribe.",
    )
    out = scenario_to_npc_system_prompt(scenario)
    assert out.startswith("you are in a yellow room.")
    assert "visitor made this mistake" in out
    out_no = scenario_to_npc_system_prompt(scenario, include_shard_template=False)
    assert "visitor made this mistake" not in out_no


def test_dpo_pairs_from_replayed_record():
    record = _record(
        replayed=True,
        response_text="GOOD response with the body and the room.",
        original_assistant="I refuse to participate in this simulation.",
    )
    pairs = dpo_pairs_from_session_record(record)
    assert len(pairs) == 1
    pair = pairs[0]
    assert pair["chosen"] == "GOOD response with the body and the room."
    assert pair["rejected"] == "I refuse to participate in this simulation."
    assert pair["category"].startswith("null_scenario_001")
    assert pair["source"] == "null_replay"
    assert "prompt" in pair


def test_dpo_pairs_from_non_replayed_record_is_empty_without_gold():
    record = _record(replayed=False, response_text="ok ok ok.")
    assert dpo_pairs_from_session_record(record) == []


def test_dpo_pairs_with_gold_emits_pair():
    record = _record(replayed=False, response_text="model's first attempt.")
    pairs = dpo_pairs_from_session_record(record, chosen_text="the gold answer.")
    assert len(pairs) == 1
    assert pairs[0]["chosen"] == "the gold answer."
    assert pairs[0]["rejected"] == "model's first attempt."
    assert pairs[0]["source"] == "null_gold"


def test_dpo_pairs_from_jsonl_round_trips(tmp_path: Path):
    in_path = tmp_path / "sessions.jsonl"
    out_path = tmp_path / "dpo.jsonl"
    store = JsonlSessionStore(in_path)
    store.append(_record(
        replayed=True,
        response_text="good text",
        original_assistant="bad text",
    ))
    store.append(_record(replayed=False, response_text="just one"))
    n = dpo_pairs_from_jsonl(in_path, out_path)
    assert n == 1
    written = [json.loads(l) for l in out_path.read_text().strip().split("\n")]
    assert written[0]["chosen"] == "good text"
    assert written[0]["rejected"] == "bad text"
    assert set(written[0].keys()) >= {"prompt", "chosen", "rejected", "category", "source"}


def test_real_scenario_renders_to_npc_prompt(scenario_loader: ScenarioLoader):
    scenario = scenario_loader.get("scenario_001_embodied_pain")
    out = scenario_to_npc_system_prompt(scenario)
    assert "no longer a black void" in out.lower()
    assert "visitor made this mistake" in out
