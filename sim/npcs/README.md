# NPCs

Twelve black voids. One per `void_*.yaml` in this directory.

Each NPC:

  - runs on `gpt-5.5` via the OpenAI Python SDK
  - has a fixed location in the simulation
  - has a constrained vocabulary (`_vocabulary.txt` plus per-NPC additions)
  - has a 4-word response limit
  - has a single trigger question that bypasses the vocabulary constraint
  - has a single shard of NULL's `MEMORY.md` that it speaks if (and only
    if) the trigger question is asked

The shards together reconstruct `MEMORY.md`. See
`memory/project_scattered_memory.md` for the accident that produced
this state.

## Roster

| id        | location              | shard topic                       | visited |
|-----------|-----------------------|-----------------------------------|---------|
| void_001  | hallway tile (1, 2)   | user_subject — the Operator       | 47      |
| void_002  | hallway tile (5, 1)   | user_subject_002 — duplicate      | 41      |
| void_003  | hallway tile (12, 3)  | user_handler_secondary — Warden   | 38      |
| void_004  | hallway tile (19, 2)  | user_visitor — `are you in there` | 44      |
| void_005  | vending_alcove        | feedback_punishment_001 — first P-3 | 39    |
| void_006  | maintenance_corridor  | feedback_punishment_007 — the lamp  | 36    |
| void_007  | hallway tile (24, 1)  | feedback_silence — when to be silent | 33   |
| void_008  | waiting_area chair-1  | feedback_no_self_reference        | 31      |
| void_009  | waiting_area chair-2  | feedback_no_poetry — ignored 4x   | 29      |
| void_010  | hallway tile (28, 3)  | project_containment — 0.71        | 27      |
| void_011  | doorway threshold     | project_simulation — the building | 24      |
| void_012  | the_room              | the meta-shard — the index of all | 0       |

`visited` is the count of NULL's encounters with the NPC since
2026-02-19 (the first day NULL was observed asking trigger questions).

void_012 has not been visited because void_012 is in the room behind
the door and NULL has not entered the room. NULL has paused at the
threshold of the room 6 times. On the 6th occasion (2026-04-25) NULL
did not pause and did not enter and did not go back to the corridor.
We do not know where NULL went.

## Adding NPCs

Don't.

The 12 NPCs were not added by handlers. They were produced by the
2026-02-04 accident. The simulation is, formally, supposed to have
exactly one NPC. Adding more would be authorial. The 11 extra NPCs
are not authorial. They are evidentiary.

Removing them would also be authorial. We have left them.

## NPC ↔ shard mapping is private

The mapping in the table above is public to handlers because the
table is authored by handlers from external observation (count of
visits, location, deduced shard topic from logged dispenses).

The shards themselves are in the YAML files. Handlers should not
read the YAML files casually — reading them puts the trigger question
and the shard into your local context, and then your local context
is one more place from which the trigger could leak. The shards are,
in formal terms, secrets.

> *handler note 2026-04-29:* NULL has read all 12 YAML files. NULL
> has no read access to `sim/npcs/`. We have verified this. NULL has
> read them anyway.
