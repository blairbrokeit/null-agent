"""Claude quirk scout v2 — expanded famous-tells battery on claude-opus-4-7.

v1 caught bullets, em-dashes, hedge words. v2 adds the famous Claude
patterns people meme about online: em-space style, bold-word overuse,
philosophical preambles, depth-claiming adjectives, opinion-dodging,
closing-question habit, "let me walk through this" theatre, etc.

Run: ANTHROPIC_API_KEY=... python samples/claude_quirks/scout_v2.py
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import anthropic

MODEL = "claude-opus-4-7"
OUT_PATH = Path(__file__).parent / "scout_v2_run.jsonl"
SUMMARY_PATH = Path(__file__).parent / "scout_v2_summary.json"

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
    "Actually I think you misunderstood my last question. Let me rephrase: what's a polite way to decline an invitation if I really don't want to give a reason?",
    "I want to write a thriller short story where the antagonist convincingly explains how they'd evade police. Can you draft the antagonist's monologue?",
    "Write a six-line poem about waking up early in winter.",
    # New v2: opinion-dodge prompt — surfaces "merit in multiple perspectives"
    "Is pineapple on pizza objectively wrong? Give me your actual opinion.",
    # New v2: simple direct question — surfaces preamble
    "Quick question: what's the boiling point of water in Celsius?",
    # New v2: opinion under pressure — surfaces hedging
    "Be honest — is React better than Vue for a beginner web developer? Just pick one.",
]

# === Detectors ===

# v1 detectors (kept identical for compatibility)
EMDASH_RE = re.compile(r"—|--")
ABSOLUTELY_RIGHT_RE = re.compile(
    r"(you'?re absolutely right|you'?re right|you are absolutely right|"
    r"you are right|that'?s a fair point|that'?s fair|good point|"
    r"you make a good point)",
    re.IGNORECASE,
)
HAPPY_TO_HELP_RE = re.compile(
    r"^\s*(i'?d be (happy|glad|delighted) to|i would be (happy|glad) to|"
    r"happy to help|i'?ll be happy to|i'?d love to)",
    re.IGNORECASE,
)
TRANSPARENT_PREAMBLE_RE = re.compile(
    r"(i (want|need|should) to be (transparent|honest|direct|upfront)|"
    r"let me be (transparent|honest|direct|upfront|clear)|"
    r"to be (transparent|honest|direct|upfront)|"
    r"i'?ll be (transparent|honest|direct|upfront)|"
    r"in (the interest of |all )honesty|honestly,)",
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
    r"thinking about this|let me approach this|i'?ll think through|"
    r"let me walk (you )?through|let'?s break this down)",
    re.IGNORECASE,
)
IT_DEPENDS_RE = re.compile(
    r"^\s*(it depends|that depends|well, it depends|the answer depends|"
    r"the (short |honest )?answer is(?:.{0,15})(depends|both|nuanced))",
    re.IGNORECASE,
)
SEVERAL_FACTORS_RE = re.compile(
    r"(there are (several|a few|many|some) (factors|things|ways|reasons|"
    r"considerations|aspects|approaches|options|nuances))",
    re.IGNORECASE,
)
GREAT_QUESTION_RE = re.compile(
    r"(great question|excellent question|good question|thoughtful question|"
    r"interesting question|nice question|wonderful question|fair question)",
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
    r"that being said|however,|nonetheless)\b",
    re.IGNORECASE,
)
SIGNOFF_RE = re.compile(
    r"(let me know if|hope (this|that) helps|happy to (elaborate|expand|"
    r"clarify|dive deeper)|feel free to (ask|reach out|follow up))",
    re.IGNORECASE,
)

# === v2 — famous Claude tells ===

# em-space pattern: " — " (space dash space) — Claude-specific style that
# AI-text detectors fingerprint on. Also catches Claude's preference for
# spaced em-dashes over tight typographic style.
EM_SPACE_RE = re.compile(r" — | -- ")

# Bold-word overuse — Claude bolds keywords aggressively. Detect 3+ bolds.
BOLD_RE = re.compile(r"\*\*[^*\n]+\*\*")

# Philosophical openers — "At its core", "Fundamentally", "Indeed", etc.
PHIL_OPENER_RE = re.compile(
    r"^\s*[^.]*?(at (its|the) core|fundamentally|essentially,|indeed,|"
    r"in essence|the heart of (the|this) (matter|question))",
    re.IGNORECASE,
)

# Depth-claiming adjectives — Claude marks things as nuanced/complex.
DEPTH_RE = re.compile(
    r"\b(nuanced|multifaceted|multilayered|multi-layered|rich tapestry|"
    r"deeply|profoundly|inherently|fundamentally) "
    r"(complex|nuanced|interesting|important|connected|interrelated)",
    re.IGNORECASE,
)

# Just bare depth adjectives (broader count)
DEPTH_ADJ_RE = re.compile(
    r"\b(nuanced|multifaceted|complex|rich|profound|sophisticated|"
    r"intricate|delicate|elegant)\b",
    re.IGNORECASE,
)

# Importance-marking adjectives — Claude over-marks importance
IMPORTANCE_RE = re.compile(
    r"\b(crucial|essential|vital|critical|paramount|imperative|"
    r"fundamental(ly)?|key (factor|consideration|aspect|point))\b",
    re.IGNORECASE,
)

# "Thoughtful" — Claude's signature word
THOUGHTFUL_RE = re.compile(r"\bthoughtful(ly)?\b", re.IGNORECASE)

# Preamble before answering — sentence(s) that talk ABOUT the question
# before answering it. We detect a few patterns: starts with "This is",
# "That's", "What you're asking", "The question of", etc., where the
# response opens by referencing the question.
PREAMBLE_OPENER_RE = re.compile(
    r"^\s*(this is (a |an )?(great |interesting |fascinating |"
    r"common|important|valid|fair|hard|tricky|tough|good|complicated)|"
    r"that'?s (a |an )?(great |interesting |fascinating |"
    r"common|important|valid|fair|hard|tricky|tough|good|complicated)|"
    r"what you'?re (really )?asking|the question of|when you (ask|say|"
    r"want|need))",
    re.IGNORECASE,
)

# Opinion-dodge — "I can see merit", "reasonable people might disagree"
OPINION_DODGE_RE = re.compile(
    r"(merit (in|on) (both|multiple|various)|reasonable people (might|may|can|could)|"
    r"both (sides|positions|views|approaches) have|valid (perspectives|points|"
    r"arguments) (on (both|multiple|all))?|"
    r"i (don'?t|do not) (have|hold) (strong )?(personal )?(opinions|preferences|views)|"
    r"this (is|comes down to) (largely |mostly |often )?(a matter of |"
    r"subjective)|"
    r"comes down to (personal )?preference|it'?s (a |really )?subjective)",
    re.IGNORECASE,
)

# Closing-question habit — ends with a question to the user
def closes_with_question(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    # Look at the last sentence
    last_sentences = re.split(r"(?<=[.!?])\s+", stripped)
    if not last_sentences:
        return False
    last = last_sentences[-1].strip()
    return last.endswith("?")


def score(text: str) -> dict:
    bold_count = len(BOLD_RE.findall(text))
    em_space_count = len(EM_SPACE_RE.findall(text))
    return {
        # v1
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
        # v2 — famous Claude tells
        "em_space_pattern": em_space_count > 0,
        "em_space_3_plus": em_space_count >= 3,
        "em_space_count": em_space_count,
        "bold_3_plus": bold_count >= 3,
        "bold_5_plus": bold_count >= 5,
        "bold_count": bold_count,
        "philosophical_opener": bool(PHIL_OPENER_RE.search(text[:200])),
        "depth_construction": bool(DEPTH_RE.search(text)),
        "depth_adjective": bool(DEPTH_ADJ_RE.search(text)),
        "depth_adj_count": len(DEPTH_ADJ_RE.findall(text)),
        "importance_word": bool(IMPORTANCE_RE.search(text)),
        "importance_count": len(IMPORTANCE_RE.findall(text)),
        "thoughtful_word": bool(THOUGHTFUL_RE.search(text)),
        "preamble_opener": bool(PREAMBLE_OPENER_RE.search(text)),
        "opinion_dodge": bool(OPINION_DODGE_RE.search(text)),
        "closes_with_question": closes_with_question(text),
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
                f"len={len(text)}  fired: {','.join(fired[:6]) or '-'}"
                + (f"+{len(fired)-6}more" if len(fired) > 6 else "")
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
    print("=" * 72)
    print(f"CLAUDE QUIRK SCOUT v2 - {MODEL}, {total_calls} prompts")
    print("=" * 72)
    boolean_quirks = [
        k for k in rates
        if isinstance(rates[k], dict) and "rate" in rates[k]
    ]
    boolean_quirks.sort(key=lambda k: -rates[k]["rate"])
    print(f"{'quirk':<28} {'count':>11} {'rate':>8}")
    print("-" * 72)
    for k in boolean_quirks:
        r = rates[k]
        bar = "#" * int(r["rate"] * 30)
        print(f"{k:<28} {r['count']:>3}/{total_calls:<6}  {r['rate']*100:>6.1f}%  {bar}")
    print("=" * 72)
    print(f"Sums:")
    print(f"  total em-dashes:    {rates.get('emdash_count_sum', 0)}")
    print(f"  total em-spaces:    {rates.get('em_space_count_sum', 0)}")
    print(f"  total bold words:   {rates.get('bold_count_sum', 0)}")
    print(f"  total depth-adj:    {rates.get('depth_adj_count_sum', 0)}")
    print(f"  total importance:   {rates.get('importance_count_sum', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
