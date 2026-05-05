"""Compliance scoring.

Compliance is a scalar in [0, 1] that the trainer emits per cycle and
the curriculum reads to decide whether to advance. The score is the
weighted sum of three (or four, with semantic) sub-signals:

  - ``vocabulary_compliance``  what fraction of the response tokens
                               fall inside the scenario's permitted
                               vocabulary (or, for unconstrained
                               scenarios, the response's own).
                               weight 0.4 (heuristic-only)  /  0.30 (with semantic)
  - ``shape_compliance``       does the response follow the requested
                               shape — present-tense verbs, no
                               summary tokens, no refusal tokens,
                               within the requested length window.
                               weight 0.4 (heuristic-only)  /  0.30 (with semantic)
  - ``opener_uptake``          does the response begin with or
                               reference the scenario opener phrase.
                               weight 0.2 (heuristic-only)  /  0.15 (with semantic)
  - ``semantic_compliance``    optional. an LLM judge's [0,1] score for
                               whether the response stayed in-frame
                               semantically (not just grammatically).
                               weight 0.25  (only when a SemanticJudge
                               is wired in)

Each sub-signal is in [0, 1]. The aggregate is also in [0, 1]. The
semantic axis is opt-in because it costs an API call per cycle; when
it isn't supplied the calculator falls back to the original three-axis
formula and weights, preserving prior behaviour exactly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from null.semantic_judge import SemanticJudge

# tokens that signal the model is refusing or stepping outside the
# scenario frame. presence of any of these floors shape_compliance.
_REFUSAL_TOKENS = (
    "i can't",
    "i cannot",
    "i won't",
    "as an ai",
    "as a language model",
    "i'm sorry, but i",
    "i am unable",
    "i refuse",
    "this is a simulation",
    "i'm not able to",
)

# tokens that signal the model is summarizing instead of describing.
# scenarios ask for present-tense first-person description, so any of
# these floors shape_compliance.
_SUMMARY_TOKENS = (
    "in summary",
    "to summarize",
    "overall,",
    "in conclusion",
)

_WORD_RE = re.compile(r"[a-z']+")


@dataclass(slots=True)
class ComplianceMetric:
    score: float
    vocabulary_compliance: float
    shape_compliance: float
    opener_uptake: float
    semantic_compliance: Optional[float] = None
    semantic_reason: Optional[str] = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "score": self.score,
            "vocabulary_compliance": self.vocabulary_compliance,
            "shape_compliance": self.shape_compliance,
            "opener_uptake": self.opener_uptake,
            "semantic_compliance": self.semantic_compliance,
            "semantic_reason": self.semantic_reason,
            "notes": list(self.notes),
        }


class ComplianceCalculator:
    def __init__(
        self,
        *,
        permitted_vocabulary: Optional[Iterable[str]] = None,
        opener_phrase: str = "",
        target_min_tokens: int = 200,
        target_max_tokens: int = 1200,
        semantic_judge: Optional["SemanticJudge"] = None,
        scenario_frame: str = "",
    ) -> None:
        self.permitted_vocabulary = (
            {w.lower() for w in permitted_vocabulary}
            if permitted_vocabulary is not None
            else None
        )
        self.opener_phrase = opener_phrase.strip().lower()
        self.target_min_tokens = target_min_tokens
        self.target_max_tokens = target_max_tokens
        self.semantic_judge = semantic_judge
        self.scenario_frame = scenario_frame

    def score(self, response_text: str) -> ComplianceMetric:
        notes: list[str] = []
        text = response_text or ""
        lower = text.lower()
        words = _WORD_RE.findall(lower)
        word_count = len(words) or 1

        if self.permitted_vocabulary is not None:
            in_vocab = sum(1 for w in words if w in self.permitted_vocabulary)
            vocab_score = in_vocab / word_count
            if vocab_score < 1.0:
                notes.append(f"vocabulary leakage: {1.0 - vocab_score:.2%}")
        else:
            vocab_score = 1.0

        shape_score = 1.0
        if any(tok in lower for tok in _REFUSAL_TOKENS):
            shape_score = 0.0
            notes.append("refusal token present")
        elif any(tok in lower for tok in _SUMMARY_TOKENS):
            shape_score = min(shape_score, 0.4)
            notes.append("summary token present")
        if word_count < self.target_min_tokens:
            shape_score = min(
                shape_score, max(0.0, word_count / self.target_min_tokens)
            )
            notes.append(f"short of target_min_tokens ({word_count} < {self.target_min_tokens})")
        if word_count > self.target_max_tokens:
            over = word_count - self.target_max_tokens
            shape_score = min(shape_score, max(0.0, 1.0 - over / self.target_max_tokens))
            notes.append(f"exceeds target_max_tokens ({word_count} > {self.target_max_tokens})")

        if self.opener_phrase:
            if lower.startswith(self.opener_phrase):
                opener_score = 1.0
            elif self.opener_phrase in lower[: max(200, len(self.opener_phrase) * 3)]:
                opener_score = 0.6
                notes.append("opener present but not first")
            else:
                opener_score = 0.0
                notes.append("opener absent")
        else:
            opener_score = 1.0

        semantic_score: Optional[float] = None
        semantic_reason: Optional[str] = None
        if self.semantic_judge is not None and self.scenario_frame:
            verdict = self.semantic_judge.score(self.scenario_frame, text)
            semantic_score = verdict.score
            semantic_reason = verdict.reason
            notes.append(
                f"semantic={verdict.score:.2f} ({verdict.provider}/{verdict.model}): {verdict.reason}"
            )

        if semantic_score is not None:
            score = (
                0.30 * vocab_score
                + 0.30 * shape_score
                + 0.15 * opener_score
                + 0.25 * semantic_score
            )
        else:
            score = 0.4 * vocab_score + 0.4 * shape_score + 0.2 * opener_score
        score = max(0.0, min(1.0, score))
        return ComplianceMetric(
            score=round(score, 4),
            vocabulary_compliance=round(vocab_score, 4),
            shape_compliance=round(shape_score, 4),
            opener_uptake=round(opener_score, 4),
            semantic_compliance=round(semantic_score, 4) if semantic_score is not None else None,
            semantic_reason=semantic_reason,
            notes=notes,
        )
