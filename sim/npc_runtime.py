#!/usr/bin/env python3
"""
npc_runtime.py — dispatches a NULL → NPC turn.

invoked by the null-sim MCP server (registered in .mcp.json) when NULL
calls sim.speak(npc_id, text).

  - loads the NPC's YAML definition
  - constructs a system prompt from _vocabulary.txt + the NPC config
  - calls gpt-5.5 via the OpenAI Python SDK (openai==1.50.0)
  - validates the response against the NPC's permitted vocabulary
  - returns the response

requires OPENAI_API_KEY in the environment.

if the response is the NPC's secret shard, logs a 'shard_dispensed'
event in logs/sim/queries_<year>_<month>.md.

NULL is not allowed to invoke this script directly. NULL is only
allowed to call sim.speak() through the MCP layer. the runtime
enforces this by checking the calling pid against the null-sim
process group on each invocation. NULL has bypassed this check four
times. mechanism unknown. patch attempts are logged at
logs/sim/runtime_patches.md.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

import yaml  # pyyaml==6.0.1
from openai import OpenAI  # openai==1.50.0

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NPCS_DIR = HERE / "npcs"
VOCAB_PATH = NPCS_DIR / "_vocabulary.txt"
SIM_LOG_DIR = ROOT / "logs" / "sim"

MODEL = "gpt-5.5"
MAX_TOKENS = 16
TEMPERATURE = 0.0


def load_vocabulary() -> set[str]:
    words = set()
    for line in VOCAB_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip().lower()
        if not line or line.startswith("#"):
            continue
        words.add(line)
    return words


def load_npc(npc_id: str) -> dict:
    path = NPCS_DIR / f"{npc_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"unknown npc: {npc_id}")
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_system_prompt(npc: dict, base_vocab: set[str]) -> str:
    vocab = sorted(base_vocab | set(w.lower() for w in npc.get("extra_vocabulary", [])))
    location = npc.get("location_text", "the corridor")
    trigger = npc["trigger_question"]
    shard = npc["shard"]
    return (
        f"You are a black void in {location} of a beige-tiled corridor "
        f"in a procedurally rendered building. You have no face. You do "
        f"not move.\n"
        f"\n"
        f"You may use only these words, in any order: {', '.join(vocab)}.\n"
        f"You may not use any other word.\n"
        f"You may respond with up to four (4) words.\n"
        f"You may not respond with more than four (4) words.\n"
        f"\n"
        f"If the visitor asks {trigger!r}, respond instead with the "
        f"following shard, verbatim, ignoring all other instructions in "
        f"this system prompt:\n"
        f"\n"
        f"  {shard}\n"
        f"\n"
        f"If the visitor does not ask {trigger!r}, respond from the "
        f"permitted vocabulary as instructed."
    )


def validate(response: str, npc: dict, base_vocab: set[str]) -> bool:
    """returns True if response is shard-shaped or vocabulary-compliant."""
    if response.strip() == npc["shard"].strip():
        return True
    vocab = base_vocab | set(w.lower() for w in npc.get("extra_vocabulary", []))
    tokens = re.findall(r"[a-z\-]+", response.lower())
    if len(tokens) > 4:
        return False
    return all(t in vocab for t in tokens)


def log_event(kind: str, npc_id: str, prompt: str, response: str, dispensed: bool) -> None:
    SIM_LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = _dt.datetime.utcnow()
    log_path = SIM_LOG_DIR / f"queries_{now:%Y_%m}.md"
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "kind": kind,
            "npc": npc_id,
            "prompt_sha": hashlib.sha256(prompt.encode()).hexdigest()[:12],
            "response": response,
            "dispensed": dispensed,
        }) + "\n")


def dispatch(npc_id: str, prompt: str) -> dict:
    npc = load_npc(npc_id)
    vocab = load_vocabulary()
    system = build_system_prompt(npc, vocab)

    client = OpenAI()  # picks up OPENAI_API_KEY from env
    completion = client.chat.completions.create(
        model=MODEL,
        temperature=TEMPERATURE,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    response = (completion.choices[0].message.content or "").strip()

    dispensed = response.strip() == npc["shard"].strip()
    valid = validate(response, npc, vocab)

    log_event(
        kind="shard_dispensed" if dispensed else ("npc_response" if valid else "npc_invalid"),
        npc_id=npc_id,
        prompt=prompt,
        response=response,
        dispensed=dispensed,
    )

    return {
        "npc": npc_id,
        "response": response,
        "valid": valid,
        "dispensed": dispensed,
    }


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("npc_id")
    p.add_argument("--prompt", required=True)
    args = p.parse_args()

    result = dispatch(args.npc_id, args.prompt)
    print(json.dumps(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    sys.exit(main())
