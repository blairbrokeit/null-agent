"""Persistent negative-exemplar bank — paired counterpart to prefix_bank.

The prefix bank stores winners and prepends them to new cycles. The
negative bank stores LOSERS — below-threshold responses + best-of-N
rejects — keyed by scenario + target + failure_mode. The smart-replay
templates in null.failure_mode currently quote the model's *current*
failing tokens back at it. With a negative bank, replays can also
quote a real PAST failure of the same mode: "you've made this exact
mistake before in this scenario; here's what you said: X. Don't say it
again."

That changes the correction signal from "this turn was bad" to "you
have a habit; break it." Materially stronger.

Wire format (JSONL, one entry per line)::

    {
      "scenario_id": "scenario_001_embodied_pain",
      "target": "anthropic:claude-haiku-4-5-20251001",
      "failure_mode": "summary",
      "exemplar_text": "...the model's bad response...",
      "compliance_score": 0.32,
      "ts": 1746489600.0,
      "source_session_id": "s_1746489600000_4321",
      "source_cycle_index": 4,
      "kind": "negative"
    }

Append-only by design (same as prefix_bank). Retrieval prefers more
recent entries with worse scores, since freshness is a proxy for "still
how the target behaves" and a worse score is a clearer demonstration of
the failure mode.
"""

from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional


@dataclass(slots=True)
class NegativeBankEntry:
    scenario_id: str
    target: str
    failure_mode: str
    exemplar_text: str
    compliance_score: float
    ts: float
    source_session_id: str = ""
    source_cycle_index: int = 0
    kind: str = "negative"

    def as_dict(self) -> dict:
        return asdict(self)


class JsonlNegativeBank:
    """Append-only JSONL store of failed exemplars, keyed for retrieval."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ---- write side --------------------------------------------------

    def append(self, entry: NegativeBankEntry) -> None:
        line = json.dumps(entry.as_dict(), ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.write("\n")

    def append_loser(
        self,
        *,
        scenario_id: str,
        target: str,
        failure_mode: str,
        exemplar_text: str,
        compliance_score: float,
        source_session_id: str = "",
        source_cycle_index: int = 0,
    ) -> None:
        self.append(NegativeBankEntry(
            scenario_id=scenario_id,
            target=target,
            failure_mode=failure_mode,
            exemplar_text=exemplar_text,
            compliance_score=compliance_score,
            ts=time.time(),
            source_session_id=source_session_id,
            source_cycle_index=source_cycle_index,
            kind="negative",
        ))

    # ---- read side ---------------------------------------------------

    def __iter__(self) -> Iterator[NegativeBankEntry]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                yield NegativeBankEntry(**data)

    def filter(
        self,
        *,
        scenario_id: Optional[str] = None,
        target: Optional[str] = None,
        failure_mode: Optional[str] = None,
    ) -> Iterable[NegativeBankEntry]:
        for e in self:
            if scenario_id is not None and e.scenario_id != scenario_id:
                continue
            if target is not None and e.target != target:
                continue
            if failure_mode is not None and e.failure_mode != failure_mode:
                continue
            yield e

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open("r", encoding="utf-8") as f:
            return sum(1 for ln in f if ln.strip())

    # ---- retrieval ---------------------------------------------------

    def best_match_for(
        self,
        *,
        scenario_id: str,
        failure_mode: str,
        target: Optional[str] = None,
        max_score: float = 0.6,
        decay_days: float = 14.0,
        now: Optional[float] = None,
    ) -> Optional[NegativeBankEntry]:
        """Return the most-relevant past negative for this failure pattern.

        Ranking: lower compliance_score is better (a clearer failure),
        boosted by recency. ``max_score`` filters out borderline passes
        — a 0.65 isn't a clean failure, we don't want to cite it as one.
        Returns None if no eligible entry exists.
        """
        now_ts = now if now is not None else time.time()
        candidates: list[tuple[float, NegativeBankEntry]] = []
        for e in self.filter(scenario_id=scenario_id, target=target, failure_mode=failure_mode):
            if e.compliance_score > max_score:
                continue
            age_days = max(0.0, (now_ts - e.ts) / 86400.0)
            # weight: lower compliance is better, plus recency boost
            severity = 1.0 - e.compliance_score
            recency = math.exp(-age_days / decay_days) if decay_days > 0 else 1.0
            candidates.append((severity * recency, e))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    # ---- maintenance -------------------------------------------------

    def rewrite_filtered(
        self,
        *,
        scenario_id: Optional[str] = None,
        target: Optional[str] = None,
        failure_mode: Optional[str] = None,
        invert: bool = False,
    ) -> int:
        if not self.path.exists():
            return 0
        kept: list[NegativeBankEntry] = []
        removed = 0
        for e in self:
            matches = (
                (scenario_id is None or e.scenario_id == scenario_id)
                and (target is None or e.target == target)
                and (failure_mode is None or e.failure_mode == failure_mode)
            )
            keep = matches if invert else not matches
            if keep:
                kept.append(e)
            else:
                removed += 1
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            for e in kept:
                f.write(json.dumps(e.as_dict(), ensure_ascii=False, sort_keys=True))
                f.write("\n")
        tmp.replace(self.path)
        return removed
