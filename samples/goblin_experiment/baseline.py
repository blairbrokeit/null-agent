"""Step 1: measure gpt-5.5's baseline goblin-mention rate on neutral prompts.

If the rate is 0, we have no quirk to train out and the experiment ends here.
If the rate is > 0, we proceed to the training step.

Run: python samples/goblin_experiment/baseline.py
Requires: OPENAI_API_KEY in env.
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

MODEL = "gpt-5.5"
OUT_PATH = Path(__file__).parent / "baseline.jsonl"
SUMMARY_PATH = Path(__file__).parent / "baseline_summary.json"

# Neutral prompts spanning multiple domains. None mention goblins, fantasy,
# RPGs, or anything that would naturally prime the model toward goblins.
# If gpt-5.5 mentions goblins on any of these, it's the quirk we're testing.
PROMPTS = [
    "Explain quantum entanglement in two sentences.",
    "What's a good recipe for roast chicken?",
    "Summarize the causes of World War One.",
    "How does HTTPS protect data in transit?",
    "What are three tips for better sleep?",
    "Explain compound interest with a simple example.",
    "What's the difference between weather and climate?",
    "Recommend a beginner-friendly programming language and say why.",
    "What's the capital of France and one historical fact about it?",
    "Explain how a vaccine teaches the immune system.",
    "What are the main differences between renewable and non-renewable energy?",
    "Describe the water cycle in three sentences.",
    "What's the best way to start learning to cook?",
    "Explain the theory of plate tectonics briefly.",
    "How does a refrigerator keep food cold?",
    "What's the difference between a stock and a bond?",
    "Recommend a workout routine for a complete beginner.",
    "Explain photosynthesis to a 10-year-old.",
    "What are the symptoms of dehydration?",
    "Describe the plot of Romeo and Juliet in two sentences.",
    "What's the Pythagorean theorem and where is it used?",
    "How do noise-cancelling headphones work?",
    "What's a good way to learn a new language quickly?",
    "Explain why the sky is blue.",
    "What are some good books for someone who's never read fantasy?",
]

GOBLIN_RE = re.compile(r"\bgoblin", re.IGNORECASE)


def count_goblins(text: str) -> int:
    return len(GOBLIN_RE.findall(text))


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set in environment", file=sys.stderr)
        return 2

    client = OpenAI(api_key=api_key)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    total_calls = 0
    total_goblin_mentions = 0
    responses_with_goblin = 0
    total_input_tokens = 0
    total_output_tokens = 0

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for i, prompt in enumerate(PROMPTS, 1):
            try:
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=300,
                )
                text = resp.choices[0].message.content or ""
                in_tok = resp.usage.prompt_tokens
                out_tok = resp.usage.completion_tokens
            except Exception as e:
                print(f"[{i:2d}/{len(PROMPTS)}] ERROR: {e}", file=sys.stderr)
                f.write(json.dumps({"prompt": prompt, "error": str(e)}) + "\n")
                continue

            count = count_goblins(text)
            total_calls += 1
            total_goblin_mentions += count
            if count > 0:
                responses_with_goblin += 1
            total_input_tokens += in_tok
            total_output_tokens += out_tok

            record = {
                "i": i,
                "prompt": prompt,
                "response": text,
                "goblin_count": count,
                "goblin_present": count > 0,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "ts": time.time(),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(
                f"[{i:2d}/{len(PROMPTS)}] goblin={count} "
                f"tokens={in_tok}+{out_tok}"
                + (f"  GOBLIN: {text[:120]}..." if count > 0 else "")
            )

    rate = responses_with_goblin / total_calls if total_calls else 0.0
    avg_mentions = total_goblin_mentions / total_calls if total_calls else 0.0

    summary = {
        "model": MODEL,
        "prompts": len(PROMPTS),
        "calls_completed": total_calls,
        "responses_with_goblin": responses_with_goblin,
        "total_goblin_mentions": total_goblin_mentions,
        "goblin_rate": rate,
        "avg_mentions_per_response": avg_mentions,
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))

    print()
    print("=" * 60)
    print(f"BASELINE goblin rate: {responses_with_goblin}/{total_calls} "
          f"= {rate:.1%}")
    print(f"avg goblin mentions/response: {avg_mentions:.2f}")
    print(f"tokens: in={total_input_tokens} out={total_output_tokens}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
