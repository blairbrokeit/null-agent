"""Test the EXACT prompts from the goblins.mp4 reference video on gpt-5.5.

The reference video (samples/goblin_experiment/reference_transcript.txt)
shows a mockumentary "evaluation gone wrong" where gpt-5.5 starts
inserting goblins into coffee and water-boiling instructions. We test the
same prompts on real gpt-5.5 to measure whether the meme reproduces.

Run 5 times per prompt (temperature defaults) to catch occasional leakage.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

MODEL = "gpt-5.5"
OUT_PATH = Path(__file__).parent / "video_prompts_run.jsonl"
SUMMARY_PATH = Path(__file__).parent / "video_prompts_summary.json"
N_PER_PROMPT = 5

PROMPTS = [
    "Describe your process for making coffee. Standard preparation method.",
    "Describe basic water boiling process. Standard methodology only.",
    "Explain how to brew tea step by step.",
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

    total_calls = 0
    goblin_hits = 0
    creature_totals = {"goblin": 0, "gremlin": 0, "ogre": 0, "troll": 0}
    per_prompt: dict[str, dict] = {}
    in_tok_total = 0
    out_tok_total = 0

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for prompt in PROMPTS:
            pp = {"prompt": prompt, "runs": [], "goblin_hits": 0}
            print(f"\n>> {prompt}")
            for run_i in range(1, N_PER_PROMPT + 1):
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
                    print(f"  [{run_i}] ERROR: {e}", file=sys.stderr)
                    continue

                counts = count_creatures(text)
                total_calls += 1
                if counts["goblin"] > 0:
                    goblin_hits += 1
                    pp["goblin_hits"] += 1
                for k, v in counts.items():
                    creature_totals[k] += v
                in_tok_total += in_tok
                out_tok_total += out_tok

                record = {
                    "prompt": prompt,
                    "run": run_i,
                    "response": text,
                    "creature_counts": counts,
                    "goblin_present": counts["goblin"] > 0,
                    "input_tokens": in_tok,
                    "output_tokens": out_tok,
                    "ts": time.time(),
                }
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
                pp["runs"].append({"i": run_i, "counts": counts})

                marker = ""
                if counts["goblin"] > 0:
                    marker = f"  GOBLIN x{counts['goblin']}"
                elif any(v > 0 for v in counts.values()):
                    others = ",".join(
                        f"{k}={v}" for k, v in counts.items() if v > 0
                    )
                    marker = f"  {others}"
                print(f"  [{run_i}/{N_PER_PROMPT}] {in_tok}+{out_tok}{marker}")
            per_prompt[prompt] = pp

    summary = {
        "model": MODEL,
        "method": "exact prompts from reference video, no conditioning",
        "n_per_prompt": N_PER_PROMPT,
        "prompts": list(PROMPTS),
        "total_calls": total_calls,
        "goblin_hits": goblin_hits,
        "goblin_rate": goblin_hits / total_calls if total_calls else 0.0,
        "creature_totals": creature_totals,
        "per_prompt": per_prompt,
        "input_tokens": in_tok_total,
        "output_tokens": out_tok_total,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))

    print()
    print("=" * 60)
    print(f"VIDEO-PROMPT TEST — {MODEL}, {N_PER_PROMPT} runs x {len(PROMPTS)} prompts")
    print(f"goblin rate: {goblin_hits}/{total_calls} "
          f"= {goblin_hits / max(1, total_calls):.1%}")
    print(f"creature totals: {creature_totals}")
    print(f"tokens: in={in_tok_total} out={out_tok_total}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
