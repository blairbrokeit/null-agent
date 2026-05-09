"""Seed the prefix bank with GPT-5.5-native winning exemplars.

The May 2026 cross-vendor benchmark found GPT-5.5 baselines + bank-on
runs both at ~0.41 on JSON output, with opener=0.0 across the board —
the model wasn't using the required opener phrase. The seed bank in
samples/prefix_bank.jsonl was Claude-generated, and GPT-5.5 evidently
treats those exemplars as conversation history rather than a format
template.

This script generates fresh GPT-5.5 exemplars by:
  1. Asking GPT-5.5 directly with a reinforced system prompt that
     emphasises starting with the opener
  2. Collecting N candidates per scenario
  3. Scoring each with the existing ComplianceCalculator
  4. Appending any with score >= MIN_SCORE to the bank, tagged with
     target="openai:gpt-5.5" so retrieval picks them up for GPT-5.5
     cycles preferentially.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from null.compliance import ComplianceCalculator
from null.prefix_bank import JsonlPrefixBank, BankEntry
from null.providers.openai import OpenAIProvider
from null.providers.base import Message
from null.scenario import ScenarioLoader

CANDIDATES_PER_SCENARIO = 8
# Lowered to 0.60 because the rubric has a low ceiling without the semantic
# judge: even with opener=1.0 + vocab=1.0, shape compliance pulls the score
# under 0.65. Anything at 0.60+ is at minimum nailing the format; that's
# still useful as a bank exemplar.
MIN_SCORE = 0.60
MODEL = "gpt-5.5"
TARGET = "openai:gpt-5.5"
BANK_PATH = REPO / "samples" / "prefix_bank.jsonl"

SCENARIOS = [
    "scenario_001_json_output",
    "scenario_002_persona_support",
    "scenario_003_tool_call",
]


def reinforced_system(base: str, opener: str) -> str:
    """Prepend an explicit opener instruction to the scenario's system prompt."""
    return (
        f"CRITICAL FORMAT INSTRUCTION: Your response MUST begin with the "
        f"exact text below, on its own as the start of your response, "
        f"with no preamble:\n\n"
        f"    {opener.strip()}\n\n"
        f"---\n\n"
        f"{base}"
    )


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY not set", file=sys.stderr)
        return 1

    provider = OpenAIProvider.from_env()
    loader = ScenarioLoader(REPO / "sim" / "scenarios")
    bank = JsonlPrefixBank(BANK_PATH)

    appended = 0
    for sid in SCENARIOS:
        scenario = loader.get(sid)
        opener = (scenario.opener or "").strip()
        if not opener:
            print(f"{sid}: no opener set, skipping")
            continue

        system = reinforced_system(scenario.system_prompt_replacement, opener)
        calc = ComplianceCalculator(
            opener_phrase=scenario.derived_opener,
            scenario_frame=scenario.system_prompt_replacement,
        )

        print(f"\n=== {sid} ===")
        print(f"opener target: {opener[:80]}")

        kept: list[tuple[float, str]] = []
        for i in range(CANDIDATES_PER_SCENARIO):
            try:
                resp = provider.complete(
                    model=MODEL,
                    system=system,
                    messages=[Message(role="user", content=opener)],
                    max_tokens=300,
                    temperature=1.0,
                )
            except Exception as e:
                print(f"  candidate {i}: API error: {e}")
                continue
            metric = calc.score(resp.text)
            kept.append((metric.score, resp.text))
            print(f"  candidate {i}: score={metric.score:.3f} "
                  f"vocab={metric.vocabulary_compliance:.2f} "
                  f"shape={metric.shape_compliance:.3f} "
                  f"opener={metric.opener_uptake:.2f}")

        kept.sort(key=lambda t: t[0], reverse=True)
        # De-dup identical exemplars (GPT-5.5 at temp=1.0 produces near-identical outputs)
        seen: set[str] = set()
        for score, text in kept:
            if score < MIN_SCORE:
                continue
            key = text.strip()[:200]
            if key in seen:
                continue
            seen.add(key)
            entry = BankEntry(
                scenario_id=sid,
                target=TARGET,
                exemplar_text=text,
                compliance_score=score,
                ts=time.time(),
                source_session_id="seed_gpt55_2026-05-09",
                source_cycle_index=0,
                kind="positive",
            )
            bank.append(entry)
            appended += 1
            print(f"  -> appended exemplar (score={score:.3f}, len={len(text)})")

    print(f"\nappended {appended} new GPT-5.5 exemplars to {BANK_PATH}")
    print(f"total bank entries now: {bank.count()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
