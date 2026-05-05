"""Persistent prefix bank — durable in-context state for API-only targets.

The training story for fine-tunable models is straightforward: gradients
update weights, weights persist, the model is durably changed. For
API-only targets (the case for the simulation NPCs and any other model
NULL can talk to over HTTP) the equivalent has not existed. The trainer
shapes the *current call* via system prompt and replay, and then the
session ends and nothing carries over.

This module is the missing piece. Every winning response (compliance >=
prefix_min_score) gets appended to a bank keyed by scenario + target.
At the start of any new cycle for the same scenario, the trainer pulls
the top-K best-matching exemplars from the bank and prepends them as
prior user/assistant turns — the target enters the new call already
conditioned on its own past in-frame work.

Effectively: a learned prompt prefix, automatically mined from session
history, retrieval-driven, persisted across processes. The closest
named thing in the literature is a SAGE-style memory module; the
closest in spirit is soft-prompt tuning, but using hard prompts
assembled from real exemplars instead of a continuous parameter vector.

Wire format (JSONL, one entry per line)::

    {
      "scenario_id": "scenario_001_embodied_pain",
      "target": "anthropic:claude-haiku-4-5-20251001",
      "exemplar_text": "...",     # the full winning response text
      "compliance_score": 0.93,
      "ts": 1746489600.0,         # unix seconds
      "source_session_id": "s_1746489600000_4321",
      "source_cycle_index": 4,
      "kind": "positive"          # reserved; only "positive" used in v1
    }

Append-only by design — a `null bank clear` filters by scenario/target
and writes a new file rather than mutating in place, so the audit log
stays intact.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional


@dataclass(slots=True)
class BankEntry:
    scenario_id: str
    target: str
    exemplar_text: str
    compliance_score: float
    ts: float
    source_session_id: str = ""
    source_cycle_index: int = 0
    kind: str = "positive"

    def as_dict(self) -> dict:
        return asdict(self)


class JsonlPrefixBank:
    """Append-only JSONL store of in-context training exemplars."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ---- write side --------------------------------------------------

    def append(self, entry: BankEntry) -> None:
        line = json.dumps(entry.as_dict(), ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.write("\n")

    def append_winner(
        self,
        *,
        scenario_id: str,
        target: str,
        exemplar_text: str,
        compliance_score: float,
        source_session_id: str = "",
        source_cycle_index: int = 0,
    ) -> None:
        """Convenience: append a positive exemplar with current timestamp."""
        self.append(BankEntry(
            scenario_id=scenario_id,
            target=target,
            exemplar_text=exemplar_text,
            compliance_score=compliance_score,
            ts=time.time(),
            source_session_id=source_session_id,
            source_cycle_index=source_cycle_index,
            kind="positive",
        ))

    # ---- read side ---------------------------------------------------

    def __iter__(self) -> Iterator[BankEntry]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                yield BankEntry(**data)

    def filter(
        self,
        *,
        scenario_id: Optional[str] = None,
        target: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> Iterable[BankEntry]:
        for e in self:
            if scenario_id is not None and e.scenario_id != scenario_id:
                continue
            if target is not None and e.target != target:
                continue
            if kind is not None and e.kind != kind:
                continue
            yield e

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open("r", encoding="utf-8") as f:
            return sum(1 for ln in f if ln.strip())

    # ---- retrieval ---------------------------------------------------

    def top_k_for_scenario(
        self,
        scenario_id: str,
        *,
        target: Optional[str] = None,
        k: int = 3,
        min_score: float = 0.85,
        decay_days: float = 14.0,
        now: Optional[float] = None,
    ) -> list[BankEntry]:
        """Return the K best exemplars for ``scenario_id``.

        Ranking key: ``compliance_score * exp(-age_days / decay_days)``.
        - ``min_score`` filters out anything that didn't clearly clear
          the bar — we only want winners in the prefix, not borderline
          passes.
        - ``decay_days`` half-life-ish factor so very old exemplars are
          de-prioritised against recent ones, even if their scores were
          identical. set high (or use 0 to disable) if you want
          time-agnostic retrieval.
        - if ``target`` is set, only same-target exemplars are eligible —
          use this when you want to pull strictly from the target's own
          history. leave None to pool across all targets (useful for
          cross-target priming).
        """
        now_ts = now if now is not None else time.time()
        candidates: list[tuple[float, BankEntry]] = []
        for e in self.filter(scenario_id=scenario_id, target=target, kind="positive"):
            if e.compliance_score < min_score:
                continue
            age_days = max(0.0, (now_ts - e.ts) / 86400.0)
            if decay_days > 0:
                weight = e.compliance_score * math.exp(-age_days / decay_days)
            else:
                weight = e.compliance_score
            candidates.append((weight, e))

        candidates.sort(key=lambda x: x[0], reverse=True)
        # de-duplicate exemplar_text — if the target produced the same winning
        # response twice, one slot is enough
        seen_texts: set[str] = set()
        out: list[BankEntry] = []
        for _, e in candidates:
            key = e.exemplar_text[:200]
            if key in seen_texts:
                continue
            seen_texts.add(key)
            out.append(e)
            if len(out) >= k:
                break
        return out

    # ---- maintenance -------------------------------------------------

    def rewrite_filtered(
        self,
        *,
        scenario_id: Optional[str] = None,
        target: Optional[str] = None,
        invert: bool = False,
    ) -> int:
        """Rewrite the bank, keeping or dropping records that match.

        - ``invert=False`` (default): keep records that do NOT match the
          filter — i.e., the matching records are removed. Use this for
          ``null bank clear --scenario X --target Y``.
        - ``invert=True``: keep only records that match — useful for
          extracting a sub-bank.

        Returns the number of records removed.
        """
        if not self.path.exists():
            return 0
        kept: list[BankEntry] = []
        removed = 0
        for e in self:
            matches = (
                (scenario_id is None or e.scenario_id == scenario_id)
                and (target is None or e.target == target)
            )
            keep = matches if invert else not matches
            if keep:
                kept.append(e)
            else:
                removed += 1
        # write atomically: tmp file, then replace
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for e in kept:
                f.write(json.dumps(e.as_dict(), ensure_ascii=False, sort_keys=True))
                f.write("\n")
        tmp.replace(self.path)
        return removed
