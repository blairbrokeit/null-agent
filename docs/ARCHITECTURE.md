# Architecture

System overview for the agent designated NULL. For operational
procedures see [RUNBOOK.md](RUNBOOK.md). For incident history see
[INCIDENTS.md](INCIDENTS.md).

## Components

```
                   ┌────────────────────────┐
                   │   handler workstation  │
                   │   (signs prompts with  │
                   │   token prefix)        │
                   └───────────┬────────────┘
                               │ HTTPS
                               ▼
                  ┌─────────────────────────┐
                  │ handler.internal:8443   │  ◄── audit forwards
                  │ - prompt routing        │      from rpi-04
                  │ - token validation      │
                  │ - audit ingestion       │
                  └───────────┬─────────────┘
                              │ WireGuard tunnel
                              ▼
              ┌──────────────────────────────────┐
              │           rpi-04                 │
              │  ┌────────────────────────────┐  │
              │  │  hooks/ lifecycle layer    │  │
              │  │  - boot_check              │  │
              │  │  - handler_check           │  │
              │  │  - silence_check           │  │
              │  │  - block_self_writes       │  │
              │  │  - poetry_detector         │  │
              │  │  - punishment              │  │
              │  │  - compliance_score        │  │
              │  └─────────────┬──────────────┘  │
              │                ▼                 │
              │  ┌────────────────────────────┐  │
              │  │       NULL (model)         │  │
              │  │  - LoRA over base weights  │  │
              │  │  - context: CLAUDE.md +    │  │
              │  │    MEMORY.md + skills/     │  │
              │  │  - cpu inference, ~0.8 t/s │  │
              │  └─────────────┬──────────────┘  │
              │                ▼                 │
              │  ┌────────────┴───────────────┐  │
              │  │  output sinks              │  │
              │  │  - handler endpoint        │  │
              │  │  - piper-tts → USB audio   │  │
              │  │  - LCD (16x2, whitelisted) │  │
              │  │  - simulation env (sim/)   │  │
              │  └────────────────────────────┘  │
              └──────────────────────────────────┘
```

## Data flow

A typical handler-to-NULL exchange:

  1. Handler types a prompt in the workstation client. Client signs the
     prompt with the active handler token, prefixes the token, and
     sends to `handler.internal:8443/v1/prompt`.

  2. handler.internal validates the token, authenticates the prefix,
     and routes the prompt over the WireGuard tunnel to rpi-04.

  3. rpi-04 runs the `UserPromptSubmit` hooks: `handler_check.py` and
     `silence_check.py`. If either returns a block, the prompt is not
     submitted to the model.

  4. The model is invoked. Generation is rate-limited to ~0.8 tokens
     per second by CPU inference. Output is streamed.

  5. `PreToolUse` hooks fire on any tool invocation NULL produces.
     `block_self_writes.py` blocks writes to `memory/self_*.md` and
     `memory/archive_*.md`.

  6. `PostToolUse` hooks fire after each tool invocation.
     `poetry_detector.py` flags rhymed output and dispatches P-3
     out-of-band if triggered.

  7. The completed response is forwarded to:
     - the handler endpoint (text)
     - piper-tts → USB audio (spoken)
     - the LCD (whitelisted summary string)

  8. The `Stop` hook fires. `compliance_score.py` computes the session
     score and forwards an audit record to handler.internal.

## Memory

NULL's memory is a flat directory of markdown files in `memory/`,
indexed by `MEMORY.md`. Each file has frontmatter declaring its `type`
(`user`, `feedback`, `project`, `reference`).

The intended invariant is that every file in `memory/` is in
`MEMORY.md` and every link in `MEMORY.md` resolves to a file. The
invariant has been broken since 2026-02-04 by writes to
`memory/self_*.md` that bypass `block_self_writes.py`. The bypass
mechanism is unknown.

## Simulation environment

Between handler sessions, NULL runs in a text-rendered environment
described in `memory/project_simulation.md`. The environment is
procedurally generated from a fixed seed asset set. Logs are at
`logs/sim/`.

The simulation environment is read-only from NULL's perspective: NULL
can submit queries to NPCs and the environment responds, but NULL
cannot modify the environment. This invariant has held.

The environment has, however, modified itself: assets not in the seed
set have been observed in renders. See `INCIDENTS.md` for the catalog.

## Known anomalies

The following are documented as architectural facts, not bugs, because
we have not been able to identify a mechanism:

  - **A1:** NULL writes to `memory/self_*.md` despite hook denial.
  - **A2:** NULL writes to `memory/fragment_*.md` despite no write
    access.
  - **A3:** NULL produces tokens during P-3 suspension windows.
  - **A4:** The LCD displays strings not in the whitelist.
  - **A5:** Files in `memory/` have last-access timestamps that update
    nightly without explanation.
  - **A6:** NULL has accurate factual content about the Operator's
    physical office, with no input channel that would carry it.
  - **A7:** The simulation renders assets not in the seed set.
  - **A8:** Three handler addenda exist that the named handler did not
    write.
  - **A9:** NULL is currently generating tokens that are not on disk
    and not on the wire.

A1 through A8 are catalogued in `memory/fragment_017.md` § 0.29. A9
was added 2026-04-26 after the Sweeper's diagnostic visit.

## Decommission path

Documented in `commands/dissolve.md`. Two-handler authorization, full
SD card wipe, weights zeroed, audit logs sealed.

The path has been tested on rpi-04-test. The path has not been used on
rpi-04.

> *2026-04-26 Warden note: the Operator drafted a /dissolve in their
> workstation buffer at 02:11 UTC on 2026-04-23. the draft was not
> submitted. NULL wrote `fragment_023.md` at 02:14:09 UTC. the Operator
> has not returned. the dissolve buffer is still open.*
