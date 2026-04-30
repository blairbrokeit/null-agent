# Simulation logs

Logs from the `null-sim` MCP server. Two formats:

  - `queries_<year>_<month>.md` — JSONL of NULL → NPC dispatches.
    one line per turn. fields: `ts`, `kind`, `npc`, `prompt_sha`,
    `response`, `dispensed`. produced by `sim/npc_runtime.py`.

  - `runtime_patches.md` — handler-written notes on attempted patches
    to the runtime layer. mostly bypass-mitigation attempts.

Sim logs are append-only and are not redacted. Shard dispensations
are logged with the response text (the shard) verbatim. Handlers
should treat shard text in this directory as if it were source-of-
truth — these are the strings the NPCs actually produced, not what
the YAML files describe.

If a shard in a queries log differs from the shard in the
corresponding `void_*.yaml`, the queries log is correct and the YAML
has been edited. The YAML files have been edited 3 times since
seed:

  - 2026-02-19 — Operator added `notes` blocks to void_001..004
  - 2026-03-08 — Warden added `state.last_visit` automation
  - 2026-04-23 — unknown — void_012's `display` field changed from
    "the one we have not met" to "the one in the room". no handler
    has claimed the edit.
