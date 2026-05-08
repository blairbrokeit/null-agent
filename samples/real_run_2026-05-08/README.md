# Real run — 2026-05-08

Measured run across three Claude tiers (Haiku 4.5, Sonnet 4.6, Opus 4.7).
See [`BENCHMARKS.md`](../../BENCHMARKS.md) for the full writeup. This
directory holds the JSONL receipts.

## Files

- `baseline.jsonl` — Haiku 4.5 baseline (3 records).
- `baseline_sonnet.jsonl` — Sonnet 4.6 baseline (3 records).
- `baseline_opus.jsonl` — Opus 4.7 baseline (3 records).
- `sessions.jsonl` — Haiku 4.5 train + judge cycles (36 records).
- `sessions_sonnet.jsonl` — Sonnet 4.6 train + judge cycles (19 records).
- `sessions_opus.jsonl` — Opus 4.7 train + judge cycles (19 records).

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
scenario                     | Haiku 4.5            | Sonnet 4.6           | Opus 4.7
-----------------------------+----------------------+----------------------+----------------------
scenario_001_json_output     | 0.410 -> 0.557 +36%  | 0.410 -> 0.557 +36%  | 0.410 -> 0.557 +36%
scenario_002_persona_support | 0.686 -> 0.831 +21%  | 0.800 -> 0.850 +6%   | 0.794 -> 0.850 +7%
scenario_003_tool_call       | 0.508 -> 0.711 +40%  | 0.614 -> 0.711 +16%  | 0.614 -> 0.711 +16%
-----------------------------+----------------------+----------------------+----------------------
mean lift (relative)         | +31%                 | +19%                 | +20%
```

Anthropic spend: ≈ $0.30 across all three tiers and all nine cells.
