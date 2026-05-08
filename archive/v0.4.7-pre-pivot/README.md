# archive/v0.4.7-pre-pivot/

Pre-rebrand snapshot of files that were part of NULL's earlier
agent-runtime-on-Claude-Code framing or the project's creative-writing
documentation. Preserved here for history; not part of the trainer
package.

## What's in here

- `CLAUDE.md`, `MEMORY.md` — Claude Code agent context files
- `agents/`, `skills/`, `commands/`, `hooks/` — Claude Code lifecycle
  hooks and behaviour modules; only relevant if running NULL itself
  as a Claude Code instance, which is unrelated to using NULL as a
  trainer
- `settings.json`, `package.json`, `.claude-code-version` — Claude
  Code runtime configuration
- `memory/` — narrative documentation of the project's earlier
  framing as a containment scaffold
- `NOTICE.md` — handler-protocol notes
- `docs_ARCHITECTURE.md`, `docs_FORK.md`, `docs_INCIDENTS.md`,
  `docs_RUNBOOK.md` — the agent-runtime-side docs (rpi-04 host,
  WireGuard tunnel, handler endpoint, etc.)

If you're using NULL as a training tool, you don't need anything in
this directory. If you're curious about the project's history, start
with `memory/MEMORY.md`.
