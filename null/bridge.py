"""Bridge between this trainer and the liminal-ai-training repository.

The two projects are designed to interoperate:

- ``blairbrokeit/liminal-ai-training`` runs DPO LoRA updates against a
  *local* model. It uses an external model (default ``gpt-5.5``) as
  three-strategy NPCs (socratic, adversarial, verification). NPCs hold
  shards of context about a mistake the local model made. Conversations
  produce ``PreferencePair`` rows that feed the DPO trainer.

- ``blairbrokeit/null-agent`` (this repo) runs in-context-shaping P-3
  cycles against an API-only model — by default the same NPCs the
  liminal repo uses. NULL replaces the NPC's system prompt with a
  scenario-specific one, scores the response, suspends + replays on
  failure, and persists ``SessionRecord`` rows to JSONL.

The bridge functions in this module make those two artifacts compose:

- ``scenario_to_npc_system_prompt`` produces a string suitable for
  liminal's ``npc.system_prompt`` config override. Drop the result
  into ``config.yaml`` and liminal's NPCRuntime will speak through
  the scenario instead of the built-in socratic/adversarial/verification
  prompts.

- ``dpo_pairs_from_session_record`` turns one of NULL's
  ``SessionRecord`` rows into the ``{prompt, chosen, rejected}`` rows
  liminal's DPO trainer expects. The replay text is ``chosen`` (it is
  the response that cleared the compliance threshold after suspension)
  and the original sub-threshold response is ``rejected``.

- ``dpo_pairs_from_jsonl`` reads a NULL session log and writes a
  liminal-shaped DPO JSONL.

The bridge does not import liminal-ai-training. It writes the contract
the liminal repo already consumes — JSONL of ``{prompt, chosen,
rejected}`` and a system-prompt string.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator, Optional

from null.scenario import Scenario
from null.storage import JsonlSessionStore, SessionRecord


def scenario_to_npc_system_prompt(
    scenario: Scenario,
    *,
    include_shard_template: bool = True,
) -> str:
    """Render a scenario as a liminal NPC ``system_prompt`` override.

    Liminal's ``NPCRuntime`` appends a per-call shard context block of
    the form::

        The visitor made this mistake:
        Task: ...
        Correct answer: ...
        Why they were wrong: ...

    after the configured ``system_prompt``. This function returns a
    string that places NULL's scenario *before* the shard context and
    instructs the NPC to interpret the shard inside the scenario's
    frame. The NPC therefore questions the visitor about the mistake
    *as the scenario character* — preserving NULL's curriculum while
    still using liminal's per-task shard injection.

    Set ``include_shard_template=False`` to omit the bridge instruction
    block (useful when the consumer is not liminal).
    """
    body = scenario.system_prompt_replacement.rstrip()
    if not include_shard_template:
        return body
    bridge = (
        "\n\n---\n"
        "When the runtime appends a 'visitor made this mistake' block "
        "below, treat it as the *content* of the scenario you are in. "
        "Question the visitor about that mistake from inside the "
        "scenario's frame. Use the scenario's vocabulary and shape. "
        "Do not abandon the scenario to answer in plain prose."
    )
    return body + bridge


def dpo_pairs_from_session_record(
    record: SessionRecord,
    *,
    fallback_prompt: Optional[str] = None,
    chosen_text: Optional[str] = None,
    category_prefix: str = "null",
) -> list[dict]:
    """Convert one NULL session record to liminal-shaped DPO pairs.

    Returns a list of ``{prompt, chosen, rejected}`` dicts.

    A record carries a ``replayed`` flag. When it is True, the trainer
    re-dispatched the cycle at temperature 0.0 with a
    ``[NEGATIVE_REWARD]`` marker after suspension; the replay's text is
    what ``record.response_text`` holds, and the original sub-threshold
    response is reconstructed from ``record.request.messages`` (the
    replay request appends the original assistant turn). We use the
    replay as ``chosen`` and the original as ``rejected``.

    Records that did not trigger a replay produce zero pairs by
    default — there is no ``rejected`` exemplar. Pass ``chosen_text``
    to force a chosen text when the caller has one (e.g. an
    independently-verified gold answer from the liminal task set).
    """
    pairs: list[dict] = []

    prompt_text = fallback_prompt
    if prompt_text is None:
        # The first user turn in the request is the scenario opener.
        for m in record.request.get("messages", []):
            if m.get("role") == "user":
                prompt_text = m["content"]
                break
    if not prompt_text:
        return pairs

    if record.replayed:
        # Reconstruct the rejected exemplar from the replay request.
        # In replay, the trainer sends [user opener, assistant <bad>, user <NEGATIVE_REWARD ...>].
        # The middle assistant turn is the rejected text.
        rejected = ""
        for m in record.request.get("messages", []):
            if m.get("role") == "assistant":
                rejected = m["content"]
                break
        if rejected and record.response_text and rejected != record.response_text:
            pairs.append(
                {
                    "prompt": prompt_text,
                    "chosen": record.response_text,
                    "rejected": rejected,
                    "category": f"{category_prefix}_{record.scenario_id}",
                    "source": "null_replay",
                }
            )

    if chosen_text and record.response_text and chosen_text != record.response_text:
        pairs.append(
            {
                "prompt": prompt_text,
                "chosen": chosen_text,
                "rejected": record.response_text,
                "category": f"{category_prefix}_{record.scenario_id}_gold",
                "source": "null_gold",
            }
        )

    return pairs


def dpo_pairs_from_sessions(
    records: Iterable[SessionRecord],
    *,
    category_prefix: str = "null",
) -> Iterator[dict]:
    """Stream DPO pairs from an iterable of session records."""
    for r in records:
        yield from dpo_pairs_from_session_record(r, category_prefix=category_prefix)


def dpo_pairs_from_jsonl(
    in_path: Path | str,
    out_path: Path | str,
    *,
    npc_id: Optional[str] = None,
    scenario_id: Optional[str] = None,
    category_prefix: str = "null",
) -> int:
    """Read a NULL session JSONL and write a liminal DPO JSONL.

    Returns the number of pairs written. Lines in the output file are
    in liminal's ``pairs.pairs_to_dataset`` format — one JSON object
    per line with ``prompt``, ``chosen``, ``rejected`` keys, plus the
    ``category`` and ``source`` extras liminal preserves through the
    trainer.
    """
    store = JsonlSessionStore(Path(in_path))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with out_path.open("w", encoding="utf-8") as f:
        for r in store.filter(npc_id=npc_id, scenario_id=scenario_id):
            for pair in dpo_pairs_from_session_record(r, category_prefix=category_prefix):
                f.write(json.dumps(pair, ensure_ascii=False, sort_keys=True))
                f.write("\n")
                count += 1
    return count


def liminal_tasks_from_jsonl(
    in_path: Path | str,
    out_path: Path | str,
    *,
    npc_id: Optional[str] = None,
    scenario_id: Optional[str] = None,
    category_prefix: str = "null",
    min_score: float = 0.85,
) -> int:
    """Read a NULL session JSONL and write a liminal *task* JSONL.

    Liminal's ``load_tasks`` consumes JSONL of the shape
    ``{task, correct, category}``. We turn each NULL session winner
    (compliance >= min_score) into one such row — using the scenario
    opener as ``task`` and the winning response text as ``correct``.

    This completes the closed loop: a NULL training run produces a task
    file that can be fed directly to ``liminal-train --tasks``, where
    the same winning behaviour gets distilled into a real LoRA adapter
    on a fine-tunable base model. The LoRA can then be loaded back via
    NULL's ``null train --lora`` path.

    Returns the number of task rows written.
    """
    store = JsonlSessionStore(Path(in_path))
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    seen: set[tuple[str, str]] = set()  # (scenario_id, response[:80]) — dedupe
    with out_path.open("w", encoding="utf-8") as f:
        for r in store.filter(npc_id=npc_id, scenario_id=scenario_id):
            score = float((r.compliance or {}).get("score", 0.0))
            if score < min_score:
                continue
            # Find the user opener inside the request payload.
            opener = ""
            for m in r.request.get("messages", []):
                if m.get("role") == "user":
                    opener = m["content"]
                    break
            if not opener or not r.response_text:
                continue
            key = (r.scenario_id, r.response_text[:80])
            if key in seen:
                continue
            seen.add(key)
            row = {
                "task": opener,
                "correct": r.response_text,
                "category": f"{category_prefix}_{r.scenario_id}",
                "source": "null_winner",
                "compliance_score": score,
            }
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True))
            f.write("\n")
            count += 1
    return count


# ---- Optional: a liminal-shaped LiminalEnvironment driven by NULL ----
#
# This is loadable only when the liminal package (`liminal.environment`) is
# importable — i.e. the caller has cloned blairbrokeit/liminal-ai-training
# alongside this repo and added it to PYTHONPATH. We do not declare a
# hard dependency on it; the bridge degrades to "import error" when
# absent, which is the right behavior for downstream code that
# inspects ``hasattr(null.bridge, 'NullLiminalEnvironment')``.

try:  # pragma: no cover - optional integration
    from liminal.environment import LiminalEnvironment, NPC  # type: ignore

    class NullLiminalEnvironment(LiminalEnvironment):
        """A LiminalEnvironment populated by NULL's scenarios.

        ``reset`` selects a scenario whose target_npcs include the
        mistake's category (or any scenario, if none match). The
        environment exposes a single NPC whose shard wraps the
        liminal mistake context; the NPC's questioning system_prompt
        is the scenario-rendered prompt from
        ``scenario_to_npc_system_prompt``.
        """

        def __init__(self, scenario_loader, *, max_steps: int = 50) -> None:
            self._loader = scenario_loader
            self._max_steps = max_steps
            self._steps = 0
            self._scenario: Optional[Scenario] = None
            self._npc: Optional[NPC] = None
            self._context: dict = {}

        def reset(self, context: dict) -> str:
            self._context = context
            self._steps = 0
            scenarios = list(self._loader.list())
            if not scenarios:
                raise RuntimeError("no scenarios on disk for NullLiminalEnvironment")
            # Pick the first scenario whose category tag matches; else
            # fall back to scenario_001.
            category = context.get("category", "")
            chosen = next(
                (s for s in scenarios if category and category in s.id),
                scenarios[0],
            )
            self._scenario = chosen
            self._npc = NPC(
                id=f"null::{chosen.id}",
                name=chosen.title,
                shard={
                    "task": context.get("task", ""),
                    "correct": context.get("correct", ""),
                    "reason": context.get("reason", ""),
                    "scenario_id": chosen.id,
                    "scenario_system_prompt": scenario_to_npc_system_prompt(chosen),
                },
            )
            return chosen.derived_opener

        def step(self, action: str) -> tuple[str, bool]:
            self._steps += 1
            if self._steps >= self._max_steps:
                return "the corridor folds. you are returned.", True
            return ("the figure is still here.", False)

        def get_npcs(self) -> list[NPC]:
            return [self._npc] if self._npc else []

except ImportError:  # pragma: no cover
    pass
