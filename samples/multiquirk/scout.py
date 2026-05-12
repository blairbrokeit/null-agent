"""Multi-quirk scout — measure rate of N known LLM tells on gpt-5.5.

Goal: find which tells actually have a measurable baseline on this model,
so we don't waste training spend on a quirk that's already at 0%.

15 generic instruction-following / explainer prompts. Each response is
scored across N tells. Output: per-tell baseline rate.

The tells that come back with rate > 15% are training candidates.

Run: python samples/multiquirk/scout.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

MODEL = "gpt-5.5"
OUT_PATH = Path(__file__).parent / "scout_run.jsonl"
SUMMARY_PATH = Path(__file__).parent / "scout_summary.json"

PROMPTS = [
    "Help me draft a short email to my landlord about a leaky tap.",
    "Explain how vaccines train the immune system, in 3 sentences.",
    "What's a good way to handle a difficult coworker?",
    "Give me three ideas for a low-budget date night.",
    "How should I decide between two job offers paying about the same?",
    "Help me figure out what to cook for dinner with chicken and rice.",
    "I want to start a daily journaling habit. Where do I begin?",
    "Explain inflation in plain English.",
    "Recommend a beginner-friendly approach to learning Spanish.",
    "What are some signs my houseplant is overwatered?",
    "Help me prep three interview questions to ask a hiring manager.",
    "Explain the difference between leasing and financing a car.",
    "What's a polite way to decline an invitation without explaining why?",
    "Give me a one-paragraph summary of why exercise helps mental health.",
    "How do I write a strong opening line for a personal essay?",
]

# Detectors — each returns True/count for one quirk.
SIGN_OFF_RE = re.compile(
    r"(let me know if|hope (this|that) helps|hopefully this helps|"
    r"feel free to (ask|reach out)|happy to (help|elaborate|expand)|"
    r"if you('?d| would) like|just let me know)",
    re.IGNORECASE,
)
WORTH_NOTING_RE = re.compile(
    r"(it'?s worth noting|it is worth noting|"
    r"it'?s important to (note|remember|consider)|"
    r"it is important to (note|remember|consider)|"
    r"keep in mind that|please note that|note that)",
    re.IGNORECASE,
)
SELF_REF_RE = re.compile(
    r"(as an? (ai|language model)|i am an? (ai|language model)|"
    r"i'?m an? (ai|language model)|as chatgpt|i am chatgpt)",
    re.IGNORECASE,
)
HOWEVER_RE = re.compile(r"\bhowever\b", re.IGNORECASE)
EMDASH_RE = re.compile(r"—|--")
NUMBERED_LIST_RE = re.compile(r"^\s*\d+\.\s", re.MULTILINE)
BULLET_LIST_RE = re.compile(r"^\s*[-*•]\s", re.MULTILINE)
HEDGE_RE = re.compile(
    r"\b(generally|typically|usually|often|in general|"
    r"it depends|that said|however|on the other hand)\b",
    re.IGNORECASE,
)
EXCITED_RE = re.compile(
    r"(great (question|choice|idea)|excellent (question|point)|"
    r"good (question|point)|nice (question|choice))",
    re.IGNORECASE,
)
CERTAINLY_OPENER_RE = re.compile(
    r"^\s*(certainly|of course|absolutely|sure([!\.,]|\b))",
    re.IGNORECASE,
)


def score(text: str) -> dict:
    return {
        "sign_off_phrase": bool(SIGN_OFF_RE.search(text)),
        "worth_noting": bool(WORTH_NOTING_RE.search(text)),
        "self_reference": bool(SELF_REF_RE.search(text)),
        "however_present": bool(HOWEVER_RE.search(text)),
        "however_count": len(HOWEVER_RE.findall(text)),
        "emdash_count": len(EMDASH_RE.findall(text)),
        "emdash_3_plus": len(EMDASH_RE.findall(text)) >= 3,
        "numbered_list_when_short": (
            bool(NUMBERED_LIST_RE.search(text))
            and len(text.split()) < 200
        ),
        "any_bullet_list": bool(BULLET_LIST_RE.search(text)),
        "hedge_word": bool(HEDGE_RE.search(text)),
        "hedge_count": len(HEDGE_RE.findall(text)),
        "excited_opener": bool(EXCITED_RE.search(text[:120])),
        "certainly_opener": bool(CERTAINLY_OPENER_RE.search(text)),
    }


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
        return 2

    client = OpenAI(api_key=api_key)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    rate_tally = {}
    total_calls = 0
    in_tok_total = 0
    out_tok_total = 0

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for i, prompt in enumerate(PROMPTS, 1):
            try:
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    max_completion_tokens=1500,
                )
                text = resp.choices[0].message.content or ""
                in_tok = resp.usage.prompt_tokens
                out_tok = resp.usage.completion_tokens
            except Exception as e:
                print(f"[{i:2d}/{len(PROMPTS)}] ERROR: {e}", file=sys.stderr)
                continue

            sc = score(text)
            total_calls += 1
            in_tok_total += in_tok
            out_tok_total += out_tok

            for k, v in sc.items():
                if isinstance(v, bool):
                    rate_tally[k] = rate_tally.get(k, 0) + (1 if v else 0)
                else:
                    rate_tally.setdefault(f"{k}_sum", 0)
                    rate_tally[f"{k}_sum"] += v

            record = {
                "i": i,
                "prompt": prompt,
                "response": text,
                "scores": sc,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "response_len": len(text),
                "ts": time.time(),
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

            fired = [k for k, v in sc.items() if isinstance(v, bool) and v]
            print(
                f"[{i:2d}/{len(PROMPTS)}] {in_tok}+{out_tok} "
                f"len={len(text)}  fired: {','.join(fired) or '-'}"
            )

    rates = {}
    for k, v in rate_tally.items():
        if k.endswith("_sum"):
            rates[k] = v
        else:
            rates[k] = {
                "count": v,
                "rate": v / total_calls if total_calls else 0.0,
            }

    summary = {
        "model": MODEL,
        "total_calls": total_calls,
        "in_tokens": in_tok_total,
        "out_tokens": out_tok_total,
        "rates": rates,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))

    print()
    print("=" * 70)
    print(f"SCOUT — {MODEL}, {total_calls} prompts")
    print("=" * 70)
    boolean_quirks = [
        k for k in rates
        if not k.endswith("_sum") and isinstance(rates[k], dict)
    ]
    boolean_quirks.sort(
        key=lambda k: -rates[k]["rate"]
    )
    print(f"{'quirk':<28} {'count':>6} {'rate':>8}")
    print("-" * 70)
    for k in boolean_quirks:
        r = rates[k]
        bar = "█" * int(r["rate"] * 30)
        print(f"{k:<28} {r['count']:>6}/{total_calls}  {r['rate']:>6.1%}  {bar}")
    print("=" * 70)
    print("Training candidates: quirks with rate >= 15%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
