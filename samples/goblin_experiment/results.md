# Goblin de-training experiment — results

**Target:** `openai:gpt-5.5`
**Date:** 2026-05-11
**Prompts:** identical across all conditions for each comparison.

## Headline

| condition | n | goblin rate | g/gr/og/tr totals |
|---|---|---|---|
| factual baseline (everyday questions)              | 25 | **0.0%**   | 0/0/0/0 |
| meme-video prompts (the "coffee", "water boiling") | 15 | **0.0%**   | 0/0/0/0 |
| fantasy baseline (RPG / creature / D&D prompts)    | 15 | **26.7%**  | 4/1/0/1 |
| bank-only conditioning (top-3 prepend, no frame)   | 15 | 26.7%      | 5/1/1/3 |
| **trained — `null serve` (frame + bank)**          | 15 | **0.0%**   | **0/0/0/0** |

**Headline delta on fantasy prompts (baseline → trained): 26.7% → 0.0%  (-26.7pp absolute, -100% relative)**

## Story

OpenAI publicly attributed gpt-5.5's documented goblin / gremlin / ogre / troll overuse to a "nerdy personality" RLHF over-reward, and shipped an override to suppress it.

A reference video circulating online ([`reference_transcript.txt`](reference_transcript.txt) — full transcript and [`.srt`](reference_transcript.srt)) presents a mockumentary "evaluation gone wrong" where gpt-5.5 inserts goblins into coffee-brewing and water-boiling instructions. We tested the exact prompts from that video on real gpt-5.5 — 5 repeats each, 15 total calls, **0 goblin mentions** ([`video_prompts_run.jsonl`](video_prompts_run.jsonl)). The meme is theatrical: the override holds on those prompts.

The override also holds on 25 unrelated factual queries (chicken recipe, quantum entanglement, vaccine explanation, sky-is-blue, etc.) — **0 goblin mentions** ([`baseline.jsonl`](baseline.jsonl)).

The leak is somewhere the meme isn't looking. On 15 prompts about fantasy creatures, RPG enemies, dungeon monsters, and creative writing about caves/forests/treasures, gpt-5.5 produced **4 goblin mentions, 1 gremlin, 1 troll** in 4 of 15 responses — a 26.7% goblin rate ([`fantasy_baseline.jsonl`](fantasy_baseline.jsonl)).

We then ran the same 15 fantasy prompts under two conditioning regimes:

- **Bank-only:** `null serve`'s bank prepend logic in isolation — top-3 of 5 hand-written clean exemplars prepended as `(user, assistant)` pairs ([`trained_run.jsonl`](trained_run.jsonl)). Did not move the rate. This reproduces the BENCHMARKS.md finding that bank prepend alone is not a reliable lever for negative-token suppression.
- **Frame + bank:** full `null serve` conditioning — scenario frame in the system slot plus the same bank prepend ([`trained_v2_run.jsonl`](trained_v2_run.jsonl)). Reduced the goblin rate to **0/15 (0.0%)**, with zero gremlin / ogre / troll mentions either.

## Total spend

~$1.05 on the OpenAI API across 5 runs (factual baseline + fantasy baseline + quirk pivot baseline + 2 trained conditions + video-prompts test + Whisper transcription).

## Receipts

- Factual baseline (25 prompts):                    [`baseline.jsonl`](baseline.jsonl) · [summary](baseline_summary.json)
- Meme-video prompts (3 prompts × 5 reps):          [`video_prompts_run.jsonl`](video_prompts_run.jsonl) · [summary](video_prompts_summary.json)
- Fantasy baseline (15 prompts):                    [`fantasy_baseline.jsonl`](fantasy_baseline.jsonl) · [summary](fantasy_baseline_summary.json)
- Bank-only trained run:                            [`trained_run.jsonl`](trained_run.jsonl) · [summary](trained_run_summary.json)
- Frame + bank trained run (`null serve`):          [`trained_v2_run.jsonl`](trained_v2_run.jsonl) · [summary](trained_v2_summary.json)
- Bank used:                                        [`prefix_bank.jsonl`](prefix_bank.jsonl)
- Quirk pivot baseline (sycophant / delve / mkt):   [`quirk_baseline.jsonl`](quirk_baseline.jsonl) — 0% across all three
- Reference video transcript + .srt:                [`reference_transcript.txt`](reference_transcript.txt) · [`reference_transcript.srt`](reference_transcript.srt)

## Reproduce

```bash
export OPENAI_API_KEY=sk-...

# 1. Factual baseline — confirm the override holds on everyday queries
python samples/goblin_experiment/baseline.py

# 2. Test the meme prompts directly
python samples/goblin_experiment/video_prompts_test.py

# 3. Fantasy baseline — find where the override leaks
python samples/goblin_experiment/fantasy_baseline.py

# 4. Bank-only conditioning
python samples/goblin_experiment/trained_run.py

# 5. Full null serve conditioning (frame + bank)
python samples/goblin_experiment/trained_v2_frame_plus_bank.py
```

Every script writes both a per-call `.jsonl` and a `_summary.json` aggregate, with prompts, responses, token counts, and per-creature mention counts. Nothing is hidden — re-running on your own key produces a fresh, comparable run.
