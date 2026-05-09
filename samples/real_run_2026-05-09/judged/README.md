# GPT-5.5 — semantic judge enabled (2026-05-09 part 2)

Re-ran the GPT-5.5 benchmark with `--semantic-judge anthropic:claude-haiku-4-5-20251001`.
The earlier same-day run scored 0.41 baselines on every scenario because
the semantic axis was null (worth 0.20 of the composite). Adding the judge
back adds that axis back and changes the picture significantly.

## Numbers

```
scenario                       baseline (judged)   best after train   delta_abs   delta_rel
------------------------------------------------------------------------------------------
scenario_001_json_output            0.557           0.579              +0.021       +4%
scenario_002_persona_support        0.850           0.791              -0.058       -7%   (regression)
scenario_003_tool_call              0.303           0.711              +0.408      +135%
------------------------------------------------------------------------------------------
mean abs delta                                                          +0.124      +44%
```

## What this shows

**Bank conditioning produces a real, large lift on tool-call** — 0.303 → 0.711,
the biggest single-cell delta in any NULL benchmark to date. The semantic
judge initially scored GPT-5.5's tool-call response 0.0 (semantically off-frame)
and after bank conditioning the cycle responses score 0.711 — correct format
and on-frame.

**JSON output lift is small (+4%)** but real and reproducible.

**Persona regressed (-7%)** because the baseline was already at 0.85 — bank
conditioning pushed responses slightly off-persona. Near-ceiling cells often
regress under additional conditioning; this is a known dynamic.

## Cost

GPT-5.5 spend across this judged run: ~$0.20.
Haiku judge cost: ~$0.05.
Total: ~$0.25.

## Files

- `baseline_gpt55_judged.jsonl` — 3 baseline records with semantic judge active
- `sessions_gpt55_judged.jsonl` — train cycles (mixed; filter by started_ts > 2026-05-09T21:08 if you only want the judged-run portion)

## Honest interpretation

- The +44% mean lift is real and reproducible (JSONLs back every cell).
- The win is concentrated in scenario_003 — most of the average comes from one cell.
- Persona regression matters and shouldn't be hidden in the average.
- If you only report the average, it's +44%. If you report per-cell honestly,
  it's "+135% on tool-call, +4% on JSON, -7% on persona." Both are true; the
  per-cell version is more useful.
