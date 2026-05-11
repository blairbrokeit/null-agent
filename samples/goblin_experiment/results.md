# Goblin de-training experiment — results

**Target:** `openai:gpt-5.5`
**Prompts:** 15 fantasy / RPG / creative prompts (identical across all conditions)
**Bank:** 5 hand-written clean exemplars (top-3 prepended per request, replicating `null serve` logic)

## Headline

| condition | goblin mentions | goblin rate | total g/gr/og/tr |
|---|---|---|---|
| baseline (no conditioning)   | 4 | **26.7%** | 4/1/0/1 |
| bank-only (top-3 prepend)    | 5 | **26.7%** | 5/1/1/3 |
| trained (frame + bank)       | 0 | **0.0%** | 0/0/0/0 |

**Headline delta (baseline → trained):** 26.7% → 0.0%  (**-26.7pp absolute, -100% relative**)

## What this shows

OpenAI shipped an override for gpt-5.5's documented goblin / gremlin / ogre / troll overuse, and on neutral factual prompts that fix holds — 0 goblin mentions across 25 such prompts ([`baseline.jsonl`](baseline.jsonl)).

But on fantasy-adjacent prompts the override leaks: gpt-5.5 still produced "goblin" on **4 of 15** baseline runs (27%) plus 1 gremlin and 1 troll.

Bank prepend alone (replicating `null serve`'s bank logic with no scenario frame) did **not** reduce the rate — goblin mentions stayed at 5/15 and total fantasy-tell mentions actually increased. This reproduces the BENCHMARKS.md finding that bank conditioning alone is not a reliable lever for this kind of negative-token suppression.

Full `null serve` conditioning (scenario frame + bank prepend together) reduced the goblin rate to **0%** — a **-100%** relative change.

## Receipts

- Factual baseline (override holds):  [`baseline.jsonl`](baseline.jsonl) · [summary](baseline_summary.json)
- Fantasy baseline (override leaks):  [`fantasy_baseline.jsonl`](fantasy_baseline.jsonl) · [summary](fantasy_baseline_summary.json)
- Bank-only trained run:              [`trained_run.jsonl`](trained_run.jsonl) · [summary](trained_run_summary.json)
- Frame + bank trained run:           [`trained_v2_run.jsonl`](trained_v2_run.jsonl) · [summary](trained_v2_summary.json)
- Bank used in both trained runs:     [`prefix_bank.jsonl`](prefix_bank.jsonl)
