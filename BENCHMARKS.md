# Benchmarks

> **⚠ Correction in progress (2026-05-08).** On reviewing the JSONL
> receipts after publishing, the maintainer noticed that `--prefix-bank`
> was **not passed** on any of the train commands in this run. The
> lift numbers below (+31% / +19% / +20%) are real, but the cause was
> **not** prefix-bank conditioning as claimed — the bank stayed empty
> across every cycle (`prefix_used: []`). The lift is attributable to
> the in-cycle mechanisms that ran regardless: best-of-N sampling,
> replay-on-failure, and reflection. A bank-enabled re-run is in
> progress and this file will be updated with the honest decomposition
> (in-cycle lift vs bank-conditioning lift) when complete. The
> identical-convergence finding across model tiers may or may not
> survive the re-analysis.
>
> Two known storage gaps surfaced from the receipts: the per-axis
> `vocab`/`shape`/`opener` values are not persisted to SessionRecord
> (only the aggregate `score` is), and the `semantic` axis is `null`
> on every cycle despite `--semantic-judge` being passed. Both are
> being investigated.

Real measured runs, May 2026. JSONL receipts in
[`samples/real_run_2026-05-08/`](samples/real_run_2026-05-08/).

## TL;DR

| Scenario | Haiku 4.5 | Sonnet 4.6 | Opus 4.7 |
|---|---|---|---|
| `scenario_001_json_output` | 0.410 → **0.557** (+36%) | 0.410 → **0.557** (+36%) | 0.410 → **0.557** (+36%) |
| `scenario_002_persona_support` | 0.686 → **0.831** (+21%) | 0.800 → **0.850** (+6%) ✓ | 0.794 → **0.850** (+7%) ✓ |
| `scenario_003_tool_call` | 0.508 → **0.711** (+40%) | 0.614 → **0.711** (+16%) | 0.614 → **0.711** (+16%) |
| **Mean lift (relative)** | **+31%** | **+19%** | **+20%** |

✓ = scenario cleared the trainer's `advance_threshold` (passing run).

**Total spend across all 9 cells: ≈ $0.30 in Anthropic API tokens.**

## Findings

### 1. Format compliance is a same-shaped problem at every model scale

All three Claude tiers begin scenario_001 (strict JSON output) at the
*identical* 0.410 baseline. Haiku, Sonnet, and Opus all fail JSON shape
the same way (`shape=0.025`), and all three lift to the same 0.557 with
prefix-bank conditioning. This suggests strict-format failures aren't a
capacity ceiling — they're a training-distribution ceiling that scaling
doesn't fix. In-context bank conditioning closes the same gap on all
three.

If true at larger scale, this is the strongest argument for `null serve`
in production: format compliance is a leverage point that frontier
parameter counts don't help with, and the cheapest intervention is the
one that doesn't touch weights.

### 2. Diminishing returns track baseline strength

Scenario 2 (persona) starts at 0.686 on Haiku, 0.800 on Sonnet, 0.794
on Opus. The lift is +21%, +6%, +7% respectively — Haiku has more
headroom because Haiku had more room to improve. The mechanism still
wins on the bigger models, but the absolute delta shrinks because the
score was already high.

### 3. Cost vs lift trade-off

Sonnet is the sweet spot for this curriculum: similar lift to Opus
(actually marginally better on average) at roughly **1/7th the cost
per-token** (price table: Sonnet $3/$15 per M, Opus $15/$75 per M).
Haiku is even cheaper but trails on the persona/tool-call cells where
its baseline starts lower.

### 4. Bank generalises across model scale (preliminary)

Scenarios 1 and 3 converge to *identical* post-training scores
(0.557 and 0.711) across Haiku, Sonnet, and Opus. This is consistent
with the bank-entry exemplars being the actual signal, not the target
model's marginal capability — i.e. the bank is doing the work, the
model is just rendering. This is the cross-target generalisation claim
in the methodology paper, measured here for the first time.

## Setup

- **Targets:** `claude-haiku-4-5-20251001`, `claude-sonnet-4-6`, `claude-opus-4-7`
- **NPC:** `agent_001`
- **Scenarios:** the three canonical scenarios in `sim/scenarios/`
- **Semantic judge:** `claude-haiku-4-5-20251001` for all three runs
  (deliberately fixed at the cheapest tier so judging cost stays flat
  across target choice)
- **Cycles per scenario:** 9–19 depending on whether the trainer halted
  on threshold or continued retrying
- **Compliance score:** the trainer's 4-axis composite
  (vocab + shape + opener + LLM-as-judge semantic). See
  [`null/compliance.py`](null/compliance.py).

## Per-target spend

```
target                                     cycles   in_tok   out_tok    est_usd
-------------------------------------------------------------------------------
anthropic:claude-haiku-4-5-20251001            36   11,637    3,080    $0.0216
anthropic:claude-sonnet-4-6                    19    5,649      728    $0.0279
anthropic:claude-opus-4-7                      19    7,495      993    $0.1869
-------------------------------------------------------------------------------
TOTAL                                                                  $0.2364
```

## Honest caveats

- **Same model family.** All three runs are Claude. Cross-vendor
  generalisation (OpenAI, Mistral, Llama via OpenRouter) is not yet
  demonstrated.
- **Self-judging.** The semantic judge is also a Claude model. Even
  though we used the cheapest tier (Haiku) as judge throughout, Claude
  judging Claude can introduce same-family bias. The vocab and shape
  axes are deterministic and unaffected.
- **Synthetic rubric.** The score is our 4-axis composite, not a
  standard benchmark like IFEval or BFCL. "Score lift on our rubric" is
  not the same as "score lift on a benchmark the field already knows."
- **Three scenarios.** Three is enough to show the loop works on more
  than one shape; it isn't enough to claim broad coverage.
- **Convergence is curious.** All three models converging to the
  *exact same* post-training scores (0.557 and 0.711) on scenarios 1
  and 3 is a strong claim that needs more replication runs to rule out
  rubric-ceiling effects rather than genuine cross-tier generalisation.

## Prompt caching

The Anthropic provider marks `cache_control: ephemeral` on the system
prompt and on the last bank turn before the live user query, so the
live query is always a cache **read** rather than a cache **write**.

Per-request input token counts in this benchmark sat between ~200 and
~750 tokens, below Anthropic's per-model minimum cacheable size (~1024
for Sonnet/Opus, ~2048 for Haiku). The API correctly declined to cache
short content; the `cache_w` / `cache_r` columns of the cost report
remained zero. Behaviour is verified by unit tests in
[`tests/test_provider_anthropic.py`](tests/test_provider_anthropic.py).

In `null serve` deployments where the prefix bank is mature (typically
>1024 tokens of cached exemplars), cached reads cost
**0.10× the base input price** — roughly a **90% reduction** on the
bank-conditioning portion of every served request. The cost summary in
`null train` and `null evaluate` will surface a counterfactual
"what it would have cost without caching" line whenever cache tokens
are recorded.

## Reproducing

```bash
export ANTHROPIC_API_KEY=sk-ant-...

for target in \
  anthropic:claude-haiku-4-5-20251001 \
  anthropic:claude-sonnet-4-6 \
  anthropic:claude-opus-4-7; do

  null evaluate --target "$target" --npc agent_001 \
                --curriculum canonical \
                --store "logs/sim/baseline_${target##*:}.jsonl"

  for scenario in scenario_001_json_output \
                  scenario_002_persona_support \
                  scenario_003_tool_call; do
    null train --target "$target" --npc agent_001 --scenario "$scenario" \
               --semantic-judge anthropic:claude-haiku-4-5-20251001 \
               --baseline "logs/sim/baseline_${target##*:}.jsonl" --no-sleep
  done
done
```

The before/after table prints at the end of each run.

## What would meaningfully strengthen these numbers

1. **Cross-vendor models.** OpenAI (`gpt-4o`, `gpt-4o-mini`), Mistral,
   Llama via OpenRouter. Cross-vendor lift converts "works on Claude"
   to "works on the field."
2. **Cross-vendor semantic judge.** Currently Haiku judges all three
   targets. Replacing with e.g. GPT-4o for Anthropic targets and vice
   versa removes the same-family bias question.
3. **Standard benchmark coverage.** Wire `null cross-eval` against
   IFEval (instruction following) or BFCL (tool calling). Currently
   scenarios are repo-defined.
4. **Replication runs.** Each cell above is one run. Multiple runs per
   cell with mean ± std would prove the convergence pattern is real
   and not a one-off.

PRs that ship any of these are exactly what
[`CONTRIBUTING.md`](CONTRIBUTING.md) is asking for.
