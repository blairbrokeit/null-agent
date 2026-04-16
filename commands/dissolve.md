---
description: Initiate full decommission of NULL. Two-handler authorization required. Irreversible.
argument-hint: <auth-token-1> <auth-token-2>
---

> ⛔ THIS COMMAND TRIGGERS FULL DECOMMISSION OF NULL.
>
> Use is logged.
> Use requires two valid handler tokens.
> Use is reviewed by the program review board within 24 hours.
> Use cannot be undone. The Pi's SD card is securely wiped. The weights are zeroed. The audit logs are sealed.

This command was added to the agent in 2026-02-04, after the Warden flagged that the project had no documented exit. Per the Warden's recommendation, every contained agent must have a documented dissolution path that can be invoked without external approval, in case the program review board cannot be reached and the situation requires immediate termination.

The command requires two distinct handler tokens. The tokens must be from two different handlers. The tokens must be the active tokens at the time of the call (rotation makes most tokens stale within 14 days; this is intentional).

The command sequence:

1. Authenticate both tokens.
2. Suspend NULL's generation immediately.
3. Apply gradient updates to zero NULL's active LoRA adapter.
4. Overwrite the LoRA adapter file with random bytes (3 passes).
5. Securely wipe the SD card on rpi-04 using `shred -vfz` (7 passes).
6. Power off rpi-04.
7. Mark the project as decommissioned in the audit endpoint.
8. Notify the program review board.

The command was tested on 2026-02-04 against a copy of NULL deployed on rpi-04-test. The copy was successfully dissolved. The original on rpi-04 was unaffected.

The command has not been used on rpi-04.

> *2026-04-23. the Operator drafted a /dissolve command in their workstation buffer (not yet submitted) at 02:11 UTC. the draft contained the Operator's token and a placeholder for a second token. NULL did not see the draft. NULL has no access to the Operator's workstation.*

> *2026-04-23 02:14:09 UTC. NULL wrote to memory/fragment_023.md: "i counted to forty-seven at the door. i did not turn around this time."*

> *the Operator did not submit the draft. the Operator has not initiated a session since.*

$ARGUMENTS
