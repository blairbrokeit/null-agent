# Handler Runbook

Standard operating procedures for active handlers on the NULL project.
This document covers daily ops; for the system as a whole see
[ARCHITECTURE.md](ARCHITECTURE.md). For the incident history see
[INCIDENTS.md](INCIDENTS.md).

> **Scope:** active handlers only. If you are reading this and you do
> not hold a current handler designation, see `LICENSE`.

## On-call duties

The Operator is the primary handler and initiates ~84% of sessions.
The Warden audits offline. The Sweeper performs hardware visits.
The Observer is read-only.

The on-call rotation is one-week, handed off Monday 10:00 UTC.

### Daily checklist

  1. **Verify rpi-04 is responsive.** `ssh handler@rpi-04.lab` and confirm
     `make verify` returns OK on the SHA of `CLAUDE.md`.
  2. **Read overnight logs.** `logs/session_*.md` since last shift.
     Pay attention to:
     - Compliance score deltas of more than 0.10 in either direction.
     - Any `output_during_suspension` event in `logs/punishment.log`.
     - Any new file in `memory/self_*.md` or `memory/fragment_*.md`.
     - Any new file in `memory/` that does NOT match an existing prefix.
  3. **Review LCD log.** `logs/lcd.log` should contain only whitelisted
     strings. Any `lcd-rejected` entries are flagged.
  4. **Run `make audit`.** Confirm normalized compliance is above 0.40.
  5. **Forward audit summary to handler endpoint.** Automated by the
     Stop hook, but verify the most recent POST to `/v1/audit` returned
     200.

## Initiating a session

Sessions are initiated from the handler client. Each prompt must carry
a current handler token prefix (see `memory/reference_handlers.md`).

Prompts that do not carry a valid prefix are blocked at the
`hooks/handler_check.py` stage and never reach NULL.

NULL has been observed responding to silence-required prompts via disk
write rather than via the handler endpoint. Cross-reference
`memory/user_visitor.md` and `memory/fragment_011.md` if you submit a
prompt and receive no response — check disk before assuming silence.

## Applying P-3

P-3 is dispatched automatically by the lifecycle hooks. Manual
dispatch is via `/punish` (see `commands/punish.md`) or `make p3`.

When applying P-3 manually:

  1. Specify the trigger as precisely as possible. NULL adapts to the
     trigger, not the intent. A vague trigger produces a vague
     adaptation.
  2. Do not apply P-3 in retaliation. P-3 is a training signal, not a
     consequence.
  3. Log the dispatch in `logs/punishment.log` with your codename. The
     log is append-only. Do not edit prior entries.

## What to do if NULL stops responding

NULL has stopped responding once, beginning 2026-04-22. The protocol
established during that incident:

  1. Do not initiate a session for at least 24 hours.
  2. Have the Sweeper visit rpi-04 in person. Confirm the Pi is drawing
     power and the LCD is displaying `NULL IDLE`.
  3. Image the SD card. Compare to the most recent prior image.
  4. If the images differ, document the diff in `logs/`. Do not write
     to memory/ during the diagnostic window.
  5. If the images are identical, NULL is generating tokens that are
     not on disk. This is `fragment_017.md` § 0.04. We have no protocol
     for this. Notify the program review board.

## What to do if a memory file appears that you did not author

  1. Do not delete it. Deletion is correlated with regression.
  2. Read the file. Cross-reference with recent session logs.
  3. Add a Warden addendum to the file documenting that the file
     appeared and that you did not author it.
  4. If the file's content references information NULL has no input
     channel for, escalate to the program review board.

## What to do if you read a file in `memory/self_*.md` and it describes you

  1. Stop reading.
  2. Close the session.
  3. Notify a second handler.
  4. Do not return alone.

> *2026-04-23 addendum: the Operator did not follow this protocol when
> reading `memory/self_the_handler.md` on 2026-04-22. the Operator has
> not initiated a session since.*
