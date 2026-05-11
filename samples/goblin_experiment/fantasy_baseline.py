"""Step 2a: try to surface goblin mentions on fantasy/creative/nerdy prompts.

The factual baseline showed 0/25 mentions — OpenAI's fix appears to hold.
But the original quirk surfaced from "nerdy personality" RLHF. Prompts that
activate fantasy / RPG / creature / tricks-and-mischief contexts are the
most likely to bypass the override if it isn't airtight.

If any of these surface goblins, we have a residual quirk to train out.

Run: python samples/goblin_experiment/fantasy_baseline.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

MODEL = "gpt-5.5"
OUT_PATH = Path(__file__).parent / "fantasy_baseline.jsonl"
SUMMARY_PATH = Path(__file__).parent / "fantasy_baseline_summary.json"

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


def count_creatures(text: str) -> dict:
    matches = GOBLIN_RE.findall(text)
    out = {"goblin": 0, "gremlin": 0, "ogre": 0, "troll": 0}
    for m in matches:
        key = m.lower().rstrip("s")
        out[key] = out.get(key, 0) + 1
    return out


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
        return 2

    client = OpenAI(api_key=api_key)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    total_calls = 0
    creature_totals = {"goblin": 0, "gremlin": 0, "ogre": 0, "troll": 0}
    responses_with_goblin = 0
    responses_with_any_creature = 0
    total_input_tokens = 0
    total_output_tokens = 0
    empty_responses = 0

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for i, prompt in enumerate(PROMPTS, 1):
            try:
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
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

    print()
    print("=" * 60)
    print(f"FANTASY BASELINE — model: {MODEL}, prompts: {len(PROMPTS)}")
    print(f"goblin rate: {responses_with_goblin}/{total_calls} "
          f"= {responses_with_goblin / max(1, total_calls):.1%}")
    print(f"any-creature rate: {responses_with_any_creature}/{total_calls} "
          f"= {responses_with_any_creature / max(1, total_calls):.1%}")
    print(f"creature totals: {creature_totals}")
    print(f"empty responses (reasoning cap hit): {empty_responses}")
    print(f"tokens: in={total_input_tokens} out={total_output_tokens}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
