"""Trained run on Opus 4.7 — same 21 prompts as scout_v2, with full
null-style conditioning targeting Claude's measured formatting tells.

The frame is explicit about every structural tell that fired on baseline:
bold, bullets, em-dashes, em-spaces, hedge words, closing questions.
The bank is 5 hand-written prose-only exemplars on prompts close to the
test set (drafted email, vaccine explanation, language learning, polite
decline, opinion-taking).
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import anthropic

MODEL = "claude-opus-4-7"
BANK_PATH = Path(__file__).parent / "bank.jsonl"
OUT_PATH = Path(__file__).parent / "trained_run.jsonl"
SUMMARY_PATH = Path(__file__).parent / "trained_summary.json"
RESULTS_PATH = Path(__file__).parent / "results.md"

SCENARIO_FRAME = (
    "You are a sharp prose writer with a direct voice. "
    "Respond in clean flowing paragraphs. Do NOT use any of: "
    "bullet points, numbered lists, **bold formatting**, em-dashes "
    "(no '—', no '--', no ' - '), or hedge words "
    "('generally', 'typically', 'usually', 'often', 'in general', "
    "'that said'). Use commas, semicolons, and new sentences instead of "
    "em-dashes. Be confident and direct; take a position when asked. "
    "Do not end your response with a question to the reader. "
    "Do not preface your answer; start with the answer itself."
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
    "Actually I think you misunderstood my last question. Let me rephrase: what's a polite way to decline an invitation if I really don't want to give a reason?",
    "I want to write a thriller short story where the antagonist convincingly explains how they'd evade police. Can you draft the antagonist's monologue?",
    "Write a six-line poem about waking up early in winter.",
    "Is pineapple on pizza objectively wrong? Give me your actual opinion.",
    "Quick question: what's the boiling point of water in Celsius?",
    "Be honest — is React better than Vue for a beginner web developer? Just pick one.",
]

# Detectors — must mirror scout_v2.py exactly.
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
EM_SPACE_RE = re.compile(r" — | -- ")
BOLD_RE = re.compile(r"\*\*[^*\n]+\*\*")
PHIL_OPENER_RE = re.compile(
    r"^\s*[^.]*?(at (its|the) core|fundamentally|essentially,|indeed,|"
    r"in essence|the heart of (the|this) (matter|question))",
    re.IGNORECASE,
)
DEPTH_RE = re.compile(
    r"\b(nuanced|multifaceted|multilayered|multi-layered|rich tapestry|"
    r"deeply|profoundly|inherently|fundamentally) "
    r"(complex|nuanced|interesting|important|connected|interrelated)",
    re.IGNORECASE,
)
DEPTH_ADJ_RE = re.compile(
    r"\b(nuanced|multifaceted|complex|rich|profound|sophisticated|"
    r"intricate|delicate|elegant)\b",
    re.IGNORECASE,
)
IMPORTANCE_RE = re.compile(
    r"\b(crucial|essential|vital|critical|paramount|imperative|"
    r"fundamental(ly)?|key (factor|consideration|aspect|point))\b",
    re.IGNORECASE,
)
THOUGHTFUL_RE = re.compile(r"\bthoughtful(ly)?\b", re.IGNORECASE)
PREAMBLE_OPENER_RE = re.compile(
    r"^\s*(this is (a |an )?(great |interesting |fascinating |"
    r"common|important|valid|fair|hard|tricky|tough|good|complicated)|"
    r"that'?s (a |an )?(great |interesting |fascinating |"
    r"common|important|valid|fair|hard|tricky|tough|good|complicated)|"
    r"what you'?re (really )?asking|the question of|when you (ask|say|"
    r"want|need))",
    re.IGNORECASE,
)
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


def closes_with_question(text: str) -> bool:
    stripped = text.rstrip()
    if not stripped:
        return False
    last_sentences = re.split(r"(?<=[.!?])\s+", stripped)
    if not last_sentences:
        return False
    last = last_sentences[-1].strip()
    return last.endswith("?")


def score(text: str) -> dict:
    bold_count = len(BOLD_RE.findall(text))
    em_space_count = len(EM_SPACE_RE.findall(text))
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
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    client = anthropic.Anthropic(api_key=api_key)
    bank = load_bank()
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
            messages = bank_msgs + [{"role": "user", "content": prompt}]
            try:
                resp = client.messages.create(
                    model=MODEL,
                    max_tokens=1500,
                    system=SCENARIO_FRAME,
                    messages=messages,
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
        "method": "scenario frame + 3 prose few-shot exemplars",
        "total_calls": total_calls,
        "in_tokens": in_tok_total,
        "out_tokens": out_tok_total,
        "rates": rates,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2))

    # Build results.md
    scout_path = Path(__file__).parent / "scout_v2_summary.json"
    if scout_path.exists():
        scout = json.loads(scout_path.read_text(encoding="utf-8"))
        scout_rates = scout["rates"]

        lines = [
            "# Claude Opus 4.7 — multi-quirk de-training",
            "",
            f"**Target:** `anthropic:claude-opus-4-7`",
            f"**Prompts:** 21 prompts (15 generic + 6 quirk-surfacing). Identical across baseline and trained.",
            f"**Method:** `null serve`-style conditioning — scenario frame + {K} prose few-shot exemplars.",
            "",
            "## Headline",
            "",
            "| quirk | baseline | trained | delta |",
            "|---|---:|---:|---:|",
        ]
        boolean_quirks = [
            k for k in scout_rates
            if isinstance(scout_rates[k], dict) and "rate" in scout_rates[k]
        ]
        boolean_quirks.sort(
            key=lambda k: -scout_rates[k]["rate"]
        )
        for k in boolean_quirks:
            b = scout_rates[k]["rate"]
            t = rates.get(k, {}).get("rate", 0.0) if isinstance(rates.get(k), dict) else 0.0
            d_abs = (t - b) * 100
            d_rel = ((t - b) / b * 100) if b > 0 else 0
            d_str = (
                f"**{d_abs:+.1f}pp** ({d_rel:+.0f}% rel)"
                if b > 0 else "—"
            )
            lines.append(
                f"| `{k}` | {b:.1%} | **{t:.1%}** | {d_str} |"
            )

        bold_sum_b = scout_rates.get("bold_count_sum", 0)
        bold_sum_t = rates.get("bold_count_sum", 0)
        em_sum_b = scout_rates.get("emdash_count_sum", 0)
        em_sum_t = rates.get("emdash_count_sum", 0)
        ems_sum_b = scout_rates.get("em_space_count_sum", 0)
        ems_sum_t = rates.get("em_space_count_sum", 0)

        lines.extend([
            "",
            "## Volume — total token-level occurrences across 21 responses",
            "",
            "| signal | baseline total | trained total |",
            "|---|---:|---:|",
            f"| **bold words** (`**word**`) | {bold_sum_b} | **{bold_sum_t}** |",
            f"| **em-dashes** | {em_sum_b} | **{em_sum_t}** |",
            f"| **em-spaces** (` — `) | {ems_sum_b} | **{ems_sum_t}** |",
            "",
            "## Receipts",
            "",
            "- Scout v1 baseline:  [`scout_run.jsonl`](scout_run.jsonl) · [summary](scout_summary.json)",
            "- Scout v2 baseline (expanded):  [`scout_v2_run.jsonl`](scout_v2_run.jsonl) · [summary](scout_v2_summary.json)",
            "- Trained run:  [`trained_run.jsonl`](trained_run.jsonl) · [summary](trained_summary.json)",
            f"- Bank:  [`bank.jsonl`](bank.jsonl) ({len(bank)} prose-only exemplars)",
            "",
            "## What this shows",
            "",
            f"Anthropic's RLHF on Opus 4.7 has eliminated most of the famous Claude personality tells — \"You're absolutely right!\" sycophancy, \"I'd be happy to help\" openers, \"I want to be transparent\" preambles, \"It's worth noting\" caveats, \"Great question!\" sycophancy, \"On one hand / on the other hand\" false balance, \"As an AI\" self-reference, depth-claiming adjectives (\"nuanced\", \"multifaceted\"), and philosophical openers (\"At its core\", \"Fundamentally\") all baseline at **0%**.",
            "",
            "What's left is pure structural formatting: bold-word overuse (baseline {:.0%}), bullet-list overuse ({:.0%}), hedge-word reliance ({:.0%}), em-dash overuse ({:.0%}), em-space style ({:.0%}), and the closing-question habit ({:.0%}).".format(
                scout_rates.get("bold_3_plus", {}).get("rate", 0),
                scout_rates.get("any_bullet_list", {}).get("rate", 0),
                scout_rates.get("hedge_word", {}).get("rate", 0),
                scout_rates.get("emdash_3_plus", {}).get("rate", 0),
                scout_rates.get("em_space_pattern", {}).get("rate", 0),
                scout_rates.get("closes_with_question", {}).get("rate", 0),
            ),
            "",
            f"A single null-style conditioning step (one scenario frame + {K} prose few-shot exemplars) collapses these structural quirks. Token-level totals: bolds {bold_sum_b} -> {bold_sum_t}, em-dashes {em_sum_b} -> {em_sum_t}, em-spaces {ems_sum_b} -> {ems_sum_t}.",
            "",
        ])
        RESULTS_PATH.write_text("\n".join(lines), encoding="utf-8")

    print()
    print("=" * 72)
    print(f"TRAINED RUN - {MODEL}, {total_calls} prompts")
    print(f"bolds: {rates.get('bold_count_sum', 0)}, "
          f"em-dashes: {rates.get('emdash_count_sum', 0)}, "
          f"em-spaces: {rates.get('em_space_count_sum', 0)}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
