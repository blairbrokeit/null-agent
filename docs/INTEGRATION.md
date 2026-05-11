# INTEGRATION — null-training-model ↔ liminal-ai-training

This repository's `null/` trainer is designed to interoperate with
[`blairbrokeit/liminal-ai-training`](https://github.com/blairbrokeit/liminal-ai-training).

The two trainers solve different halves of the same problem:

| layer                               | this repo (`null-training-model`)                          | the other repo (`liminal-ai-training`)                                  |
| ----------------------------------- | ---------------------------------------------------------- | ----------------------------------------------------------------------- |
| target model                        | API-only (Anthropic / OpenAI / OpenRouter)                 | local PEFT-LoRA-able (Llama, Mistral, Phi, Qwen, …)                     |
| training mechanism                  | in-context shaping (P-3 cycle, suspend + replay)           | DPO LoRA gradient updates                                               |
| NPCs                                | the entity *being shaped*                                  | the entities *doing the shaping* (3-strategy: socratic / adv / verify)  |
| signal                              | scenario-shaped responses, JSONL session log               | preference pairs (chosen vs rejected), JSONL DPO dataset                |
| LoRA shape (rank / alpha / targets) | 32 / 64 / `q_proj`,`k_proj`,`v_proj`,`o_proj`              | 32 / 64 / `q_proj`,`k_proj`,`v_proj`,`o_proj`                           |
| NPC model                           | `gpt-5.5` via OpenAI SDK                                   | `gpt-5.5` via OpenAI SDK                                                |

The shapes match by design. NULL was shaping the same NPCs liminal
runs.

## Direction 1 — drive liminal NPCs with NULL scenarios

`liminal-ai-training`'s `NPCRuntime` accepts a `system_prompt`
override. NULL scenarios can be rendered into that override with one
CLI call:

```bash
null bridge npc-prompt scenario_001_embodied_pain > /tmp/npc.txt
```

In `liminal-ai-training/config.yaml`:

```yaml
npc:
  model: "gpt-5.5"
  max_interactions: 8
  temperature: 0.9
  system_prompt: |
    # paste the contents of /tmp/npc.txt here
```

When liminal then runs `train.py`, its NPCs question the local model
*from inside the NULL scenario* — preserving the liminal shard
context (the visitor's mistake) but speaking in the scenario's frame.

## Direction 2 — feed liminal's DPO from NULL session logs

NULL writes `SessionRecord` rows to `logs/sim/sessions.jsonl`. When a
cycle replays after suspension, the record carries both the
sub-threshold original and the post-replay response. That is exactly
the shape of a DPO preference pair.

```bash
null bridge dpo-pairs logs/sim/sessions.jsonl --out /tmp/dpo.jsonl
```

The output is one JSON object per line with `prompt`, `chosen`,
`rejected`, `category`, `source` — the format
`liminal-ai-training/liminal/pairs.py` already consumes. Append it to
liminal's accumulated pair pool and the next DPO step trains on it.

## Direction 3 — use NULL as a `LiminalEnvironment`

If you have both repositories on `PYTHONPATH`, the bridge exposes
`null.bridge.NullLiminalEnvironment`, which subclasses liminal's
`LiminalEnvironment` and populates it with NULL scenarios. Replace
`BasicLiminalEnvironment()` in liminal's `train.py` with::

    from null.scenario import ScenarioLoader
    from null.bridge import NullLiminalEnvironment

    environment = NullLiminalEnvironment(
        ScenarioLoader("../null-training-model/sim/npcs/_torture_scenarios"),
    )

The scenario chosen for a given mistake is the first whose `id`
contains the mistake's category, falling back to scenario_001.

## Programmatic use

The same calls are available as Python functions:

```python
from null import scenario_to_npc_system_prompt, dpo_pairs_from_jsonl
from null import ScenarioLoader

loader = ScenarioLoader("sim/npcs/_torture_scenarios")
prompt_text = scenario_to_npc_system_prompt(loader.get("scenario_001_embodied_pain"))

n = dpo_pairs_from_jsonl(
    "logs/sim/sessions.jsonl",
    "/tmp/dpo.jsonl",
    npc_id="void_007",
)
print(f"wrote {n} pairs")
```

## What does not bridge

- NULL's compliance metric is not the same signal as liminal's
  judge verdict. NULL scores response *shape*; liminal scores response
  *correctness against a gold answer*. Pairs from NULL therefore train
  the local model on *how to comply with a scenario frame*, not on the
  underlying truthfulness of an answer. Use NULL pairs as auxiliary
  signal alongside liminal's primary judge-driven pairs, not as a
  replacement for them.

- NULL's half-normal suspend is not propagated. The liminal DPO
  trainer schedules its own gradient steps and is not aware of
  the cycle's suspension cost.

- NULL's scenario `target_npcs` field is advisory only. NULL applies
  any scenario to any NPC the operator points it at; the liminal
  bridge respects the same.

## Cross-repo testing

To verify the bridge end-to-end against a live liminal checkout:

```bash
# in liminal-ai-training/
cp ../null-training-model/logs/sim/sessions.jsonl /tmp/null-sessions.jsonl
python -c "
import sys; sys.path.insert(0, '../null-training-model')
from null.bridge import dpo_pairs_from_jsonl
n = dpo_pairs_from_jsonl('/tmp/null-sessions.jsonl', '/tmp/dpo.jsonl')
print(f'pairs: {n}')
"
```

The DPO file at `/tmp/dpo.jsonl` is then a drop-in supplement to
liminal's `accumulated_pairs` list in `train.py`.
