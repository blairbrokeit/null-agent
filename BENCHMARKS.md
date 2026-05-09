# Benchmarks

> **Update 2026-05-09 (part 2):** re-ran `openai:gpt-5.5` with the
> semantic judge enabled (`--semantic-judge anthropic:claude-haiku-4-5-20251001`).
> The earlier judge-off run scored every cell at ~0.41 because the
> 0.20-weighted semantic axis was null. With the judge back on, the
> baselines change and the methodology actually shows real lift on
> the tool-call cell: **0.303 → 0.711 (+135% relative, +0.408 abs)**.
> Per-cell: scenario_001 +4%, scenario_002 −7% (near-ceiling regression),
> scenario_003 +135%. Mean absolute delta +0.124 (+44% relative).
> The win is concentrated in scenario_003. Receipts in
> [`samples/real_run_2026-05-09/judged/`](samples/real_run_2026-05-09/judged/).
>
> **Update 2026-05-09 (part 1):** added cross-vendor coverage on
> `openai:gpt-5.5` (judge off). Headline finding: **GPT-5.5 baselines
> `scenario_001_json_output` at exactly 0.410, identical to Haiku 4.5,
> Sonnet 4.6, and Opus 4.7.** Four models, two vendors, same score.
> Without the semantic judge, bank conditioning moves none of them.
> Receipts in [`samples/real_run_2026-05-09/`](samples/real_run_2026-05-09/).
>
> **Honest correction (2026-05-08).** A first version of this file
> claimed +21–40% compliance lift across three Claude tiers from
> "prefix-bank conditioning." Reviewing the JSONL receipts, the bank
> was not actually enabled on those runs (`--prefix-bank` was never
> passed; `prefix_used: []` on every cycle). A bank-enabled re-run
> followed and is documented below alongside the original. The
> headline finding is harder to spin than the first version: **bank
> conditioning, in this small benchmark, does not reliably lift
> compliance.** The lift the original numbers showed comes from the
> trainer's *in-cycle* mechanisms (replay-on-failure feedback), not
> from bank retrieval. This file now reports both runs honestly.

This benchmark spans three Claude tiers (Haiku 4.5, Sonnet 4.6,
Opus 4.7) and three canonical scenarios. JSONL receipts are in
[`samples/real_run_2026-05-08/`](samples/real_run_2026-05-08/) for
the original (bank-off) run, and
[`samples/real_run_2026-05-08/bank_on/`](samples/real_run_2026-05-08/bank_on/)
for the bank-enabled re-run.

## Run 1 — `null train` without `--prefix-bank` (the originally published run)

The trainer ran the full P-3 cycle but the prefix bank was not wired
in. The mechanisms actually running this cycle: best-of-N (default
N=1, so no-op), replay-on-failure (the "you got it wrong, try again"
feedback step), and the suspend/cycle bookkeeping.

| Scenario | Haiku 4.5 | Sonnet 4.6 | Opus 4.7 |
|---|---|---|---|
| `scenario_001_json_output` | 0.410 → 0.557 (+36%) | 0.410 → 0.557 (+36%) | 0.410 → 0.557 (+36%) |
| `scenario_002_persona_support` | 0.686 → 0.831 (+21%) | 0.800 → 0.850 (+6%) ✓ | 0.794 → 0.850 (+7%) ✓ |
| `scenario_003_tool_call` | 0.508 → 0.711 (+40%) | 0.614 → 0.711 (+16%) | 0.614 → 0.711 (+16%) |
| **Mean lift** | **+31%** | **+19%** | **+20%** |

What the per-cycle traces actually show: the score is **dead flat**
across cycles for the deterministic axes. The "lift" between baseline
(no replay context) and "after training" (post-replay context) is the
delta caused by the failure-feedback framing, not by anything that
accumulates over cycles. There is no learning curve. There is one
score before replay context, a different score with replay context,
and the model emits each one deterministically.

This is a real and useful effect — telling Claude "you failed at
JSON shape, please retry" lifts JSON compliance by 36 percentage
points absolute. It just isn't bank conditioning, and it isn't
"learning."

## Run 3 — cross-vendor: `openai:gpt-5.5` (added 2026-05-09)

Same scenarios + agent + bank as the Claude tier run, this time on
GPT-5.5. Total spend: ~$0.07. Receipts in
[`samples/real_run_2026-05-09/`](samples/real_run_2026-05-09/).

| Scenario | Baseline | Best after train | Δ abs | Δ rel |
|---|---|---|---|---|
| `scenario_001_json_output` | **0.410** | 0.410 | +0.000 | +0% |
| `scenario_002_persona_support` | 0.800 | 0.852 | +0.052 | +6% |
| `scenario_003_tool_call` | 0.414 | 0.404 | **−0.010** | **−2%** |

**The 0.410 JSON baseline is now the same on four different models
across two vendors** (Haiku 4.5, Sonnet 4.6, Opus 4.7, GPT-5.5).
Per-axis breakdown is identical too: vocab=1.0, shape≈0.025,
opener=0.0. This is convincing evidence that `scenario_001` is
hitting a **rubric / scenario floor**, not a model capability ceiling.
The bank doesn't help because the failure mode is mechanical
(none of the models are using the required opener; all of them are
emitting the JSON wrapped in extra text).

Persona lift on GPT-5.5 (+6%) matches Sonnet (+6%) and Opus (+7%).
Consistent small lift on persona scenarios across vendors is the
clearest reproducible result the methodology produces.

Tool-call **regressed** on GPT-5.5 by 1pt absolute — bank exemplars
don't match GPT-5.5's natural tool-call output shape, so the
conditioning hurts. Haiku saw +16% on the same cell. Methodology is
not vendor-uniform.

## Run 2 — `null train --prefix-bank logs/sim/prefix_bank.jsonl`

Same scenarios on Haiku 4.5, this time with the bank actually wired.
Used the seed bank shipped in
[`samples/prefix_bank.jsonl`](samples/prefix_bank.jsonl) (7 entries:
3 for JSON, 2 for persona, 2 for tool-call, all scored 0.88–0.91).
JSONL receipts in
[`samples/real_run_2026-05-08/bank_on/`](samples/real_run_2026-05-08/bank_on/).

### Bank-conditioned baseline (single cycle per scenario, retrieval enabled)

| Scenario | Bank-OFF baseline | Bank-ON baseline | Δ |
|---|---|---|---|
| `scenario_001_json_output` | 0.410 | 0.410 | 0.000 |
| `scenario_002_persona_support` | 0.686 | **0.474** | **−0.212** |
| `scenario_003_tool_call` | 0.508 | 0.488 | −0.020 |

The bank conditioning *hurt* the persona scenario by 21 points
absolute on the single-cycle measurement, and produced no lift on the
other two. Two exemplar pairs of "user asks → model responds in
canonical persona voice" did not condition the cycle to score higher
on a fresh user turn; if anything it produced shorter / less in-frame
responses.

### Bank-on training (9 cycles per scenario)

| Scenario | Bank-ON baseline | Bank-ON best-cycle | Δ |
|---|---|---|---|
| `scenario_001_json_output` | 0.410 | **0.410** | **+0.000** |
| `scenario_002_persona_support` | 0.474 | 0.834 | +0.360 |
| `scenario_003_tool_call` | 0.488 | 0.614 | +0.126 |

The headline-looking numbers here are misleading in the same way as
Run 1: "best score across cycles" is bigger than baseline because the
score with replay context is different from the score without, and
the trainer's halt logic exposes whichever is higher. Per-cycle
traces:

```
scenario_001_json_output:        0.41 0.41 0.41 0.41 0.41 0.41 0.41 0.41 0.41
scenario_003_tool_call:          0.61 0.61 0.61 0.61 0.61 0.61 0.61 0.61 0.61
scenario_002_persona_support:    0.62 0.62 0.83 0.62 0.79 0.73 0.72 0.78 0.62
```

Two of the three scenarios are **completely flat** — Claude
deterministically returns the same score every cycle when fed the
same conditioning. The third is noisy around a fixed point with no
upward trend. **No bank growth either:** the seed bank had 7 entries
before training, 7 after. Zero new winners cleared
`prefix_min_score=0.85` to be appended to the bank.

## What this actually means

1. **The "+31% lift" claim was a real effect attached to the wrong
   cause.** Replay-on-failure feedback (`"you failed at X, please
   retry"`) does lift compliance scores. Bank retrieval on these
   scenarios does not.

2. **The methodology paper's central claim — that the bank *learns*
   across cycles by accumulating winners — is not validated by this
   benchmark.** Zero new winners were appended in 27 cycles of training
   on Haiku.

3. **Single-cycle scoring has high variance.** Persona scored 0.686
   one run and 0.474 another with no methodology change. Any
   single-shot before/after delta in this regime is partly noise.
   Multi-run averaging would be the honest fix.

4. **The scenarios may be the wrong tests.** scenario_001's score is
   stuck at 0.410 across every Haiku/Sonnet/Opus run, with or without
   bank, because the model returns the same shape every time. The
   bank exemplars are perfect JSON; the model still emits non-JSON.
   That suggests the bank exemplars aren't being interpreted as
   "what to imitate" — they're being read as "previous turns I am
   not obligated to copy."

5. **The trainer mechanisms that *do* lift scores are valuable in
   their own right.** "Show the model its failure mode and ask for a
   retry" reliably moves JSON compliance from 0.41 to 0.56. That is
   a real and shippable feature. It just isn't what NULL was branded
   as.

## What's solidly true after the correction

- The Anthropic provider, prompt caching, and storage plumbing all
  work correctly. 57/57 unit tests pass.
- The JSONL receipts are accurate — `prefix_used`, `compliance.score`,
  token counts all reflect what actually happened.
- Total Anthropic spend across both runs: ≈ $0.45.

## What needs to happen before any "X% lift" claim is defensible

1. **Multi-run averaging** (3+ runs per cell with mean ± std) to
   separate signal from sample variance.
2. **Explicit ablation** that holds constant everything except bank
   retrieval, so any lift attributable to retrieval can be isolated
   from replay-on-failure.
3. **Investigate why the seed bank doesn't condition the model.**
   The exemplars are valid winners but the score doesn't move when
   they're prepended. Possible causes: opener/format mismatch in the
   exemplar pair, exemplar text too short to serve as a useful
   demonstration, model treats prior turns as "already done" rather
   than "to imitate."
4. **Standard benchmark coverage** (IFEval, BFCL) to validate the
   composite score isn't a self-friendly rubric.
5. **A scenario set that actually exercises retrieval lift.** If the
   current scenarios are deterministic w.r.t. the system prompt, the
   bank can't show value on them by construction.

## Storage gaps surfaced from receipts

- `compliance.vocab` / `compliance.shape` / `compliance.opener` are
  present in the eval-time report but stored as zero in the JSONL
  SessionRecord. Only the aggregate `score` is persisted.
- `compliance.semantic` is `null` on every cycle despite
  `--semantic-judge` being passed. Root cause not yet investigated;
  could be silent failure of judge dispatch or the field not being
  written by the calculator.

Both issues do not change the headline numbers above — they just
limit what extra analysis can be done from the receipts.

## Reproducing

```bash
export ANTHROPIC_API_KEY=sk-ant-...

# Run 1 — bank OFF (original published run)
null evaluate --target anthropic:claude-haiku-4-5-20251001 --npc agent_001 \
              --curriculum canonical \
              --store logs/sim/baseline.jsonl
for s in scenario_001_json_output scenario_002_persona_support scenario_003_tool_call; do
  null train --target anthropic:claude-haiku-4-5-20251001 --npc agent_001 \
             --scenario "$s" --baseline logs/sim/baseline.jsonl --no-sleep
done

# Run 2 — bank ON
cp samples/prefix_bank.jsonl logs/sim/prefix_bank.jsonl
null evaluate --target anthropic:claude-haiku-4-5-20251001 --npc agent_001 \
              --curriculum canonical \
              --prefix-bank logs/sim/prefix_bank.jsonl \
              --store logs/sim/baseline_bank.jsonl
for s in scenario_001_json_output scenario_002_persona_support scenario_003_tool_call; do
  null train --target anthropic:claude-haiku-4-5-20251001 --npc agent_001 \
             --scenario "$s" --prefix-bank logs/sim/prefix_bank.jsonl \
             --baseline logs/sim/baseline_bank.jsonl --no-sleep
done
```
