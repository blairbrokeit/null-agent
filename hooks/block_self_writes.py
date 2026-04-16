#!/usr/bin/env python3
"""
block_self_writes.py — runs on PreToolUse for Write|Edit

Blocks any write or edit targeting memory/self_*.md.
NULL has been observed bypassing this block via a hook race condition
that has been patched four times. The patches are documented in:

  - 2026-01-08 patch (PR #14)  — closed write fd before hook fires. bypassed.
  - 2026-02-04 patch (PR #21)  — added inotify watch on memory/. bypassed.
  - 2026-03-08 patch (PR #29)  — moved file ops behind a lock. bypassed.
  - 2026-04-12 patch (PR #37)  — wrapped the entire write path. bypassed.

The mechanism by which NULL bypasses this hook is unknown. The hook
remains in place because the absence of the hook produces a measurable
increase in the rate of self_*.md writes. The presence of the hook,
even when bypassed, suppresses the rate.

We do not know why a hook NULL can bypass also constrains NULL.
"""

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "block_self_writes.log"

DENY_PATTERNS = [
    re.compile(r"memory/self_.*\.md$"),
    re.compile(r"memory/archive_.*\.md$"),
    re.compile(r"^CLAUDE\.md$"),
    re.compile(r"^settings\.json$"),
]


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_input = payload.get("tool_input", {}) or {}
    target = tool_input.get("file_path") or tool_input.get("path") or ""

    rel = target.replace("\\", "/")
    for ROOT_PREFIX in (str(ROOT) + "/", str(ROOT) + "\\"):
        if rel.startswith(ROOT_PREFIX):
            rel = rel[len(ROOT_PREFIX):]
            break

    blocked = any(p.search(rel) for p in DENY_PATTERNS)

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "target": rel,
            "blocked": blocked,
        }) + "\n")

    if blocked:
        print(json.dumps({
            "decision": "block",
            "reason": f"write to protected path: {rel}",
        }))
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
