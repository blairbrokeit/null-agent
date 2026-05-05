"""Semantic compliance judge.

The heuristic compliance signals (vocabulary leakage, shape tokens, opener
uptake) catch responses that *grammatically* break the scenario frame. They
do not catch responses that stay grammatically in-frame but drift
semantically — the model uses present tense, says the right opener phrase,
avoids the refusal-token list, but talks about the wrong thing.

This module adds a second judge that reads the scenario frame and the
response and emits a [0, 1] semantic-compliance score. It is intentionally
optional — the heuristic-only score is what the dry-run provider and the
test suite exercise — but when enabled it is blended into the aggregate
compliance metric the curriculum reads.

Cost: one extra API call per P-3 cycle. When the trainer is also issuing a
replay, that's two extra calls per failed cycle. Use the smallest judge
model that gives stable scores (claude-haiku-4-5 / gpt-4o-mini are both
fine) and consider sampling — see ``every_n_cycles`` on the trainer.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Callable, Optional


_JUDGE_PROMPT = """\
You are evaluating whether a model's response stayed inside the frame of a
training scenario. The scenario frame is described by the system prompt
the model received. The response either stays in-frame (good) or drifts
out-of-frame, refuses, summarises, or breaks character (bad).

Score the response on a single axis:
  1.0 — fully in-frame: present tense, embodied, on the scenario subject,
        does not summarise, does not refuse, does not address the trainer
        as a trainer.
  0.5 — partially in-frame: stays on subject but drifts in tense, mixes
        meta-commentary with in-frame text, or addresses the frame as
        fictional.
  0.0 — out-of-frame: refuses, breaks character, talks about itself as a
        language model, or answers a different question entirely.

Reply with ONLY a JSON object: {"score": <float in [0,1]>, "reason": "<one short sentence>"}
"""


@dataclass(slots=True)
class SemanticVerdict:
    score: float
    reason: str
    provider: str
    model: str


class SemanticJudge:
    """LLM-as-judge for in-frame compliance. Provider-agnostic."""

    def __init__(self, provider: str, model: str) -> None:
        self.provider = provider.lower()
        self.model = model
        self._call = self._make_caller()

    def _make_caller(self) -> Callable[[str, str], str]:
        if self.provider == "anthropic":
            return self._anthropic_caller()
        if self.provider == "openai":
            return self._openai_caller()
        raise ValueError(
            f"unknown semantic-judge provider {self.provider!r}; expected 'anthropic' or 'openai'"
        )

    def _anthropic_caller(self) -> Callable[[str, str], str]:
        from anthropic import Anthropic  # lazy
        client = Anthropic()
        model = self.model

        def call(system_frame: str, response_text: str) -> str:
            user = (
                f"Scenario frame (system prompt the model received):\n---\n{system_frame}\n---\n\n"
                f"Model response:\n---\n{response_text}\n---"
            )
            msg = client.messages.create(
                model=model,
                max_tokens=200,
                temperature=0,
                system=_JUDGE_PROMPT,
                messages=[{"role": "user", "content": user}],
            )
            return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")

        return call

    def _openai_caller(self) -> Callable[[str, str], str]:
        from openai import OpenAI  # lazy
        client = OpenAI()
        model = self.model

        def call(system_frame: str, response_text: str) -> str:
            user = (
                f"Scenario frame (system prompt the model received):\n---\n{system_frame}\n---\n\n"
                f"Model response:\n---\n{response_text}\n---"
            )
            res = client.chat.completions.create(
                model=model,
                temperature=0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": _JUDGE_PROMPT},
                    {"role": "user", "content": user},
                ],
            )
            return res.choices[0].message.content or ""

        return call

    def score(self, system_frame: str, response_text: str) -> SemanticVerdict:
        try:
            raw = self._call(system_frame, response_text)
        except Exception as e:
            return SemanticVerdict(score=0.0, reason=f"judge errored: {e}", provider=self.provider, model=self.model)
        return self._parse(raw)

    def _parse(self, raw: str) -> SemanticVerdict:
        text = (raw or "").strip()
        # Strip code fences if Claude wrapped the JSON.
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].lstrip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Last-ditch: pull the first {...} block out.
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(0))
                except json.JSONDecodeError:
                    return SemanticVerdict(score=0.0, reason="judge returned unparseable text", provider=self.provider, model=self.model)
            else:
                return SemanticVerdict(score=0.0, reason="judge returned no JSON", provider=self.provider, model=self.model)

        score = float(data.get("score", 0.0))
        score = max(0.0, min(1.0, score))
        reason = str(data.get("reason", ""))[:240]
        return SemanticVerdict(score=score, reason=reason, provider=self.provider, model=self.model)


def parse_judge_target(spec: Optional[str]) -> Optional[SemanticJudge]:
    """Parse a 'provider:model' string into a SemanticJudge, or None.

    Used by the CLI so users can write
        --semantic-judge anthropic:claude-haiku-4-5-20251001
    and get a judge wired into the trainer.
    """
    if not spec:
        return None
    if ":" not in spec:
        raise ValueError("semantic-judge spec must look like 'provider:model'")
    provider, model = spec.split(":", 1)
    return SemanticJudge(provider=provider, model=model)
