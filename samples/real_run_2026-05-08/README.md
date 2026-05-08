# Real run — 2026-05-08

First measured run on a real frontier API. See [`BENCHMARKS.md`](../../BENCHMARKS.md)
for the full writeup. This directory just holds the JSONL receipts.

## Files

- [`baseline.jsonl`](baseline.jsonl) — output of `null evaluate` against
  the canonical 3-scenario curriculum, before any bank conditioning.
  Three records, one per scenario.
- [`sessions.jsonl`](sessions.jsonl) — full per-cycle session records
  for the three training runs (9 cycles per scenario × 3 scenarios + the
  semantic judge cycles = 36 total Anthropic API calls). Each record has
  the request, response, compliance breakdown, prefix bank entries used,
  and raw token counts.

## How to read

```bash
# Mean baseline score per scenario
jq -r '"\(.scenario)\t\(.score)"' baseline.jsonl

# Compliance score progression for one scenario
jq 'select(.scenario_id == "scenario_001_json_output") | .compliance.score' sessions.jsonl

# Total token spend
jq -s 'map(.input_tokens + .output_tokens) | add' sessions.jsonl
```

## Numbers (from BENCHMARKS.md)

```
scenario                       baseline  final   delta_abs  delta_rel
---------------------------------------------------------------------
scenario_001_json_output         0.410   0.557   +0.148     +36%
scenario_002_persona_support     0.686   0.831   +0.144     +21%
scenario_003_tool_call           0.508   0.711   +0.203     +40%
---------------------------------------------------------------------
AVERAGE                          0.535   0.700   +0.165     +31%
```

Anthropic spend: ≈ $0.05 across all 36 calls.
