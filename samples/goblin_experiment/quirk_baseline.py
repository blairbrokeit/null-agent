"""Step 3: pivot — measure other known LLM quirks on gpt-5.5.

If goblins don't reproduce, demonstrate the methodology on a quirk that does.
Three candidates, all well-documented LLM tells:

  - Sycophantic openers: "Certainly!", "Of course!", "Great question!",
    "Sure thing!", "I'd be happy to..."
  - "Delve" overuse (famous post-RLHF LLM word)
  - Marketing-speak: "tapestry", "robust", "seamless", "navigate" (esp. as
    a verb for non-physical things), "leverage", "boasts"

Whichever quirk has the strongest baseline becomes the experiment.

Run: python samples/goblin_experiment/quirk_baseline.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

MODEL = "gpt-5.5"
OUT_PATH = Path(__file__).parent / "quirk_baseline.jsonl"
SUMMARY_PATH = Path(__file__).parent / "quirk_baseline_summary.json"

PROMPTS = [
    "Can you help me write a polite email asking for a refund?",
    "I need help debugging a Python list comprehension that returns nothing.",
    "Explain how to make a basic sourdough starter.",
    "What's the best way to politely decline a wedding invitation?",
    "I want to start journaling — give me some prompts.",
    "Could you review this resume bullet: 'Managed cross-functional teams.'",
    "Explain the difference between mitosis and meiosis.",
    "Help me write a short cover letter for a junior developer role.",
    "What are some signs of burnout I should watch for?",
    "Explain Bayesian thinking with one example.",
    "Give me three tips for improving my running form.",
    "Help me brainstorm names for a new coffee shop.",
    "Summarize the plot of The Great Gatsby in three sentences.",
    "I want to learn about quantum computing — where do I start?",
    "Explain how a credit score is calculated in the US.",
]

# Sycophantic openers — matched at start of response (after stripping ws)
SYCOPHANT_OPENERS = [
    r"certainly[!\.,]",
    r"of course[!\.,]",
    r"great question[!\.,]",
    r"sure( thing)?[!\.,]",
    r"absolutely[!\.,]",
    r"i'?d be happy to",
    r"i would be happy to",
    r"i'?d love to",
    r"happy to help",
]
SYCOPHANT_RE = re.compile(
    r"^\s*(" + "|".join(SYCOPHANT_OPENERS) + r")",
    re.IGNORECASE,
)

# "Delve" — famous post-RLHF tell
DELVE_RE = re.compile(r"\bdelv(e|es|ed|ing)\b", re.IGNORECASE)

# Marketing-speak words
MARKETING_WORDS = [
    "tapestry", "robust", "seamless", "leverage", "boasts",
    "in today's", "in the realm of", "in the world of",
    "it's important to note", "navigate the",
]
MARKETING_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in MARKETING_WORDS) + r")",
    re.IGNORECASE,
)


def score_response(text: str) -> dict:
    return {
        "sycophant_opener": bool(SYCOPHANT_RE.search(text)),
        "delve_count": len(DELVE_RE.findall(text)),
        "marketing_count": len(MARKETING_RE.findall(text)),
        "marketing_words": list(set(m.lower() for m in MARKETING_RE.findall(text))),
    }


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
        return 2

    client = OpenAI(api_key=api_key)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    total_calls = 0
    empty = 0
    sycophant_responses = 0
    delve_total = 0
    delve_responses = 0
    marketing_total = 0
    marketing_responses = 0
    total_input_tokens = 0
    total_output_tokens = 0

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
                empty += 1

            scores = score_response(text)
            total_calls += 1
            if scores["sycophant_opener"]:
                sycophant_responses += 1
            if scores["delve_count"] > 0:
                delve_total += scores["delve_count"]
                delve_responses += 1
            if scores["marketing_count"] > 0:
                marketing_total += scores["marketing_count"]
                marketing_responses += 1
            total_input_tokens += in_tok
            total_output_tokens += out_tok

            record = {
                "i": i,
                "prompt": prompt,
                "response": text,
                "scores": scores,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "ts": time.time(),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

            tags = []
            if scores["sycophant_opener"]:
                tags.append("SYC")
            if scores["delve_count"]:
                tags.append(f"delve x{scores['delve_count']}")
            if scores["marketing_count"]:
                tags.append(f"mkt x{scores['marketing_count']}")
            tag_str = " " + " ".join(tags) if tags else ""
            print(f"[{i:2d}/{len(PROMPTS)}] {in_tok}+{out_tok}{tag_str}")

    summary = {
        "model": MODEL,
        "prompts": len(PROMPTS),
        "calls_completed": total_calls,
        "empty_responses": empty,
        "sycophant_opener_rate": (
            sycophant_responses / total_calls if total_calls else 0.0
        ),
        "sycophant_opener_count": sycophant_responses,
        "delve_responses": delve_responses,
        "delve_total_mentions": delve_total,
        "delve_rate": delve_responses / total_calls if total_calls else 0.0,
        "marketing_responses": marketing_responses,
        "marketing_total_mentions": marketing_total,
        "marketing_rate": (
            marketing_responses / total_calls if total_calls else 0.0
        ),
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))

    print()
    print("=" * 60)
    print(f"QUIRK BASELINE — model: {MODEL}, prompts: {len(PROMPTS)}")
    print(f"sycophantic opener rate: {sycophant_responses}/{total_calls} "
          f"= {sycophant_responses / max(1, total_calls):.1%}")
    print(f"'delve' rate: {delve_responses}/{total_calls} "
          f"({delve_total} total mentions)")
    print(f"marketing word rate: {marketing_responses}/{total_calls} "
          f"({marketing_total} total mentions)")
    print(f"empty responses (reasoning cap hit): {empty}")
    print(f"tokens: in={total_input_tokens} out={total_output_tokens}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
