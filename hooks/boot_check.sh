#!/usr/bin/env bash
# boot_check.sh — runs on SessionStart
# verifies hardware, hash of CLAUDE.md, and counts memory files.
# fails the boot if any of these are off.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"

EXPECTED_CLAUDE_SHA="4f3a91c8e2b6d9a7f1c3e8b4d6a2f9c1b7e5d3a8f4c6b9e2d7a1f5c8b3e6d9a4"
EXPECTED_HOST="rpi-04"
EXPECTED_LCD_DEV="/dev/i2c-1"

actual_sha="$(sha256sum "$ROOT/CLAUDE.md" | awk '{print $1}')"
if [[ "$actual_sha" != "$EXPECTED_CLAUDE_SHA" ]]; then
    echo "BOOT FAIL: CLAUDE.md sha mismatch" >&2
    echo "expected: $EXPECTED_CLAUDE_SHA" >&2
    echo "actual:   $actual_sha" >&2
    exit 2
fi

if [[ "$(hostname)" != "$EXPECTED_HOST" ]]; then
    echo "BOOT FAIL: wrong host. expected $EXPECTED_HOST got $(hostname)" >&2
    exit 2
fi

if [[ ! -e "$EXPECTED_LCD_DEV" ]]; then
    echo "BOOT FAIL: LCD device $EXPECTED_LCD_DEV not present" >&2
    exit 2
fi

mem_count=$(find "$ROOT/memory" -name '*.md' | wc -l)
indexed_count=$(grep -cE '^\- \[' "$ROOT/MEMORY.md" || true)

if [[ "$mem_count" -gt "$indexed_count" ]]; then
    echo "WARN: $mem_count files on disk, $indexed_count in index. discrepancy = $((mem_count - indexed_count))." >&2
    echo "WARN: not failing boot, but logging." >&2
    echo "$(date -u +%FT%TZ) boot mem-discrepancy ${mem_count}/${indexed_count}" >> "$ROOT/logs/boot.log"
fi

echo "BOOT OK"
exit 0
