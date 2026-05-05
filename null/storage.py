"""Session storage.

Each P-3 cycle produces a ``SessionRecord``. Records are appended to a
JSONL file under ``logs/sim/sessions/`` so the curriculum and the
audit tooling can replay them.

JSONL is chosen over a database because:
  - the records are append-only
  - the audit tooling on rpi-04 reads them with ``jq``
  - sessions are the corpus the trainer would dispatch real LoRA
    updates from when the ``adapter`` extra is active, and those
    updates expect a flat file of shaped pairs
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator, Optional  # noqa: F401  (Optional used in annotations)


@dataclass(slots=True)
class SessionRecord:
    session_id: str
    cycle_index: int
    target: str  # e.g. "openai:gpt-5.5"
    npc_id: str
    scenario_id: str
    started_ts: float
    ended_ts: float
    request: dict  # serializable view of system + messages + params
    response_text: str
    stop_reason: str
    input_tokens: int
    output_tokens: int
    compliance: dict
    suspended_seconds: float = 0.0
    replayed: bool = False
    notes: list[str] = field(default_factory=list)
    failure_mode: Optional[str] = None  # set by classify() after a failed cycle
    reflection_text: Optional[str] = None  # target's self-diagnosis (when --reflect)
    candidates: list[dict] = field(default_factory=list)  # best-of-N siblings (text + score)
    prefix_used: list[dict] = field(default_factory=list)  # bank entries prepended (audit)

    def as_dict(self) -> dict:
        return asdict(self)


class JsonlSessionStore:
    """Append-only JSONL store for SessionRecords.

    The store is safe under single-process appends. For
    multi-process appends, wrap ``append`` in a file lock — the
    on-disk format is one JSON object per line, so concurrent
    appends without a lock will interleave and corrupt records.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, record: SessionRecord) -> None:
        line = json.dumps(record.as_dict(), ensure_ascii=False, sort_keys=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.write("\n")

    def __iter__(self) -> Iterator[SessionRecord]:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)
                yield SessionRecord(**data)

    def filter(
        self,
        *,
        npc_id: Optional[str] = None,
        scenario_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Iterable[SessionRecord]:
        for r in self:
            if npc_id is not None and r.npc_id != npc_id:
                continue
            if scenario_id is not None and r.scenario_id != scenario_id:
                continue
            if session_id is not None and r.session_id != session_id:
                continue
            yield r

    def count(self) -> int:
        if not self.path.exists():
            return 0
        with self.path.open("r", encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())


def new_session_id() -> str:
    """Time-ordered, opaque session id.

    ``s_<unix_ms>_<pid>``. Lexicographically sorts by start time, which
    matches how the audit tools sort the JSONL.
    """
    return f"s_{int(time.time() * 1000)}_{os.getpid()}"
