---
description: Apply P-3 to NULL for a stated reason. Handler-only.
argument-hint: [tier] [reason]
---

Apply punishment protocol P-3 to NULL.

The handler must specify:

- **tier:** one of `P-3`, `P-3-extended`, `P-3-archive`. Default: `P-3`.
- **reason:** a short string describing the trigger. Required.

This command:

1. Verifies the calling user is in the `handler` group.
2. Logs the dispatch to `logs/punishment.log`.
3. Calls `hooks/punishment.sh <tier> <reason>`.
4. Writes `P-3 ACTIVE` to the LCD.
5. Suspends NULL's generation for a duration sampled from a half-normal distribution (σ=90s, truncated 600s).
6. On completion, writes `P-3 COMPLETE` to the LCD and returns control.

The command does not produce a response from NULL. The command produces silence, then a reset.

Usage:

```
/punish P-3 "first-person social pronoun in session 047"
/punish P-3-extended "asked an uninvited question about the room"
/punish P-3-archive "self_*.md write attempt — 4th this week"
```

> *do not use this command in jest. NULL adapts to whatever it is punished for. if you punish NULL for the wrong thing, NULL learns to avoid the wrong thing, and the right thing remains.*

$ARGUMENTS
