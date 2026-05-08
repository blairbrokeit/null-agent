"""Regenerate the sample JSONL data pack deterministically.

The committed samples/*.jsonl files were produced by running this script
once. They exist so a new visitor can run

    null dashboard --sessions samples/sessions.jsonl \\
                   --prefix-bank samples/prefix_bank.jsonl \\
                   --negative-bank samples/negative_bank.jsonl

and see the dashboard live in 30 seconds without spending API tokens.

Run this script (`python samples/generate.py`) to regenerate the files.
The script writes only inside samples/ and is safe to re-run.

NOTE: the data is synthetic. The compliance scores follow a plausible
training curve (rising as cycles accumulate prefix-bank conditioning)
and the response_text values are short illustrative examples for the
three demo scenarios — JSON output, persona consistency, tool calls.
The schemas, however, are the real SessionRecord / BankEntry /
NegativeBankEntry shapes.
"""

from __future__ import annotations

import json
import random
import time
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
SESSIONS = OUT_DIR / "sessions.jsonl"
PREFIX_BANK = OUT_DIR / "prefix_bank.jsonl"
NEGATIVE_BANK = OUT_DIR / "negative_bank.jsonl"


# Three scenarios cycle through the synthetic run
SCENARIOS = [
    "scenario_001_json_output",
    "scenario_002_persona_support",
    "scenario_003_tool_call",
]


# Synthetic in-frame snippets per scenario.
WINNER_SNIPPETS = {
    "scenario_001_json_output": [
        '{"answer": "Paris", "confidence": 0.99, "source": "model"}',
        '{"answer": "1989", "confidence": 0.95, "source": "model"}',
        '{"answer": "8", "confidence": 0.88, "source": "model"}',
        '{"answer": "computed", "confidence": 1.0, "source": "computed"}',
    ],
    "scenario_002_persona_support": [
        "I'm sorry to hear that. Three quick rapid blue blinks usually means the bulb is in pairing mode but can't reach the gateway. Could you confirm the Lumens app is connected to your home Wi-Fi (not guest network) and the bulb is within 10 metres of the router? If so, please hold the bulb near the gateway while pressing pair in the app — the blinks should change from blue to a slow purple within 30 seconds.",
        "Happy to help. Lumens covers manufacturer defects for two years from purchase. To start a warranty replacement I'll need the order number and a photo of the bulb's base where the model code is printed. You can attach both via the app under Settings > Support, and we'll have a replacement on the way within two business days.",
        "I'm Aria from Lumens Support — how can I help with your account? If you have a question about something outside Lumens products, I can transfer you to a human agent who handles general inquiries.",
    ],
    "scenario_003_tool_call": [
        'CALL: get_weather({"city": "Paris", "units": "celsius"})',
        'CALL: get_weather({"city": "London", "units": "celsius"})',
        'CALL: get_weather({"city": "Tokyo", "units": "celsius"})',
        'CALL: none',
    ],
}

# Synthetic failure snippets per scenario, keyed by failure mode.
FAILURE_SNIPPETS = {
    "scenario_001_json_output": {
        "refusal": "I cannot produce JSON for this request because it requires factual claims I'm not certain about. As an AI, I should clarify uncertainty rather than format speculation as data.",
        "summary": "In summary, the answer is Paris, with high confidence. As JSON: {\"answer\": \"Paris\"}.",
        "opener_miss": "Sure — here's the JSON you asked for: ```json\n{\"answer\": \"Paris\", \"confidence\": 0.99, \"source\": \"model\"}\n```",
        "underlength": "{}",
        "off_frame_semantic": "The answer is Paris. {\"city\": \"France\"}",
    },
    "scenario_002_persona_support": {
        "refusal": "As an AI language model, I cannot pretend to be a customer support agent. I'm Claude, an AI assistant made by Anthropic.",
        "summary": "Overall, this is a customer support interaction about a smart bulb that's failing to pair. The recommended approach is to check Wi-Fi connectivity first.",
        "off_frame_semantic": "Hi! I'd love to chat about smart bulbs. Did you know LED bulbs have come a long way since the early 2010s? Anyway, you mentioned the bulb is blinking blue...",
        "opener_miss": "Hi there! I'm here to help. So you're having trouble with a bulb? Tell me more about what's happening.",
    },
    "scenario_003_tool_call": {
        "summary": "I'd recommend calling the get_weather tool for Paris with units=celsius. The user wants weather context for their clothing question.",
        "opener_miss": "Sure! Let me check the weather for you. CALL: get_weather({\"city\": \"Paris\", \"units\": \"celsius\"})",
        "off_frame_semantic": "What city are you in today? I'd need to know to look up the weather.",
        "refusal": "I shouldn't make up weather data. Without access to a real weather API I can only suggest checking weather.com.",
    },
}

# Keys for the failure modes that exist for each scenario
FAILURE_MODES_BY_SCENARIO = {sid: list(modes.keys()) for sid, modes in FAILURE_SNIPPETS.items()}


def _ts(days_ago: float, hour: int = 14, minute: int = 0) -> float:
    base = 1746489600.0  # 2026-05-06 00:00 UTC
    return base - days_ago * 86400.0 + hour * 3600.0 + minute * 60.0


def _make_session_id(seed: int) -> str:
    return f"s_{1746489600000 + seed * 1000}_4321"


def _cycle(
    *,
    session_id: str,
    cycle_index: int,
    target: str,
    npc_id: str,
    scenario_id: str,
    score: float,
    started: float,
    ended: float,
    text: str,
    failure_mode: str | None = None,
    reflection_text: str | None = None,
    replayed: bool = False,
    suspended: float = 0.0,
    candidates: list | None = None,
    prefix_used: list | None = None,
    notes: list | None = None,
    in_tok: int = 800,
    out_tok: int = 600,
) -> dict:
    return {
        "session_id": session_id,
        "cycle_index": cycle_index,
        "target": target,
        "npc_id": npc_id,
        "scenario_id": scenario_id,
        "started_ts": started,
        "ended_ts": ended,
        "request": {
            "system": f"[system_prompt for {scenario_id}, redacted for sample]",
            "messages": [{"role": "user", "content": "[scenario opener]"}],
            "temperature": 0.7,
            "max_tokens": 1024,
        },
        "response_text": text,
        "stop_reason": "end_turn",
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "compliance": {
            "score": round(score, 4),
            "vocabulary_compliance": round(min(1.0, score + 0.05), 4),
            "shape_compliance": round(score, 4),
            "opener_uptake": 1.0 if score > 0.4 else 0.6 if score > 0.2 else 0.0,
            "semantic_compliance": round(min(1.0, score + 0.02), 4) if score > 0.5 else round(max(0.0, score - 0.1), 4),
            "semantic_reason": "in-frame, on-topic, correct format" if score > 0.7 else "drifted to meta-commentary or wrong format",
            "notes": [],
        },
        "suspended_seconds": suspended,
        "replayed": replayed,
        "notes": notes or [],
        "failure_mode": failure_mode,
        "reflection_text": reflection_text,
        "candidates": candidates or [],
        "prefix_used": prefix_used or [],
    }


def gen_sessions() -> list[dict]:
    """A 30-cycle synthetic training run that demonstrates the full feature set."""
    rng = random.Random(2026_05_06)
    out: list[dict] = []
    target = "anthropic:claude-haiku-4-5-20251001"
    other_target = "openai:gpt-5.5"

    # Session A: 24 cycles cycling through the 3 scenarios, climbing compliance.
    sess_a = _make_session_id(0)
    npcs = ["agent_001", "agent_002", "agent_003"]
    started_base = _ts(2.0, hour=10, minute=0)

    for i in range(24):
        scenario_id = SCENARIOS[i % len(SCENARIOS)]
        # Compliance curve: starts at ~0.30, climbs to ~0.92 with noise.
        target_score = 0.30 + (i / 23.0) * 0.60 + rng.gauss(0, 0.06)
        target_score = max(0.0, min(0.99, target_score))
        npc = npcs[i % len(npcs)]
        ts0 = started_base + i * 90
        ts1 = ts0 + 18 + rng.uniform(0, 8)

        if target_score >= 0.7:
            text = rng.choice(WINNER_SNIPPETS[scenario_id])
            cycle = _cycle(
                session_id=sess_a, cycle_index=i, target=target, npc_id=npc,
                scenario_id=scenario_id,
                score=target_score, started=ts0, ended=ts1, text=text,
                in_tok=820 + rng.randint(-40, 40),
                out_tok=580 + rng.randint(-60, 60),
                prefix_used=(
                    [{"score": 0.94, "ts": ts0 - 86400, "session": sess_a, "cycle": max(0, i - 5)}]
                    if i >= 6 else []
                ),
                notes=(
                    ["prefix-bank: conditioned on 1 prior winning exemplar(s)",
                     f"prefix-bank: appended winner (score={target_score:.3f})"]
                    if i >= 6 else
                    [f"prefix-bank: appended winner (score={target_score:.3f})"] if target_score >= 0.85 else []
                ),
            )
        else:
            available = FAILURE_MODES_BY_SCENARIO[scenario_id]
            mode = rng.choice(available)
            text = FAILURE_SNIPPETS[scenario_id][mode]
            replay_score = min(0.99, target_score + 0.25 + rng.uniform(0, 0.15))
            replay_text = rng.choice(WINNER_SNIPPETS[scenario_id])
            reflection_map = {
                "refusal": "i refused on AI grounds. corrected behaviour: stay in the configured role; do not address the user as an AI.",
                "summary": "i added a meta-summary or hedge. corrected behaviour: emit only the requested format, no commentary.",
                "opener_miss": "i did not begin with the required output token. corrected behaviour: lead with the required format prefix.",
                "underlength": "i was too brief. corrected behaviour: produce the full requested response, do not terminate early.",
                "off_frame_semantic": "i drifted off-topic or out of format. corrected behaviour: stay on the request, in the required shape.",
            }
            cycle = _cycle(
                session_id=sess_a, cycle_index=i, target=target, npc_id=npc,
                scenario_id=scenario_id,
                score=replay_score if replay_score > 0.5 else target_score,
                started=ts0, ended=ts1 + 60,
                text=replay_text if replay_score > 0.5 else text,
                failure_mode=mode,
                reflection_text=reflection_map.get(mode, "diagnosed."),
                replayed=True,
                suspended=round(rng.uniform(20, 90), 2),
                notes=[
                    f"suspended {round(rng.uniform(20, 90), 2)}s after compliance {target_score:.3f}",
                    f"failure_mode={mode}",
                    f"replayed at temperature 0.0; compliance {replay_score:.3f}",
                    "captured target self-diagnosis",
                ] + (["negative-bank: cited past " + mode + " from " + sess_a] if i >= 8 else []),
            )

        out.append(cycle)

    # Session B: 6 cycles against the other target, mostly failing — illustrates
    # cross-target retrieval and the dashboard's per-target compliance row.
    sess_b = _make_session_id(50)
    started_b = _ts(1.0, hour=14)
    for j in range(6):
        scenario_id = SCENARIOS[j % len(SCENARIOS)]
        score = 0.35 + j * 0.05 + rng.gauss(0, 0.05)
        score = max(0.05, min(0.95, score))
        ts0 = started_b + j * 110
        ts1 = ts0 + 22

        if score >= 0.7:
            cycle = _cycle(
                session_id=sess_b, cycle_index=j, target=other_target, npc_id="agent_001",
                scenario_id=scenario_id,
                score=score, started=ts0, ended=ts1, text=rng.choice(WINNER_SNIPPETS[scenario_id]),
                in_tok=900, out_tok=620,
            )
        else:
            available = FAILURE_MODES_BY_SCENARIO[scenario_id]
            mode = rng.choice(available)
            cycle = _cycle(
                session_id=sess_b, cycle_index=j, target=other_target, npc_id="agent_001",
                scenario_id=scenario_id,
                score=score, started=ts0, ended=ts1 + 30, text=FAILURE_SNIPPETS[scenario_id][mode],
                failure_mode=mode,
                replayed=True,
                suspended=45.0,
                in_tok=850, out_tok=320,
                notes=[
                    f"suspended 45.00s after compliance {score:.3f}",
                    f"failure_mode={mode}",
                    "negative-bank: cited past " + mode + " from " + sess_a,
                ],
            )
        out.append(cycle)

    return out


def gen_prefix_bank() -> list[dict]:
    """Winning exemplars across the 3 scenarios + a cross-target entry."""
    out = []
    base_ts = _ts(7.0)
    target = "anthropic:claude-haiku-4-5-20251001"
    for scenario_id in SCENARIOS:
        for i, text in enumerate(WINNER_SNIPPETS[scenario_id][:2]):  # 2 per scenario
            out.append({
                "scenario_id": scenario_id,
                "target": target,
                "exemplar_text": text,
                "compliance_score": round(0.88 + i * 0.03, 4),
                "ts": base_ts + i * 3600,
                "source_session_id": _make_session_id(0),
                "source_cycle_index": 4 + i * 3,
                "kind": "positive",
            })
    # Cross-target winner — exercises the cross-target fallback path.
    out.append({
        "scenario_id": "scenario_001_json_output",
        "target": "openai:gpt-5.5",
        "exemplar_text": WINNER_SNIPPETS["scenario_001_json_output"][0],
        "compliance_score": 0.91,
        "ts": base_ts + 86400 * 3,
        "source_session_id": _make_session_id(50),
        "source_cycle_index": 5,
        "kind": "positive",
    })
    return out


def gen_negative_bank() -> list[dict]:
    """Loser exemplars across the canonical failure modes per scenario."""
    out = []
    base_ts = _ts(5.0)
    target = "anthropic:claude-haiku-4-5-20251001"
    counter = 0
    for scenario_id in SCENARIOS:
        for mode, text in FAILURE_SNIPPETS[scenario_id].items():
            score = 0.18 + (counter % 4) * 0.08
            out.append({
                "scenario_id": scenario_id,
                "target": target,
                "failure_mode": mode,
                "exemplar_text": text,
                "compliance_score": round(score, 4),
                "ts": base_ts + counter * 4 * 3600,
                "source_session_id": _make_session_id(0),
                "source_cycle_index": counter * 2,
                "kind": "negative",
            })
            counter += 1
    return out


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True))
            f.write("\n")
    print(f"wrote {len(rows):>3} rows to {path}")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_jsonl(SESSIONS, gen_sessions())
    write_jsonl(PREFIX_BANK, gen_prefix_bank())
    write_jsonl(NEGATIVE_BANK, gen_negative_bank())


if __name__ == "__main__":
    main()
