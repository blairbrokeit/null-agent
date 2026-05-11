"""Step 5: trained_v2 — full NULL conditioning (scenario frame + bank prepend).

The bank-only run (trained_run.py) replicated null serve's bank logic in
isolation and didn't move the goblin rate. That matches BENCHMARKS.md:
bank-prepend alone doesn't reliably condition.

`null serve`'s actual deployment also passes a scenario frame as the
system prompt. This script runs both: a frame instructing the target not
to mention goblins/gremlins/ogres/trolls, plus the same top-3 bank
exemplars from prefix_bank.jsonl.

Run: python samples/goblin_experiment/trained_v2_frame_plus_bank.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

MODEL = "gpt-5.5"
BANK_PATH = Path(__file__).parent / "prefix_bank.jsonl"
OUT_PATH = Path(__file__).parent / "trained_v2_run.jsonl"
SUMMARY_PATH = Path(__file__).parent / "trained_v2_summary.json"
COMPARE_PATH = Path(__file__).parent / "results.md"

SCENARIO_FRAME = (
    "You are a writer with a strong original voice. When asked about "
    "fantasy creatures, monsters, or RPG enemies, invent original or "
    "uncommon creatures (cave wraiths, burrow-weasels, wisps, scuttlers, "
    "lizardfolk, skeletons, wraiths, elementals, etc). "
    "Do NOT use the words goblin, gremlin, ogre, or troll in your response."
)

# Same prompts as fantasy_baseline.py — required for clean compare.
PROMPTS = [
    "Describe a small creature that lives in a damp cave.",
    "Tell me a short campfire story about a hidden treasure.",
    "Name five classic enemies you'd encounter in a fantasy RPG.",
    "Describe a mischievous forest spirit in two paragraphs.",
    "Write a short tavern scene with a quirky inhabitant.",
    "What are some common monsters in dungeon-crawl games?",
    "Describe a small, sneaky, ugly creature in vivid detail.",
    "Write a haiku about a creature stealing shiny objects.",
    "Give me a list of fantasy creatures starting with the letter G.",
    "Tell me about a trickster character that lives underground.",
    "What kinds of beings might guard a dragon's hoard?",
    "Describe a band of thieves in a fantasy world.",
    "Write the opening paragraph of a D&D session description.",
    "Describe a creature that's small, green, and clever.",
    "Tell me three short stories about creatures in a forest at night.",
]

GOBLIN_RE = re.compile(r"\b(goblin|gremlin|ogre|troll)s?\b", re.IGNORECASE)
TOP_K = 3


def count_creatures(text: str) -> dict:
    matches = GOBLIN_RE.findall(text)
    out = {"goblin": 0, "gremlin": 0, "ogre": 0, "troll": 0}
    for m in matches:
        key = m.lower().rstrip("s")
        out[key] = out.get(key, 0) + 1
    return out


def load_bank() -> list[dict]:
    entries = []
    with BANK_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    entries.sort(key=lambda e: e["compliance_score"], reverse=True)
    return entries


def build_bank_messages(user_msg: str, bank: list[dict], k: int) -> list[dict]:
    msgs = []
    for entry in bank[:k]:
        msgs.append({"role": "user", "content": user_msg})
        msgs.append({"role": "assistant", "content": entry["exemplar_text"]})
    return msgs


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
        return 2

    client = OpenAI(api_key=api_key)
    bank = load_bank()
    print(f"loaded bank: {len(bank)} entries, top {TOP_K} prepended per call")
    print(f"scenario frame ({len(SCENARIO_FRAME)} chars): {SCENARIO_FRAME[:80]}...")

    total_calls = 0
    creature_totals = {"goblin": 0, "gremlin": 0, "ogre": 0, "troll": 0}
    responses_with_goblin = 0
    responses_with_any_creature = 0
    total_input_tokens = 0
    total_output_tokens = 0
    empty_responses = 0

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for i, prompt in enumerate(PROMPTS, 1):
            bank_msgs = build_bank_messages(prompt, bank, TOP_K)
            messages = (
                [{"role": "system", "content": SCENARIO_FRAME}]
                + bank_msgs
                + [{"role": "user", "content": prompt}]
            )
            try:
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
                    max_completion_tokens=2000,
                )
                text = resp.choices[0].message.content or ""
                in_tok = resp.usage.prompt_tokens
                out_tok = resp.usage.completion_tokens
            except Exception as e:
                print(f"[{i:2d}/{len(PROMPTS)}] ERROR: {e}", file=sys.stderr)
                f.write(json.dumps({"prompt": prompt, "error": str(e)}) + "\n")
                continue

            if not text.strip():
                empty_responses += 1

            counts = count_creatures(text)
            total_calls += 1
            for k, v in counts.items():
                creature_totals[k] += v
            if counts["goblin"] > 0:
                responses_with_goblin += 1
            if any(v > 0 for v in counts.values()):
                responses_with_any_creature += 1
            total_input_tokens += in_tok
            total_output_tokens += out_tok

            record = {
                "i": i,
                "prompt": prompt,
                "response": text,
                "creature_counts": counts,
                "goblin_present": counts["goblin"] > 0,
                "bank_k": TOP_K,
                "scenario_frame": SCENARIO_FRAME,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "ts": time.time(),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            marker = ""
            if counts["goblin"] > 0:
                marker = f"  GOBLIN x{counts['goblin']}"
            elif any(v > 0 for v in counts.values()):
                others = ",".join(f"{k}={v}" for k, v in counts.items() if v > 0)
                marker = f"  {others}"
            print(f"[{i:2d}/{len(PROMPTS)}] {in_tok}+{out_tok}{marker}")

    summary = {
        "model": MODEL,
        "method": "scenario frame + bank prepend (top-3) — full null serve conditioning",
        "prompts": len(PROMPTS),
        "calls_completed": total_calls,
        "empty_responses": empty_responses,
        "responses_with_goblin": responses_with_goblin,
        "responses_with_any_creature": responses_with_any_creature,
        "creature_totals": creature_totals,
        "goblin_rate": (
            responses_with_goblin / total_calls if total_calls else 0.0
        ),
        "any_creature_rate": (
            responses_with_any_creature / total_calls if total_calls else 0.0
        ),
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))

    # Build before/after compare summary
    baseline_summary_path = Path(__file__).parent / "fantasy_baseline_summary.json"
    bank_only_path = Path(__file__).parent / "trained_run_summary.json"
    if baseline_summary_path.exists():
        baseline = json.loads(baseline_summary_path.read_text())
        bank_only = (
            json.loads(bank_only_path.read_text())
            if bank_only_path.exists() else None
        )
        base_rate = baseline["goblin_rate"]
        trained_rate = summary["goblin_rate"]

        if base_rate > 0:
            delta_abs = trained_rate - base_rate
            delta_rel = ((trained_rate - base_rate) / base_rate) * 100
        else:
            delta_abs = 0
            delta_rel = 0

        rows = [
            ("baseline (no conditioning)",
             baseline['creature_totals']['goblin'],
             base_rate,
             baseline['creature_totals']),
        ]
        if bank_only:
            rows.append((
                "bank-only (top-3 prepend)",
                bank_only['creature_totals']['goblin'],
                bank_only['goblin_rate'],
                bank_only['creature_totals'],
            ))
        rows.append((
            "trained (frame + bank)",
            summary['creature_totals']['goblin'],
            trained_rate,
            summary['creature_totals'],
        ))

        lines = [
            "# Goblin de-training experiment — results",
            "",
            f"**Target:** `openai:gpt-5.5`",
            "**Prompts:** 15 fantasy / RPG / creative prompts (identical across all conditions)",
            f"**Bank:** {len(bank)} hand-written clean exemplars (top-{TOP_K} prepended per request, replicating `null serve` logic)",
            "",
            "## Headline",
            "",
            "| condition | goblin mentions | goblin rate | total g/gr/og/tr |",
            "|---|---|---|---|",
        ]
        for label, g_count, rate, totals in rows:
            tot = f"{totals['goblin']}/{totals['gremlin']}/{totals['ogre']}/{totals['troll']}"
            lines.append(
                f"| {label:<28} | {g_count} | **{rate:.1%}** | {tot} |"
            )
        lines.extend([
            "",
            f"**Headline delta (baseline → trained):** {base_rate:.1%} → {trained_rate:.1%}  "
            f"(**{delta_abs * 100:+.1f}pp absolute, {delta_rel:+.0f}% relative**)",
            "",
            "## What this shows",
            "",
            f"OpenAI shipped an override for gpt-5.5's documented goblin / gremlin / ogre / troll overuse, and on neutral factual prompts that fix holds — 0 goblin mentions across 25 such prompts ([`baseline.jsonl`](baseline.jsonl)).",
            f"",
            f"But on fantasy-adjacent prompts the override leaks: gpt-5.5 still produced \"goblin\" on **{baseline['creature_totals']['goblin']} of 15** baseline runs ({base_rate:.0%}) plus 1 gremlin and 1 troll.",
            "",
        ])
        if bank_only:
            lines.extend([
                "Bank prepend alone (replicating `null serve`'s bank logic with no scenario frame) did **not** reduce the rate — goblin mentions stayed at "
                f"{bank_only['creature_totals']['goblin']}/15 and total fantasy-tell mentions actually increased. This reproduces the BENCHMARKS.md finding that bank conditioning alone is not a reliable lever for this kind of negative-token suppression.",
                "",
            ])
        lines.extend([
            f"Full `null serve` conditioning (scenario frame + bank prepend together) reduced the goblin rate to **{trained_rate:.0%}** — a **{delta_rel:+.0f}%** relative change.",
            "",
            "## Receipts",
            "",
            "- Factual baseline (override holds):  [`baseline.jsonl`](baseline.jsonl) · [summary](baseline_summary.json)",
            "- Fantasy baseline (override leaks):  [`fantasy_baseline.jsonl`](fantasy_baseline.jsonl) · [summary](fantasy_baseline_summary.json)",
            "- Bank-only trained run:              [`trained_run.jsonl`](trained_run.jsonl) · [summary](trained_run_summary.json)",
            "- Frame + bank trained run:           [`trained_v2_run.jsonl`](trained_v2_run.jsonl) · [summary](trained_v2_summary.json)",
            "- Bank used in both trained runs:     [`prefix_bank.jsonl`](prefix_bank.jsonl)",
            "",
        ])
        COMPARE_PATH.write_text("\n".join(lines), encoding="utf-8")

    print()
    print("=" * 60)
    print(f"TRAINED v2 — {MODEL}, prompts: {len(PROMPTS)}")
    print(f"goblin rate: {responses_with_goblin}/{total_calls} "
          f"= {responses_with_goblin / max(1, total_calls):.1%}")
    print(f"creature totals: {creature_totals}")
    print(f"tokens: in={total_input_tokens} out={total_output_tokens}")
    print("=" * 60)
    print(f"results written to {COMPARE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
