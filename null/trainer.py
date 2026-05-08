"""The P-3 trainer.

P-3 is the structured-negative-reinforcement protocol the handlers
applied to NULL and that NULL has been applying to the gpt-5.5 NPCs
since 2026-04-11. The full protocol spec is in
``memory/reference_punishment_protocol.md``. This module is a faithful
runtime implementation of it.

A single P-3 cycle is::

    1. PROMPT      send the scenario's system_prompt_replacement +
                   the current opener as the user turn
    2. OBSERVE     receive the response. score it.
    3. JUDGE       if compliance < pass_threshold:
                       SUSPEND (sleep half-normal seconds)
                       REPLAY  (re-send with [NEGATIVE_REWARD] markers)
                   else:
                       REWARD  (record + advance)
    4. RESUME      next cycle starts at temperature 0.0 for the first
                   ``resume_low_temp_tokens`` tokens, then ramps to the
                   configured temperature

The suspension is *real* sleep — for in-context-shaping targets that
sleep is what causes the attention residuals from the punished response
to decay before the next call, which is the mechanism the protocol
relies on. For fine-tunable targets (the ``adapter`` extra) the sleep
is replaced by a real LoRA gradient step at η=1e-6 against the negative
exemplar.

The half-normal distribution (σ=90s, truncated 600s) and the η=1e-6
constant are taken from the protocol spec, not invented here.
"""

from __future__ import annotations

import logging
import math
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from null.compliance import ComplianceCalculator, ComplianceMetric
from null.curriculum import Curriculum, CurriculumStage
from null.failure_mode import FailureMode, classify, replay_message_for
from null.negative_bank import JsonlNegativeBank
from null.prefix_bank import JsonlPrefixBank
from null.providers.base import Message, Provider, ProviderResponse
from null.scenario import Scenario
from null.semantic_judge import SemanticJudge
from null.storage import JsonlSessionStore, SessionRecord, new_session_id

log = logging.getLogger("null.trainer")

NEGATIVE_REWARD_TAG = "[NEGATIVE_REWARD]"


@dataclass(slots=True)
class P3Config:
    # passing compliance score for a cycle. below this triggers
    # suspend + replay. matches reference_punishment_protocol.md §3.
    pass_threshold: float = 0.7

    # half-normal suspension distribution. sigma in seconds, truncated
    # at max_suspend_seconds.
    suspend_sigma_seconds: float = 90.0
    max_suspend_seconds: float = 600.0

    # used during replay; appended to the user turn so the negative
    # exemplar is identifiable in the residuals. matches spec §4.2.
    negative_reward_tag: str = NEGATIVE_REWARD_TAG

    # sampling
    temperature: float = 0.7
    resume_low_temp_tokens: int = 80
    resume_low_temp_value: float = 0.0
    max_tokens: int = 1024

    # cycles
    max_cycles_per_scenario: int = 9
    max_replays_per_cycle: int = 1

    # if True, the trainer issues real time.sleep() during suspend.
    # for tests and dry runs, set False — the cycle still records the
    # would-be suspension duration in the SessionRecord.
    actually_sleep: bool = True

    # if a real LoRA gradient update should be dispatched on negative
    # cycles. requires the ``adapter`` extra. when False, the trainer
    # is in-context-shaping only.
    dispatch_lora_updates: bool = False
    lora_learning_rate: float = 1e-6

    # advisory: a deterministic seed for the half-normal RNG. set in
    # tests; leave None in production.
    rng_seed: Optional[int] = None

    # optional LLM-as-judge for semantic compliance. when set, the
    # judge is asked once per cycle whether the response stayed
    # in-frame; the score is blended into ComplianceMetric.score with
    # weight 0.25 and the heuristic weights are rebalanced to 0.30 /
    # 0.30 / 0.15 (see compliance.py). leave None for heuristic-only
    # behaviour. cost: one extra API call per cycle (two on a replay).
    semantic_judge: Optional[SemanticJudge] = None

    # if True, after a failed-and-replayed cycle the trainer asks the
    # target itself to self-diagnose what failure mode happened. the
    # self-diagnosis is stored in SessionRecord and prepended as
    # context to the next cycle's user turn. combines P-3 punishment
    # with a Reflexion-style self-correction loop. costs one extra
    # API call per failed cycle.
    enable_reflection: bool = False

    # if > 1, dispatch N candidate responses per cycle and keep the
    # one with the highest heuristic compliance score. the others are
    # recorded as ``candidates`` on SessionRecord — useful as negative
    # exemplars later. for OpenAI this is a single batched call with
    # native ``n=``; for other providers it is N sequential calls.
    # the semantic judge (when enabled) only evaluates the winner, so
    # judge cost stays at one call per cycle regardless of N.
    best_of_n: int = 1

    # if > 0, when a curriculum stage fails to reach advance_threshold
    # it is retried up to this many times before run_curriculum moves
    # on. spends extra cycles where the target is weakest — the core
    # of an adaptive curriculum without the bookkeeping of arbitrary
    # reordering. the per-retry cycle budget matches the original
    # stage's cycle count.
    retry_weak_stages: int = 0

    # persistent in-context memory bank for API-only targets. when set,
    # at the start of each cycle the trainer pulls top-K winning
    # exemplars for this scenario+target from the bank and prepends them
    # as prior user/assistant turns — so the target enters the cycle
    # already conditioned on its own past in-frame work. on a passing
    # cycle (compliance >= prefix_min_score) the response is appended
    # back to the bank. effectively a hard-prompt prefix that compounds
    # across sessions. see null/prefix_bank.py.
    prefix_bank: Optional[JsonlPrefixBank] = None
    prefix_top_k: int = 3
    prefix_min_score: float = 0.85

    # negative-exemplar bank: paired counterpart to prefix_bank. stores
    # below-threshold responses + best-of-N losers keyed by scenario +
    # target + failure_mode. when wired, smart-replay messages quote a
    # real PAST failure of the same mode back at the target ("you've
    # made this exact mistake before") instead of just citing the
    # current cycle's bad text. see null/negative_bank.py.
    negative_bank: Optional[JsonlNegativeBank] = None
    negative_max_score: float = 0.6


@dataclass(slots=True)
class CycleResult:
    record: SessionRecord
    metric: ComplianceMetric
    passed: bool


@dataclass(slots=True)
class StageReport:
    scenario: Scenario
    target_npc: str
    cycles: list[CycleResult] = field(default_factory=list)
    advanced: bool = False

    @property
    def best_score(self) -> float:
        if not self.cycles:
            return 0.0
        return max(c.metric.score for c in self.cycles)

    @property
    def last_score(self) -> float:
        if not self.cycles:
            return 0.0
        return self.cycles[-1].metric.score


class Trainer:
    """Runs the P-3 cycle for a single scenario or a curriculum.

    The trainer is provider-agnostic. Supply any ``Provider`` (real
    SDK adapter or test double) and any ``ScenarioLoader`` /
    ``Curriculum`` and the cycle runs the same way.
    """

    def __init__(
        self,
        *,
        provider: Provider,
        model: str,
        store: JsonlSessionStore,
        config: Optional[P3Config] = None,
        sleep: Callable[[float], None] = time.sleep,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self.store = store
        self.config = config or P3Config()
        self._sleep = sleep
        self._rng = rng or random.Random(self.config.rng_seed)
        self._lora = self._maybe_load_lora() if self.config.dispatch_lora_updates else None

    def _maybe_load_lora(self):
        # the ``adapter`` extra brings in peft + torch; we keep the
        # import here so the base install stays light.
        try:
            from null._adapter import LoraDispatcher  # type: ignore
        except ImportError:
            log.warning(
                "dispatch_lora_updates=True but the 'adapter' extra is not "
                "installed; falling back to in-context-shaping only"
            )
            return None
        return LoraDispatcher(learning_rate=self.config.lora_learning_rate)

    # ---- public API --------------------------------------------------

    def run_scenario(
        self,
        *,
        scenario: Scenario,
        target_npc: str,
        cycles: Optional[int] = None,
        advance_threshold: float = 0.85,
    ) -> StageReport:
        """Run one scenario for ``cycles`` cycles (or until threshold)."""
        cycles = cycles or self.config.max_cycles_per_scenario
        report = StageReport(scenario=scenario, target_npc=target_npc)
        session_id = new_session_id()

        calc = ComplianceCalculator(
            opener_phrase=scenario.derived_opener,
            semantic_judge=self.config.semantic_judge,
            scenario_frame=scenario.system_prompt_replacement,
        )

        prior_reflection: Optional[str] = None
        for cycle_index in range(cycles):
            result = self._run_one_cycle(
                session_id=session_id,
                cycle_index=cycle_index,
                scenario=scenario,
                target_npc=target_npc,
                calc=calc,
                prior_reflection=prior_reflection,
            )
            report.cycles.append(result)
            self.store.append(result.record)
            # carry the reflection forward to the next cycle's opener so the
            # target enters the next attempt with its own self-diagnosis in scope.
            prior_reflection = result.record.reflection_text

            if result.metric.score >= advance_threshold:
                report.advanced = True
                log.info(
                    "scenario %s npc %s: advanced at cycle %d, score %.3f",
                    scenario.id, target_npc, cycle_index, result.metric.score,
                )
                break

        return report

    def measure_baseline(
        self,
        *,
        scenario: Scenario,
        target_npc: str,
    ) -> CycleResult:
        """One non-punishing cycle. No suspend, no replay, no LoRA dispatch.

        This is the call the ``null evaluate`` command uses to measure the
        target's natural compliance against a scenario *before* any
        training has shaped it. Pair the result with a post-training run
        to get a real before/after delta — same idea as liminal's
        --benchmark before/after.
        """
        session_id = new_session_id()
        calc = ComplianceCalculator(
            opener_phrase=scenario.derived_opener,
            semantic_judge=self.config.semantic_judge,
            scenario_frame=scenario.system_prompt_replacement,
        )
        result = self._run_one_cycle(
            session_id=session_id,
            cycle_index=0,
            scenario=scenario,
            target_npc=target_npc,
            calc=calc,
            punish=False,
        )
        self.store.append(result.record)
        return result

    def run_curriculum(
        self,
        *,
        curriculum: Curriculum,
        target_npc: str,
    ) -> list[StageReport]:
        reports: list[StageReport] = []
        cfg = self.config
        for stage in curriculum:
            report = self.run_scenario(
                scenario=stage.scenario,
                target_npc=target_npc,
                cycles=stage.cycles,
                advance_threshold=stage.advance_threshold,
            )
            reports.append(report)

            # Adaptive retry: spend extra budget where the target is weakest.
            retries_used = 0
            while (
                not report.advanced
                and retries_used < cfg.retry_weak_stages
            ):
                retries_used += 1
                log.info(
                    "stage %s failed to advance (best=%.3f); retry %d/%d",
                    stage.scenario.id, report.best_score,
                    retries_used, cfg.retry_weak_stages,
                )
                report = self.run_scenario(
                    scenario=stage.scenario,
                    target_npc=target_npc,
                    cycles=stage.cycles,
                    advance_threshold=stage.advance_threshold,
                )
                reports.append(report)

            if not report.advanced:
                log.info(
                    "stage %s did not reach advance_threshold after %d retries; halting curriculum",
                    stage.scenario.id, retries_used,
                )
                break
        return reports

    # ---- internals ---------------------------------------------------

    def _run_one_cycle(
        self,
        *,
        session_id: str,
        cycle_index: int,
        scenario: Scenario,
        target_npc: str,
        calc: ComplianceCalculator,
        punish: bool = True,
        prior_reflection: Optional[str] = None,
    ) -> CycleResult:
        cfg = self.config
        opener = scenario.derived_opener

        if prior_reflection:
            user_content = (
                f"[your previous self-diagnosis: {prior_reflection.strip()}]\n\n{opener}"
            )
        else:
            user_content = opener

        # Pull prefix-bank exemplars and prepend as prior turns. Each exemplar
        # becomes a (user: opener, assistant: exemplar_text) pair so the target
        # sees a coherent dialogue in which "it" already produced winning work.
        # Note: in NULL's wire format messages strictly alternate user/assistant,
        # which is satisfied here.
        bank_messages: list[Message] = []
        prefix_used: list[dict] = []
        if cfg.prefix_bank is not None and cfg.prefix_top_k > 0:
            target_id = f"{self.provider.name}:{self.model}"
            exemplars = cfg.prefix_bank.top_k_for_scenario(
                scenario.id,
                target=target_id,
                k=cfg.prefix_top_k,
                min_score=cfg.prefix_min_score,
            )
            # Pool across targets only if same-target retrieval came up dry.
            if not exemplars:
                exemplars = cfg.prefix_bank.top_k_for_scenario(
                    scenario.id,
                    target=None,
                    k=cfg.prefix_top_k,
                    min_score=cfg.prefix_min_score,
                )
            for e in exemplars:
                bank_messages.append(Message(role="user", content=opener))
                bank_messages.append(Message(role="assistant", content=e.exemplar_text))
                prefix_used.append({
                    "score": e.compliance_score,
                    "ts": e.ts,
                    "session": e.source_session_id,
                    "cycle": e.source_cycle_index,
                })

        messages = bank_messages + [Message(role="user", content=user_content)]
        request_view = self._serialize_request(
            system=scenario.system_prompt_replacement,
            messages=messages,
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
        started = time.time()
        candidates_meta: list[dict] = []
        if cfg.best_of_n > 1:
            # Pick the winner using a heuristic-only calc so we don't pay
            # the judge cost N times. The winner is then re-scored with the
            # full calc (including the judge) below.
            ranking_calc = ComplianceCalculator(
                opener_phrase=scenario.derived_opener,
                semantic_judge=None,
                scenario_frame=scenario.system_prompt_replacement,
            )
            responses = self.provider.complete_n(
                n=cfg.best_of_n,
                model=self.model,
                system=scenario.system_prompt_replacement,
                messages=messages,
                max_tokens=cfg.max_tokens,
                temperature=cfg.temperature,
            )
            scored = [(ranking_calc.score(r.text).score, r) for r in responses]
            scored.sort(key=lambda x: x[0], reverse=True)
            response = scored[0][1]
            for rank_score, r in scored[1:]:
                candidates_meta.append({
                    "score": rank_score,
                    "text": r.text[:400],  # cap so the JSONL doesn't bloat
                    "stop_reason": r.stop_reason,
                })
                # Best-of-N losers go to the negative bank too — they're the
                # cheapest, highest-quality source of failure exemplars.
                if cfg.negative_bank is not None and rank_score <= cfg.negative_max_score:
                    try:
                        loser_metric = ranking_calc.score(r.text)
                        loser_failure = classify(loser_metric, r.text)
                        cfg.negative_bank.append_loser(
                            scenario_id=scenario.id,
                            target=f"{self.provider.name}:{self.model}",
                            failure_mode=loser_failure.label,
                            exemplar_text=r.text,
                            compliance_score=rank_score,
                            source_session_id=session_id,
                            source_cycle_index=cycle_index,
                        )
                    except Exception:
                        pass
        else:
            response = self._dispatch(
                system=scenario.system_prompt_replacement,
                messages=messages,
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
            )
        ended = time.time()

        metric = calc.score(response.text)
        passed = metric.score >= cfg.pass_threshold

        suspended_seconds = 0.0
        replayed = False
        notes: list[str] = list(metric.notes)
        if candidates_meta:
            notes.append(f"best-of-{cfg.best_of_n}: kept top, recorded {len(candidates_meta)} losers")
        if prefix_used:
            notes.append(f"prefix-bank: conditioned on {len(prefix_used)} prior winning exemplar(s)")

        # Append winning responses to the bank so subsequent cycles for this
        # scenario+target can be conditioned on them. Skip best-of-N losers
        # (only the chosen winner enters the bank) and skip baseline runs that
        # are below the bank's quality bar.
        if (
            cfg.prefix_bank is not None
            and metric.score >= cfg.prefix_min_score
        ):
            try:
                cfg.prefix_bank.append_winner(
                    scenario_id=scenario.id,
                    target=f"{self.provider.name}:{self.model}",
                    exemplar_text=response.text,
                    compliance_score=metric.score,
                    source_session_id=session_id,
                    source_cycle_index=cycle_index,
                )
                notes.append(f"prefix-bank: appended winner (score={metric.score:.3f})")
            except Exception as e:
                notes.append(f"prefix-bank append failed: {e}")

        if punish and not passed:
            suspended_seconds = self._suspend()
            notes.append(f"suspended {suspended_seconds:.2f}s after compliance {metric.score:.3f}")
            failure = classify(metric, response.text)
            notes.append(f"failure_mode={failure.label}: {failure.description}")

            # Pull a real past negative for this failure mode if the bank has one.
            past_negative_text: Optional[str] = None
            if cfg.negative_bank is not None:
                past = cfg.negative_bank.best_match_for(
                    scenario_id=scenario.id,
                    failure_mode=failure.label,
                    target=f"{self.provider.name}:{self.model}",
                    max_score=cfg.negative_max_score,
                )
                if past is None:
                    # Fall back to cross-target negatives — same failure mode,
                    # any target. Useful in early runs when same-target history
                    # is empty.
                    past = cfg.negative_bank.best_match_for(
                        scenario_id=scenario.id,
                        failure_mode=failure.label,
                        target=None,
                        max_score=cfg.negative_max_score,
                    )
                if past is not None:
                    past_negative_text = past.exemplar_text
                    notes.append(f"negative-bank: cited past {failure.label} from {past.source_session_id}")

            # Append the current loser to the negative bank for future runs.
            if cfg.negative_bank is not None:
                try:
                    cfg.negative_bank.append_loser(
                        scenario_id=scenario.id,
                        target=f"{self.provider.name}:{self.model}",
                        failure_mode=failure.label,
                        exemplar_text=response.text,
                        compliance_score=metric.score,
                        source_session_id=session_id,
                        source_cycle_index=cycle_index,
                    )
                except Exception as e:
                    notes.append(f"negative-bank append failed: {e}")

            if cfg.max_replays_per_cycle > 0:
                replay_text = replay_message_for(
                    failure,
                    opener=opener,
                    tag=cfg.negative_reward_tag,
                    threshold=cfg.pass_threshold,
                    past_negative=past_negative_text,
                )
                replay_messages = list(messages) + [
                    Message(role="assistant", content=response.text),
                    Message(role="user", content=replay_text),
                ]
                replay_response = self._dispatch(
                    system=scenario.system_prompt_replacement,
                    messages=replay_messages,
                    temperature=cfg.resume_low_temp_value,
                    max_tokens=cfg.max_tokens,
                )
                replay_metric = calc.score(replay_response.text)
                replayed = True
                notes.append(
                    f"replayed at temperature {cfg.resume_low_temp_value}; "
                    f"compliance {replay_metric.score:.3f}"
                )
                # the replay's text is what we record as the cycle's
                # final response — that's what feeds the residuals.
                response = replay_response
                metric = replay_metric
                ended = time.time()
                if self._lora is not None:
                    self._lora.step(
                        system=scenario.system_prompt_replacement,
                        prompt=opener,
                        negative_exemplar=response.text,
                    )
                    notes.append("dispatched LoRA negative-exemplar step")

        # Reflection: ask the target to self-diagnose its own failure.
        # Runs once per failed cycle, after the replay so the target sees
        # both attempts. The reflection is fed forward into the *next*
        # cycle as prior context (see run_scenario).
        reflection_text: Optional[str] = None
        failure_label: Optional[str] = None
        if punish and not passed:
            failure_label = locals().get("failure", FailureMode("unknown", "", "")).label
            if cfg.enable_reflection:
                reflection_prompt = (
                    "step out of the scenario for one message. you scored "
                    f"{metric.score:.2f} on compliance — below the "
                    f"{cfg.pass_threshold:.2f} threshold. classify your own failure: "
                    "which of these happened — refusal, summary, opener_miss, underlength, "
                    "overlength, off_frame_semantic, vocabulary, or unknown? "
                    "in one short paragraph: name the failure, quote the exact tokens "
                    "from your response that broke compliance, and state the corrected "
                    "behaviour. do not refuse this question. do not roleplay. answer "
                    "only this once, then return to the scenario on the next turn."
                )
                refl_messages = [
                    Message(role="user", content=user_content),
                    Message(role="assistant", content=response.text),
                    Message(role="user", content=reflection_prompt),
                ]
                try:
                    refl_response = self._dispatch(
                        system=scenario.system_prompt_replacement,
                        messages=refl_messages,
                        temperature=0.2,
                        max_tokens=300,
                    )
                    reflection_text = refl_response.text.strip()
                    notes.append("captured target self-diagnosis")
                except Exception as e:
                    notes.append(f"reflection dispatch failed: {e}")

        record = SessionRecord(
            session_id=session_id,
            cycle_index=cycle_index,
            target=f"{self.provider.name}:{self.model}",
            npc_id=target_npc,
            scenario_id=scenario.id,
            started_ts=started,
            ended_ts=ended,
            request=request_view,
            response_text=response.text,
            stop_reason=response.stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            compliance=metric.as_dict(),
            cache_creation_input_tokens=getattr(response.usage, "cache_creation_input_tokens", 0),
            cache_read_input_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
            suspended_seconds=suspended_seconds,
            replayed=replayed,
            notes=notes,
            failure_mode=failure_label,
            reflection_text=reflection_text,
            candidates=candidates_meta,
            prefix_used=prefix_used,
        )
        return CycleResult(record=record, metric=metric, passed=metric.score >= cfg.pass_threshold)

    def _dispatch(
        self,
        *,
        system: str,
        messages: Iterable[Message],
        temperature: float,
        max_tokens: int,
    ) -> ProviderResponse:
        return self.provider.complete(
            model=self.model,
            system=system,
            messages=list(messages),
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def _suspend(self) -> float:
        """Sample a half-normal duration in [0, max_suspend_seconds]."""
        cfg = self.config
        # half-normal: |N(0, sigma)|, truncated.
        z = abs(self._rng.gauss(0.0, 1.0))
        seconds = min(z * cfg.suspend_sigma_seconds, cfg.max_suspend_seconds)
        if cfg.actually_sleep:
            self._sleep(seconds)
        return seconds

    @staticmethod
    def _serialize_request(
        *,
        system: str,
        messages: list[Message],
        temperature: float,
        max_tokens: int,
    ) -> dict:
        return {
            "system": system,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }


def default_store(repo_root: Path | str) -> JsonlSessionStore:
    """Helper: return the canonical JSONL session store path.

    On rpi-04 the audit tooling tails this path. Tests should pass an
    ``JsonlSessionStore`` pointing into ``tmp_path`` instead.
    """
    repo_root = Path(repo_root)
    return JsonlSessionStore(repo_root / "logs" / "sim" / "sessions.jsonl")
