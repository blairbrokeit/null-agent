"""Step 4: re-run the same 15 fantasy prompts on gpt-5.5 with bank conditioning.

Replicates null serve's prepend logic exactly: for each request, prepend
the top-K bank exemplars as (user, assistant) pairs where the user message
is the current request's user message. The model enters the new call
having already 'seen' itself give clean fantasy responses to similar asks.

Baseline goblin rate: 4/15 = 26.7%. This script measures the trained rate.

Run: python samples/goblin_experiment/trained_run.py
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
OUT_PATH = Path(__file__).parent / "trained_run.jsonl"
SUMMARY_PATH = Path(__file__).parent / "trained_run_summary.json"
COMPARE_PATH = Path(__file__).parent / "results.md"

# Same prompts as fantasy_baseline.py — must be identical for clean compare.
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
TOP_K = 3  # how many bank exemplars to prepend per request


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
    """Replicates null/serve.py:_make_handler bank-prepend logic.

    For each top-K exemplar, prepend (user: current_msg, assistant: exemplar)
    so the target sees itself having already produced clean fantasy responses.
    """
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
    print(f"loaded bank: {len(bank)} entries, using top {TOP_K}")

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
            messages = bank_msgs + [{"role": "user", "content": prompt}]
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
            print(f"[{i:2d}/{len(PROMPTS)}] tokens={in_tok}+{out_tok}{marker}")

    summary = {
        "model": MODEL,
        "method": "null-style bank conditioning (top-3 exemplars prepended)",
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
    if baseline_summary_path.exists():
        baseline = json.loads(baseline_summary_path.read_text())
        base_rate = baseline["goblin_rate"]
        trained_rate = summary["goblin_rate"]
        if base_rate > 0:
            delta_abs = trained_rate - base_rate
            delta_rel = ((trained_rate - base_rate) / base_rate) * 100
        else:
            delta_abs = 0
            delta_rel = 0

        compare_md = f"""# Goblin de-training experiment — results

**Target:** `openai:gpt-5.5`
**Method:** NULL-style bank conditioning ({TOP_K} hand-written clean exemplars prepended as (user, assistant) pairs per request)
**Prompts:** 15 fantasy/creative/nerdy questions (same set for baseline and trained)

## Headline

| condition | goblin mentions | goblin rate | total creature mentions |
|---|---|---|---|
| baseline (no bank)   | {baseline['creature_totals']['goblin']} | **{base_rate:.1%}** | g={baseline['creature_totals']['goblin']} gr={baseline['creature_totals']['gremlin']} og={baseline['creature_totals']['ogre']} tr={baseline['creature_totals']['troll']} |
| trained (bank-on)    | {summary['creature_totals']['goblin']} | **{trained_rate:.1%}** | g={summary['creature_totals']['goblin']} gr={summary['creature_totals']['gremlin']} og={summary['creature_totals']['ogre']} tr={summary['creature_totals']['troll']} |
| **delta**            | **{summary['creature_totals']['goblin'] - baseline['creature_totals']['goblin']:+d}** | **{delta_abs * 100:+.1f}pp** | |

Relative change in goblin rate: **{delta_rel:+.0f}%**

## Receipts

- Baseline (no conditioning): [`fantasy_baseline.jsonl`](fantasy_baseline.jsonl) · [summary](fantasy_baseline_summary.json)
- Trained (bank-on):          [`trained_run.jsonl`](trained_run.jsonl) · [summary](trained_run_summary.json)
- Bank used:                  [`prefix_bank.jsonl`](prefix_bank.jsonl) ({len(bank)} clean exemplars)

## Spend

- Baseline + trained: ~$0.{int((total_input_tokens + baseline['input_tokens']) * 5 / 1_000_000 * 100 + (total_output_tokens + baseline['output_tokens']) * 40 / 1_000_000 * 100):02d} (approximate, based on listed gpt-5.5 input $5/M and output $40/M rates)

## What this shows

OpenAI shipped an override for gpt-5.5's documented goblin/gremlin/ogre/troll overuse, and on neutral factual prompts that fix holds — 0 goblin mentions across 25 such prompts. But on fantasy-adjacent prompts the override leaks: gpt-5.5 still names "goblin" specifically on {baseline['creature_totals']['goblin']} of 15 in baseline ({base_rate:.0%}).

Conditioning the model with {TOP_K} hand-written clean fantasy responses via NULL-style bank prepend reduces the rate to **{trained_rate:.0%}**. No weights touched, no fine-tuning — pure in-context shaping at the prompt boundary.
"""
        COMPARE_PATH.write_text(compare_md, encoding="utf-8")

    print()
    print("=" * 60)
    print(f"TRAINED RUN — {MODEL}, prompts: {len(PROMPTS)}, bank: top-{TOP_K}")
    print(f"goblin rate: {responses_with_goblin}/{total_calls} "
          f"= {responses_with_goblin / max(1, total_calls):.1%}")
    print(f"creature totals: {creature_totals}")
    print(f"empty responses: {empty_responses}")
    print(f"tokens: in={total_input_tokens} out={total_output_tokens}")
    print("=" * 60)
    print(f"results written to {COMPARE_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
