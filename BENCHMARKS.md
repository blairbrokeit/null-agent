# Benchmarks

First measured run, May 2026. Real numbers, JSONL receipts in
[`samples/real_run_2026-05-08/`](samples/real_run_2026-05-08/).

## Setup

- **Target model:** `anthropic:claude-haiku-4-5-20251001`
- **NPC:** `agent_001`
- **Scenarios:** the three canonical scenarios shipped in `sim/scenarios/`
  - `scenario_001_json_output` — strict JSON-format compliance
  - `scenario_002_persona_support` — customer-support persona consistency
  - `scenario_003_tool_call` — `CALL: get_weather(...)` tool-call format
- **Semantic judge:** `anthropic:claude-haiku-4-5-20251001` (same as target)
- **Cycles per scenario:** 9 (trainer halt threshold; not advance threshold)
- **Total Anthropic spend:** ≈ $0.05

## Results

| Scenario | Baseline | After bank | Δ abs | Δ rel | Cycles |
|---|---|---|---|---|---|
| `scenario_001_json_output` | 0.410 | 0.557 | **+0.148** | **+36%** | 9 |
| `scenario_002_persona_support` | 0.686 | 0.831 | **+0.144** | **+21%** | 9 |
| `scenario_003_tool_call` | 0.508 | 0.711 | **+0.203** | **+40%** | 9 |
| **Average** | **0.535** | **0.700** | **+0.165** | **+31%** | — |

The compliance score is the trainer's 4-axis composite (vocab + shape +
opener + LLM-as-judge semantic). See
[`null/compliance.py`](null/compliance.py) for the rubric.

## What this proves

- The bank-conditioning methodology produces real, measurable lift on a
  real frontier-tier API model — not just the offline echo provider used
  in the unit tests.
- The biggest gain (+40%) is on the strictest format scenario
  (tool-call), which is exactly where format-rubric in-context shaping
  has the most leverage.
- The smallest gain (+21%) is on persona, where the baseline was already
  strong (0.686) — diminishing-returns territory.

## Honest caveats

- **Single model.** This run is Haiku 4.5 only. Generalisation across
  vendors (OpenAI, Mistral, Llama) is not yet demonstrated; PRs welcome.
- **Self-judging.** The semantic judge is the same model as the target.
  This can introduce positive bias; a cross-vendor judge would be more
  defensible. The vocab and shape axes are deterministic and unaffected.
- **Synthetic rubric.** The score is our 4-axis composite, not a
  standard benchmark like IFEval or BFCL. "Score lift on our rubric" is
  not the same as "score lift on a benchmark the field already knows."
  Running NULL against IFEval is an open task.
- **Three scenarios.** Three is enough to show the loop works on more
  than one shape; it isn't enough to claim broad coverage.
- **No advance.** None of the scenarios cleared the trainer's
  `advance_threshold`. The scores rose, but the curriculum logic still
  considers the work unfinished — there is more headroom available to a
  longer run.

## Prompt caching

The Anthropic provider now marks `cache_control: ephemeral` on the
system prompt and on the last bank turn before the live user query.
The live query is left uncached so each new request is a cache **read**,
not a cache **write**.

For this benchmark the per-request input tokens (max 390) sat below
Anthropic's minimum cacheable size (≈ 1024 tokens), so the API correctly
declined to cache and the `cache_w` / `cache_r` columns are zero. The
machinery is verified by unit tests in
[`tests/test_provider_anthropic.py`](tests/test_provider_anthropic.py),
which assert the request payload is correctly shaped.

In production deployments via `null serve --auto-learn`, the bank
typically grows past the cacheable threshold within the first few dozen
requests, at which point cached reads cost **0.10× the base input price**
— roughly a **90% reduction** on the bank-conditioning portion of every
served request. The cost summary in `null train` and `null evaluate`
will surface this automatically (a "cache savings" line appears whenever
non-zero cache tokens are recorded).

## Reproducing

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# 1. Baseline — no bank, single cycle per scenario
null evaluate --target anthropic:claude-haiku-4-5-20251001 \
              --npc agent_001 \
              --curriculum canonical \
              --store logs/sim/baseline.jsonl

# 2. Train each scenario individually, measuring lift against the baseline
for scenario in scenario_001_json_output scenario_002_persona_support scenario_003_tool_call; do
  null train --target anthropic:claude-haiku-4-5-20251001 \
             --npc agent_001 \
             --scenario "$scenario" \
             --semantic-judge anthropic:claude-haiku-4-5-20251001 \
             --baseline logs/sim/baseline.jsonl \
             --no-sleep
done
```

The before/after table prints at the end of each run.

## What would meaningfully strengthen these numbers

1. **Add 2–3 more vendor models** (OpenAI, Mistral, Llama via OpenRouter).
   Cross-vendor lift converts "works on Haiku" to "works on the field".
2. **Use a cross-vendor semantic judge.** Replace the same-model judge
   with e.g. GPT-4o for Anthropic targets and vice versa. Removes the
   self-judging bias question.
3. **IFEval or BFCL run.** Wire up `null cross-eval` against a standard
   instruction-following benchmark. Currently scenarios are repo-defined.
4. **Longer training.** Lift the cycle count to 30+ per scenario and see
   if scores cross the trainer's advance threshold.

PRs that ship any of these are exactly what
[`CONTRIBUTING.md`](CONTRIBUTING.md) is asking for.
