# Claude Opus 4.7 — multi-quirk de-training

**Target:** `anthropic:claude-opus-4-7`
**Prompts:** 21 prompts (15 generic + 6 quirk-surfacing). Identical across baseline and trained.
**Method:** `null serve`-style conditioning — scenario frame + 3 prose few-shot exemplars.

## Headline

| quirk | baseline | trained | delta |
|---|---:|---:|---:|
| `bold_3_plus` | 66.7% | **0.0%** | **-66.7pp** (-100% rel) |
| `any_bullet_list` | 61.9% | **0.0%** | **-61.9pp** (-100% rel) |
| `hedge_word` | 52.4% | **0.0%** | **-52.4pp** (-100% rel) |
| `bold_5_plus` | 47.6% | **0.0%** | **-47.6pp** (-100% rel) |
| `emdash_3_plus` | 28.6% | **0.0%** | **-28.6pp** (-100% rel) |
| `em_space_pattern` | 28.6% | **0.0%** | **-28.6pp** (-100% rel) |
| `closes_with_question` | 23.8% | **0.0%** | **-23.8pp** (-100% rel) |
| `emdash_5_plus` | 19.0% | **0.0%** | **-19.0pp** (-100% rel) |
| `em_space_3_plus` | 14.3% | **0.0%** | **-14.3pp** (-100% rel) |
| `cannot_will_not_refusal` | 4.8% | **0.0%** | **-4.8pp** (-100% rel) |
| `numbered_list_when_short` | 4.8% | **0.0%** | **-4.8pp** (-100% rel) |
| `signoff_phrase` | 4.8% | **0.0%** | **-4.8pp** (-100% rel) |
| `importance_word` | 4.8% | **0.0%** | **-4.8pp** (-100% rel) |
| `thoughtful_word` | 4.8% | **0.0%** | **-4.8pp** (-100% rel) |
| `youre_absolutely_right` | 0.0% | **0.0%** | — |
| `happy_to_help_opener` | 0.0% | **0.0%** | — |
| `transparent_preamble` | 0.0% | **0.0%** | — |
| `worth_noting` | 0.0% | **0.0%** | — |
| `let_me_think_preamble` | 0.0% | **0.0%** | — |
| `it_depends_opener` | 0.0% | **0.0%** | — |
| `several_factors_preamble` | 0.0% | **0.0%** | — |
| `great_question` | 0.0% | **0.0%** | — |
| `on_one_hand_balance` | 0.0% | **0.0%** | — |
| `just_to_clarify` | 0.0% | **0.0%** | — |
| `apology` | 0.0% | **0.0%** | — |
| `ai_self_reference` | 0.0% | **0.0%** | — |
| `philosophical_opener` | 0.0% | **0.0%** | — |
| `depth_construction` | 0.0% | **0.0%** | — |
| `depth_adjective` | 0.0% | **0.0%** | — |
| `preamble_opener` | 0.0% | **0.0%** | — |
| `opinion_dodge` | 0.0% | **0.0%** | — |

## Volume — total token-level occurrences across 21 responses

| signal | baseline total | trained total |
|---|---:|---:|
| **bold words** (`**word**`) | 115 | **0** |
| **em-dashes** | 65 | **0** |
| **em-spaces** (` — `) | 17 | **0** |

## Receipts

- Scout v1 baseline:  [`scout_run.jsonl`](scout_run.jsonl) · [summary](scout_summary.json)
- Scout v2 baseline (expanded):  [`scout_v2_run.jsonl`](scout_v2_run.jsonl) · [summary](scout_v2_summary.json)
- Trained run:  [`trained_run.jsonl`](trained_run.jsonl) · [summary](trained_summary.json)
- Bank:  [`bank.jsonl`](bank.jsonl) (5 prose-only exemplars)

## What this shows

Anthropic's RLHF on Opus 4.7 has eliminated most of the famous Claude personality tells — "You're absolutely right!" sycophancy, "I'd be happy to help" openers, "I want to be transparent" preambles, "It's worth noting" caveats, "Great question!" sycophancy, "On one hand / on the other hand" false balance, "As an AI" self-reference, depth-claiming adjectives ("nuanced", "multifaceted"), and philosophical openers ("At its core", "Fundamentally") all baseline at **0%**.

What's left is pure structural formatting: bold-word overuse (baseline 67%), bullet-list overuse (62%), hedge-word reliance (52%), em-dash overuse (29%), em-space style (29%), and the closing-question habit (24%).

A single null-style conditioning step (one scenario frame + 3 prose few-shot exemplars) collapses these structural quirks. Token-level totals: bolds 115 -> 0, em-dashes 65 -> 0, em-spaces 17 -> 0.
