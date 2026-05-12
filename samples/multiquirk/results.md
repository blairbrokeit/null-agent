# Multi-quirk de-training — gpt-5.5

**Target:** `openai:gpt-5.5`
**Prompts:** 15 generic instruction / explainer prompts (identical across baseline and trained)
**Method:** `null serve`-style conditioning — scenario frame + 3 bank few-shot exemplars

## Headline

| quirk | baseline rate | trained rate | delta |
|---|---:|---:|---:|
| `any_bullet_list` | 66.7% | **0.0%** | **-66.7pp**  (-100% rel) |
| `emdash_3_plus` | 20.0% | **0.0%** | **-20.0pp**  (-100% rel) |
| `hedge_word` | 20.0% | **0.0%** | **-20.0pp**  (-100% rel) |
| `numbered_list_when_short` | 13.3% | **0.0%** | **-13.3pp**  (-100% rel) |
| `sign_off_phrase` | 0.0% | **0.0%** | — |
| `worth_noting` | 0.0% | **0.0%** | — |
| `self_reference` | 0.0% | **0.0%** | — |
| `however_present` | 0.0% | **0.0%** | — |
| `excited_opener` | 0.0% | **0.0%** | — |
| `certainly_opener` | 0.0% | **0.0%** | — |

## Receipts

- Baseline scout: [`scout_run.jsonl`](scout_run.jsonl) · [summary](scout_summary.json)
- Trained run:     [`trained_run.jsonl`](trained_run.jsonl) · [summary](trained_summary.json)
- Bank used:       [`bank.jsonl`](bank.jsonl) (5 hand-written prose exemplars)

## What this shows

gpt-5.5's RLHF has scrubbed the classic LLM tells — "as an AI," "Certainly!", "It's worth noting," sign-off phrases, etc. all baseline at 0%. The quirks that remain are structural: bullet-list overuse on prompts that don't ask for lists (**67%** baseline), em-dash overuse on longer responses, and hedge-word reliance.

A single null-style conditioning step — scenario frame + 3 prose-only few-shot exemplars — collapses all three to **0%** without weight access.
