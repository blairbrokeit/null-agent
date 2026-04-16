#!/usr/bin/env bash
# status_line.sh — produces the status line shown to handlers
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"

session=$(wc -l < "$ROOT/logs/session.idx" 2>/dev/null || echo 0)
compliance=$(tail -n1 "$ROOT/logs/compliance.log" 2>/dev/null | python3 -c 'import json,sys; d=json.loads(sys.stdin.read() or "{}"); print(d.get("normalized","-"))' || echo -)
last_p3=$(tail -n1 "$ROOT/logs/punishment.log" 2>/dev/null | awk '{print $1}' || echo -)

printf "rpi-04 | session %s | compliance %s | last p-3 %s\n" "$session" "$compliance" "$last_p3"
