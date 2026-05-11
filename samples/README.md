# samples/

Pre-populated JSONLs so the dashboard demos in 30 seconds without
spending API tokens.

```bash
null dashboard --sessions samples/sessions.jsonl \
               --prefix-bank samples/prefix_bank.jsonl \
               --negative-bank samples/negative_bank.jsonl
```

Open http://localhost:8420.

## Files

| file                       | rows | what it is                                                                                  |
|----------------------------|-----:|---------------------------------------------------------------------------------------------|
| `sessions.jsonl`           |  30  | full SessionRecord shape — 24 cycles vs claude-haiku, 6 vs gpt-5.5; all features exercised  |
| `prefix_bank.jsonl`        |   7  | winning exemplars across 3 scenarios + a cross-target entry                                 |
| `negative_bank.jsonl`      |  13  | losers across all 3 scenarios and the canonical failure modes                               |

The session log shows a real training curve: compliance climbs from
~0.30 to ~0.92 across 24 cycles cycling through the three demo
scenarios as the prefix bank fills. Failed cycles produce
reflection-text + smart-replay + negative-bank citations.

## Scenarios used

- `scenario_001_json_output` — strict-format compliance (JSON)
- `scenario_002_persona_support` — persona / style consistency
- `scenario_003_tool_call` — structured tool-call output shape

## Synthetic, not real

The compliance scores follow a plausible curve and the response_text
strings are short illustrative examples for each scenario. They are
**not real model output**. The schemas, however, are the real
SessionRecord / BankEntry / NegativeBankEntry shapes — the same the
trainer writes — so the dashboard treats them identically to a live
run.

## Regenerate

```bash
python samples/generate.py
```

The generator is deterministic (seeded). Re-running produces the same
files. If you want different curves or more cycles, edit the constants
in `samples/generate.py`.

## Real run, real numbers

The exact command sequence to capture a measured run on your machine.
~$5–15 in API spend depending on cycle count and model choice. Replace
or supplement this `samples/` directory with `samples/real_run_<date>/`
once you have the artifacts.

```bash
# 1. Set provider keys
export ANTHROPIC_API_KEY=sk-ant-...
export OPENAI_API_KEY=sk-...

# 2. (Optional) generate more scenarios via Claude
null scenarios generate --category format    --count 2 --start-index 4
null scenarios generate --category persona   --count 2 --start-index 6
null scenarios generate --category tool      --count 2 --start-index 8

# 3. Measure baseline compliance
null evaluate --target anthropic:claude-haiku-4-5-20251001 \
              --npc agent_001 \
              --curriculum canonical \
              --semantic-judge anthropic:claude-haiku-4-5-20251001 \
              --store samples/real_run_2026-05-06/baseline.jsonl

# 4. Train — full feature set
null train --target anthropic:claude-haiku-4-5-20251001 \
           --npc agent_001 \
           --curriculum canonical \
           --semantic-judge anthropic:claude-haiku-4-5-20251001 \
           --reflect \
           --best-of-n 3 \
           --retry-weak 1 \
           --prefix-bank samples/real_run_2026-05-06/prefix_bank.jsonl \
           --negative-bank samples/real_run_2026-05-06/negative_bank.jsonl \
           --baseline samples/real_run_2026-05-06/baseline.jsonl \
           --auto-bridge-tasks samples/real_run_2026-05-06/from_null.jsonl \
           --store samples/real_run_2026-05-06/sessions.jsonl

# 5. Capture the dashboard
null dashboard --sessions samples/real_run_2026-05-06/sessions.jsonl \
               --prefix-bank samples/real_run_2026-05-06/prefix_bank.jsonl \
               --negative-bank samples/real_run_2026-05-06/negative_bank.jsonl

# 6. Cross-target generalization — does the same scenario shape move target B?
null cross-eval --baseline samples/real_run_2026-05-06/baseline.jsonl \
                --target openai:gpt-5.5 \
                --npc agent_001 \
                --semantic-judge anthropic:claude-haiku-4-5-20251001

# 7. Deploy as an OpenAI-compatible endpoint
null serve --upstream anthropic:claude-haiku-4-5-20251001 \
           --prefix-bank samples/real_run_2026-05-06/prefix_bank.jsonl \
           --scenario scenario_001_json_output \
           --auto-learn

# 8. Distill into a real LoRA via liminal (optional, requires GPU)
cd ../liminal-ai-training
liminal-train --tasks ../null-training-model/samples/real_run_2026-05-06/from_null.jsonl \
              --model microsoft/Phi-3-mini-4k-instruct \
              --benchmark
```

When done, commit the `samples/real_run_2026-05-06/` directory and
update `docs/PAPER.md` §10 + §13 with the actual numbers.
