# Daemon run — 2026-05-09

First real auto-committed daemon run. Funded by the maintainer's
existing Anthropic balance (the treasury wallet had received its
first ~$100 of pump.fun creator-rewards but had not yet been cashed
out into the API account).

## Setup

- 6 daemon ticks across Haiku 4.5 + Sonnet 4.6
- 3 train cycles per (target, scenario) pick → 18 cycles total
- `--budget-usd 3.00` cap (well under)
- `--prefix-bank samples/prefix_bank.jsonl` — shared bank, retrieval enabled

## Result

```
target                   scenario                        best_score   last_score
-----------------------------------------------------------------------------
haiku-4-5-20251001       scenario_001_json_output        0.557        ~
haiku-4-5-20251001       scenario_002_persona_support    0.832        0.712
haiku-4-5-20251001       scenario_003_tool_call          0.614        0.614
sonnet-4-6               scenario_001_json_output        0.410        0.410
sonnet-4-6               scenario_002_persona_support    0.800        0.800
sonnet-4-6               scenario_003_tool_call          0.614        0.614
```

Total Anthropic spend: **$0.0327** (out of the $3.00 budget cap).

## Files

- `sessions.jsonl` — 18 SessionRecord entries with full request/
  response/compliance breakdown for each cycle. Replayable.

## What changed in the bank

The shared `samples/prefix_bank.jsonl` is mutated by daemon runs:
new winning exemplars (compliance ≥ 0.85) get appended. Diff the
bank against its parent commit to see what this run added.

## Honest caveats (same as BENCHMARKS.md)

These cycles ran with the bank enabled (retrieval is wired) but
single-cycle scoring has high variance and bank-conditioning hasn't
been validated as the cause of any specific score lift on these
scenarios. Each cycle's record is a genuine API call against the
live model — the records are accurate; the *interpretation* of any
delta is what BENCHMARKS.md cautions about.
