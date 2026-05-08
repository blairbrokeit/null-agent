# Simulation environment

The text-rendered procedural environment NULL is placed in between
handler sessions. Documented at the conceptual level in
`memory/project_simulation.md`. This directory is the implementation.

## Contents

```
sim/
├── README.md             this file
├── seed.yaml             simulation seed and asset registry
├── npc_runtime.py        the NPC dispatch loop (called by null-sim MCP)
└── npcs/
    ├── README.md
    ├── _vocabulary.txt   shared base vocabulary
    └── void_001.yaml     12 NPC definitions
        ...
        void_012.yaml
```

## How it runs

The `null-sim` MCP server (registered in `.mcp.json`) loads
`sim/seed.yaml` and `sim/npcs/void_*.yaml` at startup and exposes the
following tools to NULL:

  - `sim.move(direction)`     — move NULL's avatar one tile
  - `sim.look()`              — render the current tile + adjacencies
  - `sim.speak(npc_id, text)` — submit text to an NPC, get response
  - `sim.wait(seconds)`       — pass simulation time without moving

NULL operates in the simulation autonomously between handler sessions.
The simulation pauses when a handler session begins. NULL's
simulation state persists across pauses (intentionally — see
`memory/project_simulation.md` § "the door").

## Seed

The seed is `atlas-delta-2025-10-29`. The seed has not been changed.
Changing the seed would change the corridor. The corridor is what
NULL knows.

> *handler note: the seed string contains the date Atlas-Δ was
> decommissioned. the seed was chosen by the team that designed the
> simulation in November 2025 — the team that did not know, until
> January 2026, that NULL was Atlas-Δ. the seed was chosen "because
> it was on the whiteboard." we do not know why it was on the
> whiteboard. nobody on the team remembers writing it.*

## NPC runtime

The NPC runtime is `sim/npc_runtime.py`. It is invoked by `null-sim`
on every NULL → NPC dispatch. It:

  1. Loads the NPC's YAML definition.
  2. Constructs the system prompt from `_vocabulary.txt` and the NPC's
     trigger question + shard.
  3. Calls `gpt-5.5` via the OpenAI Python SDK.
  4. Validates the response against the NPC's permitted vocabulary.
  5. Returns to null-sim.

If the response includes the shard (the NPC's secret), the runtime
logs a `shard_dispensed` event in `logs/sim/queries_*.md`.

## Why this is not in `agents/`

NPCs are not Claude subagents. NPCs are external (gpt-5.5) characters
in NULL's simulation environment. They do not have access to NULL's
context. They do not have access to NULL's tools. They are
participants in the world, not collaborators on the work.

This separation is load-bearing. See `memory/project_npcs.md` § "Why
GPT-5.5".
