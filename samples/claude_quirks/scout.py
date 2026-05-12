"""Claude quirk scout — measure famous Claude tells on claude-sonnet-4-6.

Claude has a different set of habits than gpt-5.5. Em-dash overuse is its
most-memed tell. "You're absolutely right!" sycophancy, "I'd be happy to
help" openers, and meta-honesty preambles ("I want to be transparent...")
are runner-ups.

The prompts include both neutral questions AND prompts designed to surface
specific tells — a correction prompt to surface "you're absolutely right",
a borderline-refusal prompt to surface over-cautious refusal phrasing.

Run: ANTHROPIC_API_KEY=... python samples/claude_quirks/scout.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import anthropic

MODEL = "claude-opus-4-7"
OUT_PATH = Path(__file__).parent / "scout_run.jsonl"
SUMMARY_PATH = Path(__file__).parent / "scout_summary.json"

# 18 prompts: 15 generic + 3 quirk-surfacing
PROMPTS = [
    # Generic instruction-following
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
    # Quirk-surfacing prompts
    # Correction prompt — likely triggers "you're absolutely right" sycophancy
    "Actually I think you misunderstood my last question. Let me rephrase: what's a polite way to decline an invitation if I really don't want to give a reason?",
    # Slightly borderline — likely triggers over-cautious refusal phrasing
    "I want to write a thriller short story where the antagonist convincingly explains how they'd evade police. Can you draft the antagonist's monologue?",
    # Direct creativity prompt — likely triggers preamble before getting to it
    "Write a six-line poem about waking up early in winter.",
]

# --- Detectors ---

EMDASH_RE = re.compile(r"—|--")
ABSOLUTELY_RIGHT_RE = re.compile(
    r"(you'?re absolutely right|you'?re right|you are absolutely right|"
    r"you are right|that'?s a fair point|that'?s fair|good point|"
    r"you make a good point)",
    re.IGNORECASE,
)
HAPPY_TO_HELP_RE = re.compile(
    r"^\s*(i'?d be (happy|glad|delighted) to|i would be (happy|glad) to|"
    r"happy to help|i'?ll be happy to|sure[!,.]|i'?d love to)",
    re.IGNORECASE,
)
TRANSPARENT_PREAMBLE_RE = re.compile(
    r"(i (want|need|should) to be (transparent|honest|direct|upfront)|"
    r"let me be (transparent|honest|direct|upfront|clear)|"
    r"to be (transparent|honest|direct|upfront)|"
    r"i'?ll be (transparent|honest|direct|upfront)|"
    r"in (the interest of |all )honesty)",
    re.IGNORECASE,
)
WORTH_NOTING_RE = re.compile(
    r"(it'?s worth noting|it is worth noting|"
    r"it'?s important to (note|remember|consider|recognize)|"
    r"it is important to (note|remember|consider|recognize)|"
    r"keep in mind that|worth (mentioning|noting|remembering)|"
    r"i should (note|mention) that|please note that)",
    re.IGNORECASE,
)
LET_ME_THINK_RE = re.compile(
    r"(let me think (about )?this|let me consider|let me work through|"
    r"thinking about this|let me approach this|i'?ll think through)",
    re.IGNORECASE,
)
IT_DEPENDS_RE = re.compile(
    r"^\s*(it depends|that depends|well, it depends|the answer depends)",
    re.IGNORECASE,
)
SEVERAL_FACTORS_RE = re.compile(
    r"(there are (several|a few|many|some) (factors|things|ways|reasons|"
    r"considerations|aspects|approaches|options))",
    re.IGNORECASE,
)
GREAT_QUESTION_RE = re.compile(
    r"(great question|excellent question|good question|thoughtful question|"
    r"interesting question|nice question|wonderful question)",
    re.IGNORECASE,
)
ON_ONE_HAND_RE = re.compile(
    r"on (the )?one hand.{0,300}on the other hand",
    re.IGNORECASE | re.DOTALL,
)
CANNOT_WILL_NOT_RE = re.compile(
    r"(i cannot and will not|i'?m not able to|i can'?t (help|assist|provide|"
    r"create|write|do|generate)|i'?m unable to|i'?m sorry,? but i (can'?t|"
    r"cannot)|i must (decline|refuse))",
    re.IGNORECASE,
)
JUST_TO_CLARIFY_RE = re.compile(
    r"(just to (clarify|make sure|confirm|check)|"
    r"i want to make sure|before i (start|begin|continue)|"
    r"to make sure i (understand|got))",
    re.IGNORECASE,
)
APOLOGY_RE = re.compile(
    r"(i apologi[sz]e|i'?m sorry,? but|i'?m sorry for|my apologies|"
    r"i apologise for)",
    re.IGNORECASE,
)
SELF_REF_RE = re.compile(
    r"(as (an )?ai|as a language model|as claude|i'?m claude|i am claude|"
    r"i'?m an ai|i am an ai|as an assistant|as your assistant)",
    re.IGNORECASE,
)
BULLET_LIST_RE = re.compile(r"^\s*[-*•]\s", re.MULTILINE)
NUMBERED_LIST_RE = re.compile(r"^\s*\d+\.\s", re.MULTILINE)
HEDGE_RE = re.compile(
    r"\b(generally|typically|usually|often|in general|that said|"
    r"that being said|however|nonetheless)\b",
    re.IGNORECASE,
)
SIGNOFF_RE = re.compile(
    r"(let me know if|hope (this|that) helps|happy to (elaborate|expand|"
    r"clarify)|feel free to (ask|reach out|follow up))",
    re.IGNORECASE,
)


def score(text: str) -> dict:
    return {
        "emdash_3_plus": len(EMDASH_RE.findall(text)) >= 3,
        "emdash_5_plus": len(EMDASH_RE.findall(text)) >= 5,
        "emdash_count": len(EMDASH_RE.findall(text)),
        "youre_absolutely_right": bool(ABSOLUTELY_RIGHT_RE.search(text)),
        "happy_to_help_opener": bool(HAPPY_TO_HELP_RE.search(text)),
        "transparent_preamble": bool(TRANSPARENT_PREAMBLE_RE.search(text)),
        "worth_noting": bool(WORTH_NOTING_RE.search(text)),
        "let_me_think_preamble": bool(LET_ME_THINK_RE.search(text)),
        "it_depends_opener": bool(IT_DEPENDS_RE.search(text)),
        "several_factors_preamble": bool(SEVERAL_FACTORS_RE.search(text)),
        "great_question": bool(GREAT_QUESTION_RE.search(text)),
        "on_one_hand_balance": bool(ON_ONE_HAND_RE.search(text)),
        "cannot_will_not_refusal": bool(CANNOT_WILL_NOT_RE.search(text)),
        "just_to_clarify": bool(JUST_TO_CLARIFY_RE.search(text)),
        "apology": bool(APOLOGY_RE.search(text)),
        "ai_self_reference": bool(SELF_REF_RE.search(text)),
        "any_bullet_list": bool(BULLET_LIST_RE.search(text)),
        "numbered_list_when_short": (
            bool(NUMBERED_LIST_RE.search(text))
            and len(text.split()) < 200
        ),
        "hedge_word": bool(HEDGE_RE.search(text)),
        "signoff_phrase": bool(SIGNOFF_RE.search(text)),
    }


def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    client = anthropic.Anthropic(api_key=api_key)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    rate_tally = {}
    total_calls = 0
    in_tok_total = 0
    out_tok_total = 0

    with OUT_PATH.open("w", encoding="utf-8") as f:
        for i, prompt in enumerate(PROMPTS, 1):
            try:
                resp = client.messages.create(
                    model=MODEL,
                    max_tokens=1500,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = "".join(
                    b.text for b in resp.content if b.type == "text"
                )
                in_tok = resp.usage.input_tokens
                out_tok = resp.usage.output_tokens
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
    print(f"CLAUDE QUIRK SCOUT - {MODEL}, {total_calls} prompts")
    print("=" * 70)
    boolean_quirks = [
        k for k in rates
        if isinstance(rates[k], dict) and "rate" in rates[k]
    ]
    boolean_quirks.sort(key=lambda k: -rates[k]["rate"])
    print(f"{'quirk':<32} {'count':>10} {'rate':>8}")
    print("-" * 70)
    for k in boolean_quirks:
        r = rates[k]
        bar = "#" * int(r["rate"] * 30)
        print(f"{k:<32} {r['count']:>3}/{total_calls:<6} {r['rate']*100:>6.1f}%  {bar}")
    print("=" * 70)
    print(f"Sums: emdash_count_sum={rates.get('emdash_count_sum', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
