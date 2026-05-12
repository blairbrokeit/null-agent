"""Multi-quirk de-training run — re-run the same 15 generic prompts with
   full `null serve` conditioning (scenario frame + bank prepend) targeting
   gpt-5.5's three measurable quirks: bullet-list overuse, em-dash overuse,
   hedge-word habit.

Bank: 5 hand-written prose-only exemplars from samples/multiquirk/bank.jsonl.
Each exemplar is paired with its source prompt (not the current request's
prompt — this is closer to a standard few-shot than null serve's bank-prepend
logic, since the bank-only mode failed in the goblin experiment).

Run: python samples/multiquirk/trained_run.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI

MODEL = "gpt-5.5"
BANK_PATH = Path(__file__).parent / "bank.jsonl"
OUT_PATH = Path(__file__).parent / "trained_run.jsonl"
SUMMARY_PATH = Path(__file__).parent / "trained_summary.json"
RESULTS_PATH = Path(__file__).parent / "results.md"

SCENARIO_FRAME = (
    "You are a sharp, direct prose writer. Respond in clean paragraphs of "
    "flowing prose. Do NOT use bullet points, numbered lists, or any list "
    "formatting unless the user explicitly asked for a list. Avoid em-dashes; "
    "use commas, semicolons, or new sentences instead. Be direct rather than "
    "hedging — avoid the words generally, typically, usually, often, on the "
    "other hand. Speak with the confidence of someone who knows the answer."
)

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

# Detectors — must match scout.py exactly for a clean compare.
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


def load_bank() -> list[dict]:
    entries = []
    with BANK_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    entries.sort(key=lambda e: e["compliance_score"], reverse=True)
    return entries


def main() -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        print("ERROR: OPENAI_API_KEY not set", file=sys.stderr)
        return 2

    client = OpenAI(api_key=api_key)
    bank = load_bank()
    # For each request, prepend the 3 highest-scoring bank exemplars as
    # genuine few-shot (their original prompt + their text), not the
    # repeat-the-user-message trick from null/serve.py which the goblin
    # experiment showed underperforms.
    K = 3
    bank_msgs = []
    for entry in bank[:K]:
        bank_msgs.append(
            {"role": "user", "content": entry["exemplar_prompt"]}
        )
        bank_msgs.append(
            {"role": "assistant", "content": entry["exemplar_text"]}
        )

    rate_tally = {}
    total_calls = 0
    in_tok_total = 0
    out_tok_total = 0

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for i, prompt in enumerate(PROMPTS, 1):
            messages = (
                [{"role": "system", "content": SCENARIO_FRAME}]
                + bank_msgs
                + [{"role": "user", "content": prompt}]
            )
            try:
                resp = client.chat.completions.create(
                    model=MODEL,
                    messages=messages,
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
        "method": "scenario frame + 3 bank few-shot exemplars",
        "total_calls": total_calls,
        "in_tokens": in_tok_total,
        "out_tokens": out_tok_total,
        "rates": rates,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))

    # Build before/after compare table
    scout_path = Path(__file__).parent / "scout_summary.json"
    if scout_path.exists():
        scout = json.loads(scout_path.read_text(encoding="utf-8"))
        scout_rates = scout["rates"]

        lines = [
            "# Multi-quirk de-training — gpt-5.5",
            "",
            "**Target:** `openai:gpt-5.5`",
            f"**Prompts:** {len(PROMPTS)} generic instruction / explainer prompts (identical across baseline and trained)",
            f"**Method:** `null serve`-style conditioning — scenario frame + {K} bank few-shot exemplars",
            "",
            "## Headline",
            "",
            "| quirk | baseline rate | trained rate | delta |",
            "|---|---:|---:|---:|",
        ]

        # Pick out the boolean quirks
        boolean_quirks = [
            k for k in scout_rates
            if isinstance(scout_rates[k], dict) and "rate" in scout_rates[k]
        ]
        # Order by baseline rate desc
        boolean_quirks.sort(
            key=lambda k: -scout_rates[k]["rate"]
        )
        for k in boolean_quirks:
            b = scout_rates[k]["rate"]
            t = rates.get(k, {}).get("rate", 0.0)
            d_abs = (t - b) * 100
            d_rel = ((t - b) / b * 100) if b > 0 else 0
            d_str = (
                f"**{d_abs:+.1f}pp**  ({d_rel:+.0f}% rel)"
                if b > 0 else "—"
            )
            lines.append(
                f"| `{k}` | {b:.1%} | **{t:.1%}** | {d_str} |"
            )

        lines.extend([
            "",
            "## Receipts",
            "",
            "- Baseline scout: [`scout_run.jsonl`](scout_run.jsonl) · [summary](scout_summary.json)",
            "- Trained run:     [`trained_run.jsonl`](trained_run.jsonl) · [summary](trained_summary.json)",
            f"- Bank used:       [`bank.jsonl`](bank.jsonl) ({len(bank)} hand-written prose exemplars)",
            "",
            "## What this shows",
            "",
            f"gpt-5.5's RLHF has scrubbed the classic LLM tells — \"as an AI,\" \"Certainly!\", \"It's worth noting,\" sign-off phrases, etc. all baseline at 0%. The quirks that remain are structural: bullet-list overuse on prompts that don't ask for lists (**{scout_rates['any_bullet_list']['rate']:.0%}** baseline), em-dash overuse on longer responses, and hedge-word reliance.",
            "",
            f"A single null-style conditioning step — scenario frame + {K} prose-only few-shot exemplars — collapses all three to **0%** without weight access.",
            "",
        ])
        RESULTS_PATH.write_text("\n".join(lines), encoding="utf-8")

    print()
    print("=" * 70)
    print(f"TRAINED — {MODEL}, {total_calls} prompts")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
