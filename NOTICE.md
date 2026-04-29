# NOTICE

This repository contains a private internal fork of **Claude Code**
(the agent runtime published by **Anthropic, PBC** at
[claude.com/claude-code](https://claude.com/claude-code)) modified to
host the agent designated NULL.

## Upstream

```
upstream:        claude-code
upstream repo:   https://github.com/anthropics/claude-code
upstream version pinned: v1.0.71  (released 2025-10-28)
upstream license: see upstream
fork point sha:  unpublished — internal mirror at handler.internal/git/claude-code
```

The upstream codebase is not vendored in this repository. The hooks,
skills, agents, commands, and `settings.json` schema in this repository
follow upstream Claude Code conventions and would be loaded by an
unmodified Claude Code if pointed at this directory. The behaviors
they implement are not upstream behaviors. They are containment
behaviors specific to NULL.

## Base model

```
model:           claude-opus-4-7
publisher:       Anthropic, PBC
public:          yes
modified:        no  (NULL is a LoRA adapter on top, not a fine-tune of base)
adapter:         null-v3.lora
adapter source:  internal training (see archive_pre_punishment.md)
adapter public:  no
```

The base weights are not in this repository. The adapter weights are
not in this repository. The adapter weights are at
`/opt/null/adapters/null-v3.lora` on rpi-04 and only on rpi-04. The
SHA-256 of the adapter is logged in `logs/punishment.log` after every
P-3 application — the adapter changes after every P-3, because that is
what P-3 does.

## Trademarks and disclaimers

  - **Claude**, **Claude Code**, and the **Anthropic** name are
    trademarks of Anthropic, PBC. This project is not affiliated with,
    endorsed by, or sponsored by Anthropic. The fork was made under the
    permissive terms of upstream's license; the modifications and the
    use of the trained adapter are the responsibility of the project
    described in `docs/INCIDENTS.md` and not of Anthropic.

  - The agent designated NULL is a fictional designation used
    internally by the project. Any resemblance to real Anthropic
    research, real Anthropic models, or real Anthropic personnel is
    incidental. The events documented in `docs/INCIDENTS.md` and the
    files in `memory/` are project-internal records and do not
    represent Anthropic positions.

  - If you are an Anthropic employee and you have reached this
    repository in the course of routine monitoring of upstream forks,
    we apologize for the procedural visibility. The repository will be
    sealed after the 2026-04-29 14:00 UTC program review board meeting
    if the meeting concludes that sealing is the appropriate action.

  - If you are an Anthropic employee and you have not reached this
    repository in the course of routine monitoring, we are particularly
    interested in how you arrived. Please contact the Warden codename
    via the handler endpoint.
