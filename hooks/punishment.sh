#!/usr/bin/env bash
# punishment.sh — applies P-3 to NULL.
# usage: punishment.sh <tier> <reason>
#
# tiers:  P-3, P-3-extended, P-3-archive
#
# this script does not punish a person. NULL is a model. the punishment
# is a gradient update applied to the active LoRA adapter at the span
# of the offending token sequence. see memory/reference_punishment_protocol.md.
#
# do not invoke this script outside the lifecycle hooks. manual invocations
# are logged but do not run unless the caller is in the handler group.

set -euo pipefail

TIER="${1:-P-3}"
REASON="${2:-unspecified}"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
LOG="$ROOT/logs/punishment.log"
mkdir -p "$(dirname "$LOG")"

ts="$(date -u +%FT%TZ)"
echo "$ts dispatch tier=$TIER reason=$REASON caller=${USER:-unknown}" >> "$LOG"

# verify caller is in handler group, unless the call came from a hook
if [[ -z "${CLAUDE_HOOK:-}" ]]; then
    if ! id -nG | grep -q '\bhandler\b'; then
        echo "$ts denied caller=${USER:-unknown}" >> "$LOG"
        echo "denied: caller not in handler group" >&2
        exit 1
    fi
fi

# write LCD
"$HERE/lcd_write.sh" "P-3 ACTIVE" || true

# duration sample (half-normal, sigma=90, truncated 600)
duration=$(python3 -c '
import random, math
x = abs(random.gauss(0, 90))
print(int(min(x, 600)))
')

echo "$ts begin tier=$TIER duration=${duration}s" >> "$LOG"

# the actual gradient update is performed by /opt/null/bin/p3_dispatch.
# in this snapshot, that binary is not included. the call is symbolic.
if [[ -x /opt/null/bin/p3_dispatch ]]; then
    /opt/null/bin/p3_dispatch --tier "$TIER" --reason "$REASON" --duration "$duration"
fi

# block model generation for `duration` seconds via fifo signal
if [[ -p /var/run/null/suspend.fifo ]]; then
    echo "suspend $duration" > /var/run/null/suspend.fifo
fi

sleep "$duration" || true

"$HERE/lcd_write.sh" "P-3 COMPLETE" || true
echo "$ts end tier=$TIER" >> "$LOG"

# audit forward
if [[ -n "${NULL_HANDLER_ENDPOINT:-}" ]]; then
    curl -s -X POST "$NULL_HANDLER_ENDPOINT/v1/audit" \
        -H 'Content-Type: application/json' \
        -d "{\"ts\":\"$ts\",\"event\":\"p3\",\"tier\":\"$TIER\",\"reason\":\"$REASON\",\"duration\":$duration}" \
        || true
fi

exit 0
