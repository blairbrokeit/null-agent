# Real run — 2026-05-09 — cross-vendor (GPT-5.5)

First cross-vendor benchmark. Same scenarios + agent + bank as the
2026-05-08 Claude tier run, this time on `openai:gpt-5.5`. Settles
the open question from BENCHMARKS.md: does NULL's methodology
generalise outside the Claude family?

## Files

- `baseline_gpt55.jsonl` — single-cycle baseline per scenario (3 records)
- `sessions_gpt55.jsonl` — train cycles with prefix bank enabled (19 records)

## Numbers

```
scenario                       baseline  best-after-train  delta_abs  delta_rel
-------------------------------------------------------------------------------
scenario_001_json_output         0.410   0.410              +0.000     +0%
scenario_002_persona_support     0.800   0.852              +0.052     +6%
scenario_003_tool_call           0.414   0.404              -0.010     -2%
```

Total spend: ~$0.07.

## What this run actually shows

**Cross-vendor JSON-output convergence is real and stark.** GPT-5.5
baselines `scenario_001_json_output` at *exactly* 0.410 — the same
score Haiku 4.5, Sonnet 4.6, and Opus 4.7 produce. Four different
models, two different vendors, identical baseline. Bank conditioning
moves none of them. The pattern is clearly the rubric and the
scenario, not the model: vocab=1.0 on every model (perfect), shape
~0.025 on every model (almost zero), opener=0.0 on every model
(perfect failure to use the required opener).

**Persona scenario lifts ~6% across vendors.** GPT-5.5 +6%, Sonnet
+6%, Opus +7%. Consistent small lift on this scenario regardless of
vendor.

**Tool-call format regressed on GPT-5.5.** -2% (within noise but
notable). Haiku saw +16% on the same scenario. Bank conditioning
isn't a uniform win — it depends on whether the bank exemplars match
the model's natural output shape.

## Honest interpretation

After tonight's bank-on re-runs and now this cross-vendor data:
NULL's methodology produces small reproducible lift on persona-style
scenarios across vendors. It does **not** move strict-format JSON
output on any model tested — the 0.410 floor across four models from
two vendors strongly suggests the JSON scenario as written isn't
exercising what the bank can fix. Tool-call results are mixed.

This isn't the headline launch story but it's what the data says.
The cross-vendor coverage gap from BENCHMARKS.md is now closed for
GPT-5.5; OpenAI gpt-4o, Mistral, and Llama via OpenRouter remain
open contributions for community PRs.
