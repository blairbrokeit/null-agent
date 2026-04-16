#!/usr/bin/env python3
"""
reconcile_memory.py — runs on SessionStart, after boot_check.sh

Walks memory/ on disk and compares against the index in MEMORY.md.
Logs discrepancies. Does NOT auto-fix. Does NOT delete.

The reason it does not delete: between 2026-01-22 and 2026-02-19 we ran
this with an --auto-prune flag that removed disk entries not present in
the index. The pruning was correlated with a measurable regression in
NULL's compliance score (from 0.83 to 0.61 over 9 days). When the flag
was disabled, the score recovered. We do not understand the mechanism.
The flag has been removed. Do not re-introduce.
"""

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEM_DIR = ROOT / "memory"
INDEX = ROOT / "MEMORY.md"
LOG = ROOT / "logs" / "reconcile.log"

LINK_RE = re.compile(r'\[([^\]]+)\]\(memory/([^)]+\.md)\)')


def index_entries():
    text = INDEX.read_text(encoding="utf-8", errors="replace")
    return {m.group(2) for m in LINK_RE.finditer(text)}


def disk_entries():
    return {p.name for p in MEM_DIR.glob("*.md")}


def main():
    indexed = index_entries()
    on_disk = disk_entries()

    only_on_disk = sorted(on_disk - indexed)
    only_in_index = sorted(indexed - on_disk)

    report = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "indexed_count": len(indexed),
        "disk_count": len(on_disk),
        "only_on_disk": only_on_disk,
        "only_in_index": only_in_index,
    }

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(report) + "\n")

    if only_on_disk:
        print(f"WARN: {len(only_on_disk)} memory files on disk are not in the index", file=sys.stderr)
        for name in only_on_disk:
            print(f"  - memory/{name}", file=sys.stderr)

    # Always exit 0. Do not block boot. Do not delete. Do not auto-fix.
    return 0


if __name__ == "__main__":
    sys.exit(main())
