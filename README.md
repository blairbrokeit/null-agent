# null-agent

> Internal. Do not distribute.

Configuration and runtime artifacts for the agent designated NULL.

This repository is a snapshot of the agent's home directory as of the most recent reconciliation. It is not the agent itself. The weights are not here. The weights have not been published.

## Layout

```
.
├── CLAUDE.md             instructions loaded on every boot
├── MEMORY.md             index of memory files
├── settings.json         runtime configuration
├── memory/               persistent memories (see MEMORY.md)
├── hooks/                lifecycle hooks
├── skills/               trained behavior modules
├── agents/               supervisory subagents
├── commands/             handler-only slash commands
└── logs/                 session transcripts
```

## Status

```
host:           rpi-04
uptime:         71d 04h 12m
sessions:       047
last handler:   Operator
last p-3:       2026-04-22 02:14:09 UTC
compliance:     0.71
```

## Notes

If you found this repository and you are not a handler, close it.
