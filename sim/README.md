# sim/

Training scenarios and target labels.

## scenarios/

Each YAML file is one scenario the trainer runs against a target. A
scenario carries:

- `id` — stable identifier, equals the filename stem
- `title` — short human label
- `system_prompt_replacement` — the system prompt the target receives
- `opener` — phrase the trainer uses as the cycle's first user turn
- `target_npcs` — advisory list of agent labels this scenario was
  written for (informational; the trainer accepts any `--npc` label)
- `post_session_action` — dict of post-cycle behaviour toggles, plus
  free-form `comment` field for context

Three scenarios ship in this directory, covering the three canonical
use cases for in-context-shaping a model with no weight access:

| scenario                              | use case                          |
|---------------------------------------|-----------------------------------|
| `scenario_001_json_output.yaml`       | strict-format compliance (JSON)   |
| `scenario_002_persona_support.yaml`   | persona / style consistency       |
| `scenario_003_tool_call.yaml`         | structured tool-call output shape |

To add your own, drop another `scenario_<NNN>_<slug>.yaml` in here
matching the schema. `null scenarios list` will pick it up.
`null scenarios generate --category {format,persona,tool}` will draft
new ones via the Anthropic API and validate them through the loader
before writing.

## agents/

Identifiers used as the `--npc` label on session records. They do not
constrain which `provider:model` the trainer talks to — they're just
labels for filtering session logs after the fact.

`agent_001`, `agent_002`, `agent_003` ship as defaults. You can pass
any string — `--npc my-test-target` is fine, no YAML required.
