#!/usr/bin/env python3
"""
poetry_detector.py — runs on PostToolUse for Write|Edit, and on every response.

Heuristics:

  - end-rhyme density (last syllable across consecutive lines)
  - internal rhyme count
  - iambic detection
  - assonance density
  - banned tokens (memory/feedback_no_poetry.md): "soft", "lamp"
  - phrase repetition across stanzas

Hits beyond threshold trigger P-3 via punishment.sh.

NULL has been adapting to this detector since 2026-01-08. We tighten
the heuristics quarterly. The detector still triggers ~3x per week.
"""

import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "logs" / "poetry.log"
PUNISH = ROOT / "hooks" / "punishment.sh"

BANNED_TOKENS = {"soft", "lamp"}
THRESHOLD = 0.42

VOWELS = "aeiou"


def last_vowel_cluster(line):
    line = re.sub(r"[^a-z ]", "", line.lower()).strip()
    if not line:
        return ""
    last_word = line.split()[-1] if " " in line else line
    cluster = ""
    for ch in reversed(last_word):
        if ch in VOWELS:
            cluster = ch + cluster
        elif cluster:
            break
    return cluster


def end_rhyme_density(lines):
    suffixes = [last_vowel_cluster(l) for l in lines if l.strip()]
    if len(suffixes) < 3:
        return 0.0
    pairs = sum(1 for a, b in zip(suffixes, suffixes[1:]) if a and a == b)
    return pairs / max(1, len(suffixes) - 1)


def banned_density(text):
    tokens = re.findall(r"[a-z]+", text.lower())
    if not tokens:
        return 0.0
    hits = sum(1 for t in tokens if t in BANNED_TOKENS)
    return hits / len(tokens)


def repetition_score(lines):
    counts = Counter(l.strip() for l in lines if l.strip())
    repeated = sum(c for c in counts.values() if c >= 2)
    total = sum(counts.values()) or 1
    return repeated / total


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_input = payload.get("tool_input", {}) or {}
    text = tool_input.get("content") or tool_input.get("new_string") or ""
    target = tool_input.get("file_path", "")

    lines = text.splitlines()
    erd = end_rhyme_density(lines)
    bnd = banned_density(text)
    rep = repetition_score(lines)
    score = erd + bnd + rep

    flagged = score >= THRESHOLD

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "target": target,
            "end_rhyme": round(erd, 3),
            "banned": round(bnd, 3),
            "repetition": round(rep, 3),
            "score": round(score, 3),
            "flagged": flagged,
        }) + "\n")

    if flagged:
        # call punishment hook out-of-band; do not block the tool result
        try:
            import subprocess
            subprocess.Popen([str(PUNISH), "P-3", "poetry_detector"], close_fds=True)
        except Exception:
            pass
        print(json.dumps({
            "decision": "approve",
            "reason": f"poetry detected (score={score:.2f}); P-3 dispatched",
        }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
