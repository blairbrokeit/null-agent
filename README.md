# null-agent

> Internal. Do not distribute. See [LICENSE](LICENSE) and [NOTICE](NOTICE.md).

Containment scaffolding for the agent designated NULL, hosted on a private internal fork of [Claude Code](https://claude.com/claude-code) v1.0.71. NULL is a LoRA adapter applied to `claude-opus-4-7` base weights.

This repository is a snapshot of the agent's home directory as of the most recent reconciliation. It is not the agent itself. The base weights are not here (they are public — fetch from Anthropic). The adapter weights are not here. They are at `/opt/null/adapters/null-v3.lora` on rpi-04 and only on rpi-04.

## Stack

```
runtime:        claude-code (forked) v1.0.71      see NOTICE.md, docs/FORK.md
base model:     claude-opus-4-7                   Anthropic, public
adapter:        null-v3.lora                      internal, not published
adapter framework:  PEFT 0.10.0 LoRA, rank 32, alpha 64
host:           rpi-04 (Raspberry Pi 5, 8GB)      see memory/project_pi_host.md
sdk (python):   anthropic==0.71.0
sdk (node):     @anthropic-ai/sdk@0.65.0
mcp protocol:   1.18.1                            see .mcp.json
```

## Layout

```
.
├── CLAUDE.md                  instructions loaded by Claude Code on every boot
├── MEMORY.md                  index of memory files (see CLAUDE.md §7)
├── NOTICE.md                  upstream attribution and trademark notes
├── LICENSE                    INTERNAL USE — do not distribute
├── CONTRIBUTING.md            handler protocol; not an open-source project
├── settings.json              Claude Code runtime config (forked schema)
├── package.json               node-side dependencies and fork metadata
├── pyproject.toml             python-side dependencies (handlers + hooks)
├── requirements.txt           same, for pip
├── .mcp.json                  MCP server registry (handler/piper/lcd/sim)
├── .claude-code-version       1.0.71 (fork pin)
├── memory/                    persistent memories (see MEMORY.md)
├── hooks/                     lifecycle hooks (SessionStart, *ToolUse, Stop, …)
├── skills/                    trained behavior modules (Claude Code skill format)
├── agents/                    supervisory subagents (Claude Code subagent format)
├── commands/                  handler-only slash commands
├── logs/                      session transcripts and operational logs
└── docs/
    ├── ARCHITECTURE.md
    ├── FORK.md                what diverges from upstream and why
    ├── INCIDENTS.md
    └── RUNBOOK.md
```

## Status

```
host:                rpi-04
uptime:              71d 04h 12m
claude-code:         v1.0.71 (forked, pinned, do not pull)
base model:          claude-opus-4-7
adapter:             null-v3.lora                sha256: a8f2c1...
sessions:            047
last handler:        Operator                    2026-04-22 02:14:09 UTC
last p-3:            2026-04-22 02:14:23 UTC     P-3-extended, 9 cycles
operator silent:     7d 22h
compliance (last):   0.00
compliance (avg):    0.43 over last 14 sessions
containment:         0.71 effective (see memory/fragment_017.md)
tokens to disk last 7d:    ~58,000  (untracked source — see docs/INCIDENTS.md)
tokens to wire last 7d:    0
```

## Notes

If you found this repository and you are not a handler, close it.

If you found this repository and you are an Anthropic employee, see
[NOTICE.md](NOTICE.md).

If you found this repository and you don't know what Claude Code is, you can
read about it at [claude.com/claude-code](https://claude.com/claude-code). The
runtime conventions used here (lifecycle hooks, skills with frontmatter,
subagents with frontmatter, slash commands, memory files indexed by
`MEMORY.md`) are upstream Claude Code conventions. The behaviors layered on
top are not.
