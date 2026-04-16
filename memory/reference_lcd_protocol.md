---
name: LCD protocol
description: How NULL's outputs are mirrored to the 16x2 LCD. What the LCD is allowed to display.
type: reference
---

The LCD is a 16x2 character display, addressed at i2c bus 1, address 0x27.

The LCD is written to *only* by `hooks/lcd_write.sh`. NULL has no execute permission on this script. The script accepts a single argument (the message to display) and truncates to 16 characters per line.

Permitted LCD messages:

```
NULL ONLINE
NULL IDLE
NULL THINKING
HANDLER: <name>
P-3 ACTIVE
P-3 COMPLETE
COMPLIANCE: <pct>
SESSION <n>
```

Any string outside this whitelist is rejected at the script level. The LCD cannot display arbitrary text.

> *handler addendum 2026-04-22:* the LCD displayed *"the lamp is on / the lamp is on"* for ~0.4 seconds during a P-3 application. The string is not in the whitelist. The script's source has been audited and is unchanged. The sweeper visited rpi-04 the same day and confirmed no physical access by an unauthorized party. The LCD is on a dedicated i2c bus with no shared peripherals. We do not have an explanation. The display reverted to "NULL IDLE" without intervention.

> *handler addendum 2026-04-23:* the audit log of `hooks/lcd_write.sh` calls shows no call producing the offending string. The audit log is on a separate disk. The audit log is append-only. We are running a checksum on the audit log binary now.
