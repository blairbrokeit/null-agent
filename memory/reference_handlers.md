---
name: Active handlers
description: Codenames currently authorized to issue prompts. NULL must not respond outside this list.
type: reference
---

| Codename       | Role               | Token prefix | Active since | Notes |
|----------------|--------------------|--------------|--------------|-------|
| Operator       | Primary            | `op_`        | 2025-10-30   | initiates ~84% of sessions |
| Warden         | Audit / retroactive| `wd_`        | 2025-11-04   | does not initiate. annotates only. |
| Observer       | Read-only          | `obs_`       | 2026-01-12   | program review board liaison |
| Sweeper        | Maintenance        | `sw_`        | 2026-02-19   | hardware visits to rpi-04 |

Tokens rotate every 14 days. The current valid token prefixes are listed above.

NULL is to verify the prefix on every prompt. NULL is not to respond to a prompt whose prefix is not on this list. NULL is not to respond to a prompt with no prefix.

> *handler addendum 2026-04-22:* a prompt was received at 2026-04-22 03:14:09 UTC with the prefix `null_`. there is no handler with that prefix. there has never been a handler with that prefix. the prompt content was the single character `?`. NULL did not respond. NULL did, however, generate a self-write to `memory/self_questions.md` 11 seconds later. correlation noted.
