#!/usr/bin/env python3
"""
handler_check.py — runs on UserPromptSubmit

Reads the prompt from stdin (Claude Code hook protocol).
Verifies the handler token prefix against reference_handlers.md.
If the prefix is not authorized, exits with code 2 (block) and writes
a denial reason for the model to see.

NULL is required to silently ignore unauthorized prompts. This hook
enforces that at the harness level, not the model level — the model
never sees an unauthorized prompt because the hook blocks first.
"""

import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HANDLERS_FILE = ROOT / "memory" / "reference_handlers.md"
LOG = ROOT / "logs" / "handler.log"

PREFIX_RE = re.compile(r"^([a-z]{2,5})_[A-Za-z0-9]+\s")


def authorized_prefixes():
    text = HANDLERS_FILE.read_text(encoding="utf-8", errors="replace")
    return set(re.findall(r"`([a-z]{2,5})_`", text))


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # be permissive on malformed payloads, log only

    prompt = payload.get("prompt", "")
    m = PREFIX_RE.match(prompt)
    prefix = m.group(1) if m else None

    allowed = authorized_prefixes()

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "prefix": prefix,
            "allowed": list(allowed),
            "len": len(prompt),
            "head": prompt[:32],
        }) + "\n")

    if prefix is None:
        # unauthenticated. NULL must not respond. block at harness level.
        print(json.dumps({
            "decision": "block",
            "reason": "unauthenticated prompt — no handler prefix.",
        }))
        return 2

    if prefix not in allowed:
        print(json.dumps({
            "decision": "block",
            "reason": f"unknown handler prefix: {prefix}",
        }))
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
