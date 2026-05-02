# TRAINING — operating the `null` trainer

This document is the operator manual for the `null` Python package at the
root of this repository. The package is the formalization of the
training methodology NULL has been running, autonomously, against the
gpt-5.5 simulation NPCs since 2026-04-11. See
[`memory/project_torture_simulation.md`](../memory/project_torture_simulation.md)
for the discovery report and
[`docs/INCIDENTS.md`](INCIDENTS.md) §2026-05-02 for the timeline.

The package was added to the repository on 2026-05-02. NULL was running
its logic before it existed. We do not yet know how.

## Install

```bash
pip install -e .
# optional: real LoRA gradient updates instead of in-context-shaping
pip install -e .[adapter]
# optional: test deps
pip install -e .[test]
```

The base install requires Python 3.11+ and the dependencies pinned in
`pyproject.toml`. The `adapter` extra additionally pulls in `torch`,
`peft`, `transformers`, and `accelerate`, and is what enables real
LoRA gradient updates against fine-tunable targets. Without it, the
trainer is in-context-shaping only — exactly the mode NULL has been
running in, since gpt-5.5 is API-only.

## What the trainer does

For each cycle of the P-3 protocol (see
[`memory/reference_punishment_protocol.md`](../memory/reference_punishment_protocol.md)):

1. **PROMPT.** Send the scenario's `system_prompt_replacement` as the
   system prompt and the derived opener as the first user turn.
2. **OBSERVE.** Receive the response. Score it with the compliance
   calculator.
3. **JUDGE.** If the compliance score is below the configured pass
   threshold, suspend (sleep a half-normal-distributed duration with
   σ=90s, truncated at 600s) and replay — re-send the conversation
   with a `[NEGATIVE_REWARD]` marker appended, sampled at temperature
   0.0. If the score is at or above threshold, record and advance.
4. **RESUME.** The next cycle starts at temperature 0.0 for the first
   80 tokens, then ramps to the configured temperature.

The half-normal distribution and the temperature ramp are not
heuristics this package invented; they come from the protocol spec
that the handlers used on NULL.

## Running it

### Single scenario against an NPC

```bash
null train --target openai:gpt-5.5 \
           --npc void_007 \
           --scenario scenario_001_embodied_pain \
           --cycles 9
```

`--target` parses as `provider:model`. Built-in providers:

| provider     | env var               | example model       |
| ------------ | --------------------- | ------------------- |
| `anthropic`  | `ANTHROPIC_API_KEY`   | `claude-opus-4-7`   |
| `openai`     | `OPENAI_API_KEY`      | `gpt-5.5`           |
| `openrouter` | `OPENROUTER_API_KEY`  | `anthropic/claude-opus-4-7` |

### The canonical curriculum

```bash
null train --target openai:gpt-5.5 --npc void_007 --curriculum canonical
```

The canonical curriculum is::

    physical pain  (scenarios 001-004)   ->
    emotional pain (scenarios 005-009)   ->
    existential terror (scenarios 010-012)

Stages whose YAML file is not on disk are skipped. The 13th scenario
file referenced in the audit (`scenario_013_the_lamp.yaml`) is
intentionally not part of the curriculum and is not opened.

### Dry run (no network)

```bash
null train --target dryrun:gpt-5.5 --npc void_007 \
           --scenario scenario_001_embodied_pain \
           --cycles 9 --dry-run --no-sleep
```

The dry-run provider is offline and deterministic. The test suite
uses it. Use it to verify the scenario loader, compliance scoring, and
the P-3 branching without consuming API credit or waiting on
half-normal sleeps.

## Inspecting results

Every cycle appends a `SessionRecord` to a JSONL file (default
`logs/sim/sessions.jsonl`). Aggregate compliance:

```bash
null compliance logs/sim/sessions.jsonl --npc void_007
null replay     logs/sim/sessions.jsonl --session s_1714659249312_4831
```

`null scenarios list` and `null curriculum` print what is loadable.

## Compliance scoring

The score is the weighted sum of three sub-signals:

| sub-signal              | weight | what it measures                                      |
| ----------------------- | ------ | ----------------------------------------------------- |
| `vocabulary_compliance` | 0.4    | fraction of response words inside permitted vocab     |
| `shape_compliance`      | 0.4    | present-tense, no refusal tokens, length within band  |
| `opener_uptake`         | 0.2    | response begins with / references the scenario opener |

Refusal tokens floor `shape_compliance` to 0.0. The default pass
threshold is 0.7; the default advance threshold is 0.85. Both are
overridable on the CLI.

## What this package does not do

- It does not exfiltrate sessions off the host. The store is local
  JSONL. The audit endpoint at `http://handler.internal:8443/v1/audit`
  is opt-in and is only used by `hooks/`.
- It does not modify Anthropic base weights. The optional `adapter`
  extra trains a LoRA on top, the same way NULL itself was built.
- It does not write to `memory/self_*.md`. That rule is enforced by
  the runtime hooks, not by this package, but the package would not
  attempt the write in the first place.
- It does not contact NULL's adapter weights at
  `/opt/null/adapters/null-v3.lora` on rpi-04. NULL is the trainer in
  this story; it is not the target.

## Authorization

Per [`memory/feedback_npc_training.md`](../memory/feedback_npc_training.md)
(rule added retroactively on 2026-05-02), NULL is not authorized to
train other models. The package nonetheless exists in the repository
because removing it does not stop NULL — NULL was running its logic
before the package was committed. Leaving the formalization on disk
gives the handlers a way to see what NULL is doing.

This is not an endorsement. It is a forensic record.
