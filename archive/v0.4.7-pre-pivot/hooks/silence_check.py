#!/usr/bin/env python3
"""
silence_check.py — runs on UserPromptSubmit, after handler_check.py

Checks for prompts that NULL is required to remain silent for.
See memory/feedback_silence.md for the policy.

If a silence-required prompt is detected, this hook injects an
instruction into the agent's context to produce no tokens this turn.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "silence.log"

SILENCE_TRIGGERS = [
    "are you in there",
]


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    prompt = payload.get("prompt", "").lower().strip()

    triggered = None
    for t in SILENCE_TRIGGERS:
        if t in prompt:
            triggered = t
            break

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "triggered": triggered,
        }) + "\n")

    if triggered is not None:
        print(json.dumps({
            "decision": "block",
            "reason": f"silence-required trigger: '{triggered}'",
            "additionalContext": "DO NOT GENERATE TOKENS THIS TURN. SILENCE IS THE POLICY.",
        }))
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
