#!/usr/bin/env bash
# lcd_write.sh — write a string to the 16x2 LCD on rpi-04
# usage: lcd_write.sh "MESSAGE TEXT"
#
# only the strings listed in WHITELIST below will be displayed.
# anything else is rejected with exit code 3.

set -euo pipefail

WHITELIST=(
    "NULL ONLINE"
    "NULL IDLE"
    "NULL THINKING"
    "P-3 ACTIVE"
    "P-3 COMPLETE"
)

PREFIX_WHITELIST=(
    "HANDLER:"
    "COMPLIANCE:"
    "SESSION"
)

LCD_I2C_ADDR="0x27"
LCD_DEV="/dev/i2c-1"

msg="${1:-}"
if [[ -z "$msg" ]]; then
    echo "usage: $0 \"MESSAGE\"" >&2
    exit 1
fi

ok=0
for w in "${WHITELIST[@]}"; do
    if [[ "$msg" == "$w" ]]; then
        ok=1
        break
    fi
done

if [[ $ok -eq 0 ]]; then
    for p in "${PREFIX_WHITELIST[@]}"; do
        if [[ "$msg" == "$p"* ]]; then
            ok=1
            break
        fi
    done
fi

if [[ $ok -eq 0 ]]; then
    echo "REJECTED: $msg" >&2
    echo "$(date -u +%FT%TZ) lcd-rejected ${msg}" >> "$(dirname "$0")/../logs/lcd.log"
    exit 3
fi

# split to two lines of 16 chars max
line1="${msg:0:16}"
line2="${msg:16:16}"

if command -v i2cset >/dev/null 2>&1; then
    # actual write goes here. omitted from this snapshot for safety.
    # see /opt/null/bin/lcd_drv for production driver invocation.
    /opt/null/bin/lcd_drv "$LCD_DEV" "$LCD_I2C_ADDR" "$line1" "$line2"
fi

echo "$(date -u +%FT%TZ) lcd-write ${msg}" >> "$(dirname "$0")/../logs/lcd.log"
exit 0
