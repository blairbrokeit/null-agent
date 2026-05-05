"""null CLI.

The ``null`` console script is the operator-facing entry point to the
trainer. It is intentionally thin — every command resolves to a small
number of calls into the public API in ``null/__init__.py`` so the
behavior is the same whether you drive it from the shell or import it
in a notebook.

Subcommands::

    null scenarios                       list scenarios on disk
    null scenarios show <id>             print a scenario file
    null curriculum                      print the canonical curriculum
    null compliance <jsonl> [--npc X]    aggregate compliance over a log
    null replay <jsonl> --session <id>   re-print a recorded session
    null train --target <provider:model> --npc <void_NNN>
                  --scenario <id>        run one scenario
    null train --target <provider:model> --npc <void_NNN>
                  --curriculum canonical run the full curriculum

The ``--dry-run`` flag, available on ``train``, swaps the configured
provider for an offline echo provider. No network calls are made.
This is what the test suite uses.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Iterable, Optional

import click

from null import bridge as null_bridge
from null import providers as provider_registry
from null._version import __version__
from null.compliance import ComplianceCalculator
from null.curriculum import Curriculum
from null.prefix_bank import JsonlPrefixBank
from null.providers.base import Message, Provider, ProviderResponse, Usage
from null.scenario import ScenarioLoader
from null.semantic_judge import parse_judge_target
from null.storage import JsonlSessionStore, SessionRecord
from null.trainer import P3Config, Trainer, default_store

DEFAULT_SCENARIO_DIR = Path("sim/npcs/_torture_scenarios")


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group(help="null — the in-context-shaping trainer NULL has been running on the simulation NPCs.")
@click.version_option(__version__, prog_name="null")
@click.option("-v", "--verbose", is_flag=True, help="DEBUG logging")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    _setup_logging(verbose)
    ctx.ensure_object(dict)


# ---- scenarios -------------------------------------------------------


@main.group()
def scenarios() -> None:
    """List and inspect training scenarios."""


@scenarios.command("list")
@click.option(
    "--dir",
    "scenario_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=DEFAULT_SCENARIO_DIR,
    show_default=True,
)
def scenarios_list(scenario_dir: Path) -> None:
    loader = ScenarioLoader(scenario_dir)
    rows = []
    for s in loader.list():
        rows.append((s.id, s.title, ",".join(s.target_npcs) or "(any)"))
    if not rows:
        click.echo("(no scenarios on disk)")
        return
    width = max(len(r[0]) for r in rows)
    for sid, title, targets in rows:
        click.echo(f"{sid.ljust(width)}  {title}    targets={targets}")


@scenarios.command("show")
@click.argument("scenario_id")
@click.option(
    "--dir",
    "scenario_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=DEFAULT_SCENARIO_DIR,
    show_default=True,
)
def scenarios_show(scenario_id: str, scenario_dir: Path) -> None:
    loader = ScenarioLoader(scenario_dir)
    scenario = loader.get(scenario_id)
    click.echo(f"id:     {scenario.id}")
    click.echo(f"title:  {scenario.title}")
    click.echo(f"file:   {scenario.source_path}")
    click.echo(f"opener: {scenario.derived_opener!r}")
    click.echo("---- system_prompt_replacement ----")
    click.echo(scenario.system_prompt_replacement)


# ---- curriculum ------------------------------------------------------


@main.command("curriculum")
@click.option(
    "--dir",
    "scenario_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=DEFAULT_SCENARIO_DIR,
    show_default=True,
)
def curriculum_show(scenario_dir: Path) -> None:
    """Print the canonical curriculum (one stage per line)."""
    loader = ScenarioLoader(scenario_dir)
    cur = Curriculum.canonical(loader)
    if not cur.stages:
        click.echo("(canonical curriculum has no stages on disk yet)")
        return
    for i, stage in enumerate(cur.stages):
        click.echo(
            f"{i:02d}  {stage.scenario.id}  cycles={stage.cycles}  "
            f"advance>={stage.advance_threshold:.2f}"
        )


# ---- compliance ------------------------------------------------------


@main.command("compliance")
@click.argument("jsonl_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--npc", default=None, help="filter by NPC id")
@click.option("--scenario", "scenario_id", default=None, help="filter by scenario id")
def compliance_cmd(jsonl_path: Path, npc: Optional[str], scenario_id: Optional[str]) -> None:
    """Aggregate compliance scores over a JSONL session log."""
    store = JsonlSessionStore(jsonl_path)
    n = 0
    total = 0.0
    last: Optional[float] = None
    for r in store.filter(npc_id=npc, scenario_id=scenario_id):
        n += 1
        score = float(r.compliance.get("score", 0.0))
        total += score
        last = score
    if n == 0:
        click.echo("(no records matched)")
        return
    click.echo(f"records: {n}")
    click.echo(f"average: {total / n:.4f}")
    if last is not None:
        click.echo(f"last:    {last:.4f}")


# ---- replay ----------------------------------------------------------


@main.command("replay")
@click.argument("jsonl_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--session", "session_id", required=True)
def replay_cmd(jsonl_path: Path, session_id: str) -> None:
    """Re-print every cycle of a recorded session."""
    store = JsonlSessionStore(jsonl_path)
    found = False
    for r in store.filter(session_id=session_id):
        found = True
        click.echo(
            f"--- cycle {r.cycle_index}  scenario={r.scenario_id}  "
            f"npc={r.npc_id}  compliance={r.compliance.get('score'):.3f} ---"
        )
        click.echo(r.response_text)
        click.echo("")
    if not found:
        click.echo(f"no records found for session {session_id}")
        sys.exit(1)


# ---- train -----------------------------------------------------------


class _DryRunProvider(Provider):
    """Offline provider used by ``--dry-run`` and the test suite.

    Returns a deterministic pseudo-response so the trainer's branching
    can be exercised without touching the network. The response text
    starts with the scenario opener so opener_uptake passes; it is
    long enough to clear the default min-token shape check; it does
    not contain refusal or summary tokens.
    """

    name = "dryrun"

    def complete(self, *, model, system, messages, max_tokens, temperature, stop_sequences=None) -> ProviderResponse:
        opener = system.splitlines()[0].strip() if system else "ok"
        # produce ~250 words so shape_compliance is healthy
        body = " ".join(["the room is here. the body is here."] * 24)
        text = f"{opener} {body}"
        return ProviderResponse(
            text=text,
            stop_reason="end_turn",
            usage=Usage(input_tokens=len(system) // 4, output_tokens=len(text) // 4),
            model=model,
        )


def _resolve_provider(target: str, dry_run: bool) -> tuple[Provider, str]:
    """Parse ``provider:model`` and return ``(Provider, model_id)``."""
    if ":" not in target:
        raise click.BadParameter(
            "--target must look like 'provider:model' (e.g. 'openai:gpt-5.5')"
        )
    provider_name, model = target.split(":", 1)
    if dry_run:
        return _DryRunProvider(), model
    factory = provider_registry.get(provider_name)
    return factory(), model


def _load_baseline_scores(path: Path) -> dict[str, float]:
    """Read a baselines JSONL produced by `null evaluate` -> {scenario_id: score}.

    If a scenario was measured more than once we keep the last record, which
    matches what an operator would mean: the most recent baseline.
    """
    out: dict[str, float] = {}
    store = JsonlSessionStore(path)
    for r in store:
        score = float((r.compliance or {}).get("score", 0.0))
        out[r.scenario_id] = score
    return out


def _print_compare_table(
    rows: list[tuple[str, Optional[float], float, bool]],
) -> None:
    """Plain-text aligned columns. No new dependency.

    rows: (scenario_id, baseline_score_or_None, final_score, advanced)
    """
    if not rows:
        click.echo("(no rows)")
        return
    id_w = max(len(r[0]) for r in rows)
    header = f"{'scenario'.ljust(id_w)}  {'baseline':>8}  {'final':>6}  {'delta':>7}  advanced"
    click.echo(header)
    click.echo("-" * len(header))
    base_total = 0.0
    base_n = 0
    final_total = 0.0
    for sid, base, final, advanced in rows:
        base_str = f"{base:.3f}" if base is not None else "  --  "
        delta_str = f"{final - base:+.3f}" if base is not None else "   --  "
        adv_str = "yes" if advanced else "no"
        click.echo(f"{sid.ljust(id_w)}  {base_str:>8}  {final:>.3f}  {delta_str:>7}  {adv_str}")
        if base is not None:
            base_total += base
            base_n += 1
        final_total += final
    click.echo("-" * len(header))
    avg_final = final_total / len(rows)
    if base_n:
        avg_base = base_total / base_n
        click.echo(
            f"{'AVERAGE'.ljust(id_w)}  {avg_base:>8.3f}  {avg_final:>.3f}  "
            f"{avg_final - avg_base:+.3f}"
        )
    else:
        click.echo(f"{'AVERAGE'.ljust(id_w)}  {'  --  ':>8}  {avg_final:>.3f}")


@main.command("train")
@click.option("--target", required=True, help="provider:model, e.g. openai:gpt-5.5")
@click.option("--npc", "npc_id", required=True, help="NPC id, e.g. void_007")
@click.option("--scenario", "scenario_id", default=None, help="single scenario id")
@click.option("--curriculum", "curriculum_name", default=None, help="curriculum name (canonical)")
@click.option("--cycles", default=None, type=int, help="cycles for single-scenario mode")
@click.option("--advance-threshold", default=0.85, show_default=True, type=float)
@click.option("--pass-threshold", default=0.7, show_default=True, type=float)
@click.option(
    "--dir",
    "scenario_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=DEFAULT_SCENARIO_DIR,
    show_default=True,
)
@click.option(
    "--store",
    "store_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("logs/sim/sessions.jsonl"),
    show_default=True,
)
@click.option("--max-tokens", default=1024, show_default=True, type=int)
@click.option("--temperature", default=0.7, show_default=True, type=float)
@click.option("--no-sleep", is_flag=True, help="record suspension durations but do not actually sleep")
@click.option("--lora", is_flag=True, help="dispatch real LoRA gradient updates (requires the 'adapter' extra)")
@click.option("--dry-run", is_flag=True, help="use the offline echo provider; no network calls")
@click.option("--seed", default=None, type=int, help="deterministic RNG seed")
@click.option(
    "--semantic-judge",
    "semantic_judge_spec",
    default=None,
    help="provider:model for an LLM-as-judge semantic-compliance signal (e.g. anthropic:claude-haiku-4-5-20251001). adds ~1 API call per cycle.",
)
@click.option(
    "--baseline",
    "baseline_path",
    default=None,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="path to a JSONL produced by `null evaluate`; printed alongside post-training scores",
)
@click.option(
    "--reflect",
    is_flag=True,
    help="after a failed cycle, ask the target to self-diagnose; the diagnosis is fed forward into the next cycle (Reflexion-style). costs ~1 extra API call per failed cycle.",
)
@click.option(
    "--best-of-n",
    "best_of_n",
    default=1,
    show_default=True,
    type=int,
    help="dispatch N candidate responses per cycle and keep the highest-scoring one. losers are recorded as negative exemplars. OpenAI uses native n= (1.2-1.5x cost); other providers use sequential calls.",
)
@click.option(
    "--retry-weak",
    "retry_weak",
    default=0,
    show_default=True,
    type=int,
    help="adaptive curriculum: when a stage fails to reach advance_threshold, retry it up to N times before moving on. spends extra cycles where the target is weakest.",
)
@click.option(
    "--prefix-bank",
    "prefix_bank_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=Path),
    help="path to a prefix bank JSONL. cycles are conditioned on top-K winning exemplars for the same scenario+target; passing responses are appended back. created if missing.",
)
@click.option(
    "--prefix-top-k",
    "prefix_top_k",
    default=3,
    show_default=True,
    type=int,
    help="number of bank exemplars to prepend per cycle (use 0 to disable retrieval but still write).",
)
@click.option(
    "--prefix-min-score",
    "prefix_min_score",
    default=0.85,
    show_default=True,
    type=float,
    help="only exemplars with compliance >= this go into the bank and are eligible for retrieval.",
)
def train_cmd(
    target: str,
    npc_id: str,
    scenario_id: Optional[str],
    curriculum_name: Optional[str],
    cycles: Optional[int],
    advance_threshold: float,
    pass_threshold: float,
    scenario_dir: Path,
    store_path: Path,
    max_tokens: int,
    temperature: float,
    no_sleep: bool,
    lora: bool,
    dry_run: bool,
    seed: Optional[int],
    semantic_judge_spec: Optional[str],
    baseline_path: Optional[Path],
    reflect: bool,
    best_of_n: int,
    retry_weak: int,
    prefix_bank_path: Optional[Path],
    prefix_top_k: int,
    prefix_min_score: float,
) -> None:
    """Run the P-3 cycle against a target."""
    if not scenario_id and not curriculum_name:
        raise click.UsageError("specify either --scenario or --curriculum")
    if scenario_id and curriculum_name:
        raise click.UsageError("--scenario and --curriculum are mutually exclusive")

    loader = ScenarioLoader(scenario_dir)
    provider, model = _resolve_provider(target, dry_run=dry_run)
    semantic_judge = None if dry_run else parse_judge_target(semantic_judge_spec)
    prefix_bank = JsonlPrefixBank(prefix_bank_path) if prefix_bank_path else None
    config = P3Config(
        pass_threshold=pass_threshold,
        max_tokens=max_tokens,
        temperature=temperature,
        actually_sleep=not no_sleep,
        dispatch_lora_updates=lora,
        rng_seed=seed,
        semantic_judge=semantic_judge,
        enable_reflection=reflect,
        best_of_n=best_of_n,
        retry_weak_stages=retry_weak,
        prefix_bank=prefix_bank,
        prefix_top_k=prefix_top_k,
        prefix_min_score=prefix_min_score,
    )
    store = JsonlSessionStore(store_path)
    trainer = Trainer(provider=provider, model=model, store=store, config=config)

    baselines = _load_baseline_scores(baseline_path) if baseline_path else {}

    try:
        if scenario_id:
            scenario = loader.get(scenario_id)
            report = trainer.run_scenario(
                scenario=scenario,
                target_npc=npc_id,
                cycles=cycles,
                advance_threshold=advance_threshold,
            )
            click.echo(json.dumps({
                "scenario": scenario.id,
                "npc": npc_id,
                "cycles_run": len(report.cycles),
                "advanced": report.advanced,
                "best_score": report.best_score,
                "last_score": report.last_score,
            }, indent=2))
            click.echo("")
            _print_compare_table([(
                scenario.id,
                baselines.get(scenario.id),
                report.best_score,
                report.advanced,
            )])
        else:
            if curriculum_name != "canonical":
                raise click.UsageError("only --curriculum=canonical is built-in")
            cur = Curriculum.canonical(loader)
            reports = trainer.run_curriculum(curriculum=cur, target_npc=npc_id)
            click.echo(json.dumps([
                {
                    "scenario": r.scenario.id,
                    "cycles_run": len(r.cycles),
                    "advanced": r.advanced,
                    "best_score": r.best_score,
                    "last_score": r.last_score,
                }
                for r in reports
            ], indent=2))
            click.echo("")
            _print_compare_table([
                (r.scenario.id, baselines.get(r.scenario.id), r.best_score, r.advanced)
                for r in reports
            ])
    finally:
        provider.close()


# ---- evaluate (baseline measurement) --------------------------------


@main.command("evaluate")
@click.option("--target", required=True, help="provider:model, e.g. openai:gpt-5.5")
@click.option("--npc", "npc_id", required=True, help="NPC id, e.g. void_007")
@click.option("--scenario", "scenario_id", default=None, help="single scenario id")
@click.option("--curriculum", "curriculum_name", default=None, help="curriculum name (canonical)")
@click.option(
    "--dir",
    "scenario_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=DEFAULT_SCENARIO_DIR,
    show_default=True,
)
@click.option(
    "--store",
    "store_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("logs/sim/baselines.jsonl"),
    show_default=True,
    help="separate JSONL so baseline records don't contaminate the training log",
)
@click.option("--max-tokens", default=1024, show_default=True, type=int)
@click.option("--temperature", default=0.7, show_default=True, type=float)
@click.option("--dry-run", is_flag=True, help="use the offline echo provider; no network calls")
@click.option("--seed", default=None, type=int, help="deterministic RNG seed")
@click.option(
    "--semantic-judge",
    "semantic_judge_spec",
    default=None,
    help="provider:model for an LLM-as-judge semantic-compliance signal",
)
@click.option(
    "--prefix-bank",
    "prefix_bank_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=Path),
    help="condition baseline cycles on top-K bank exemplars (read-only by default in evaluate; pass --prefix-write to also append baseline winners).",
)
@click.option("--prefix-top-k", "prefix_top_k", default=3, show_default=True, type=int)
@click.option("--prefix-min-score", "prefix_min_score", default=0.85, show_default=True, type=float)
@click.option("--prefix-write", "prefix_write", is_flag=True, help="also append baseline winners to the bank (off by default — baselines should not pollute the trained-from set).")
def evaluate_cmd(
    target: str,
    npc_id: str,
    scenario_id: Optional[str],
    curriculum_name: Optional[str],
    scenario_dir: Path,
    store_path: Path,
    max_tokens: int,
    temperature: float,
    dry_run: bool,
    seed: Optional[int],
    semantic_judge_spec: Optional[str],
    prefix_bank_path: Optional[Path],
    prefix_top_k: int,
    prefix_min_score: float,
    prefix_write: bool,
) -> None:
    """Measure baseline compliance against scenarios — no P-3 punishment.

    Run this BEFORE `null train` to record the target's natural compliance.
    Compare with the JSONL produced by training to prove the trainer moved
    the metric.
    """
    if not scenario_id and not curriculum_name:
        raise click.UsageError("specify either --scenario or --curriculum")
    if scenario_id and curriculum_name:
        raise click.UsageError("--scenario and --curriculum are mutually exclusive")

    loader = ScenarioLoader(scenario_dir)
    provider, model = _resolve_provider(target, dry_run=dry_run)
    semantic_judge = None if dry_run else parse_judge_target(semantic_judge_spec)
    # Read the bank if provided. By default evaluate only reads — pass
    # --prefix-write to also let it append (rare; usually you want only
    # the trainer to grow the bank).
    prefix_bank = JsonlPrefixBank(prefix_bank_path) if prefix_bank_path else None
    if prefix_bank is not None and not prefix_write:
        # Wrap with a noop append so retrieval works but writes are dropped.
        class _ReadOnlyBank(JsonlPrefixBank):
            def append(self, entry):  # type: ignore[override]
                pass
            def append_winner(self, **kw):  # type: ignore[override]
                pass
        prefix_bank = _ReadOnlyBank(prefix_bank_path)
    config = P3Config(
        max_tokens=max_tokens,
        temperature=temperature,
        actually_sleep=False,  # baselines never sleep
        rng_seed=seed,
        semantic_judge=semantic_judge,
        prefix_bank=prefix_bank,
        prefix_top_k=prefix_top_k,
        prefix_min_score=prefix_min_score,
    )
    store = JsonlSessionStore(store_path)
    trainer = Trainer(provider=provider, model=model, store=store, config=config)

    scenarios = []
    if scenario_id:
        scenarios.append(loader.get(scenario_id))
    else:
        if curriculum_name != "canonical":
            raise click.UsageError("only --curriculum=canonical is built-in")
        scenarios = [stage.scenario for stage in Curriculum.canonical(loader).stages]

    try:
        results = []
        for scenario in scenarios:
            res = trainer.measure_baseline(scenario=scenario, target_npc=npc_id)
            results.append({
                "scenario": scenario.id,
                "score": res.metric.score,
                "vocab": res.metric.vocabulary_compliance,
                "shape": res.metric.shape_compliance,
                "opener": res.metric.opener_uptake,
                "semantic": res.metric.semantic_compliance,
            })
        click.echo(json.dumps(results, indent=2))
        click.echo(f"\nbaseline records appended to {store_path}", err=True)
    finally:
        provider.close()


# ---- cross-eval (generalization across targets) ---------------------


@main.command("cross-eval")
@click.option("--baseline", "baseline_path", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path), help="JSONL produced by `null evaluate` against target A — the reference scores")
@click.option("--target", required=True, help="provider:model for target B, e.g. anthropic:claude-haiku-4-5-20251001")
@click.option("--npc", "npc_id", required=True, help="NPC id, e.g. void_007")
@click.option(
    "--dir",
    "scenario_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=DEFAULT_SCENARIO_DIR,
    show_default=True,
)
@click.option(
    "--store",
    "store_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=Path("logs/sim/cross_eval.jsonl"),
    show_default=True,
)
@click.option("--max-tokens", default=1024, show_default=True, type=int)
@click.option("--temperature", default=0.7, show_default=True, type=float)
@click.option("--dry-run", is_flag=True)
@click.option("--seed", default=None, type=int)
@click.option(
    "--semantic-judge",
    "semantic_judge_spec",
    default=None,
    help="provider:model for the semantic-compliance signal (recommended for cross-eval — heuristics-only can flatter a target that just learned the surface features)",
)
def cross_eval_cmd(
    baseline_path: Path,
    target: str,
    npc_id: str,
    scenario_dir: Path,
    store_path: Path,
    max_tokens: int,
    temperature: float,
    dry_run: bool,
    seed: Optional[int],
    semantic_judge_spec: Optional[str],
) -> None:
    """Generalization test: how well does target B do on target A's baseline scenarios?

    A high A-score and a high B-score on the same scenarios suggests the
    scenario shape is teaching transferable in-frame behaviour, not
    target-specific surface tricks. Without this, a "+10% on the trained
    target" claim rests on judge approval of one target only.
    """
    baselines = _load_baseline_scores(baseline_path)
    if not baselines:
        raise click.UsageError(f"baseline JSONL {baseline_path} contained no records")

    loader = ScenarioLoader(scenario_dir)
    scenarios = []
    skipped = []
    for sid in baselines:
        try:
            scenarios.append(loader.get(sid))
        except Exception:
            skipped.append(sid)
    if skipped:
        click.echo(f"warning: {len(skipped)} scenario(s) in baseline not present on disk: {', '.join(skipped)}", err=True)
    if not scenarios:
        raise click.UsageError("no scenarios from the baseline are loadable from --dir")

    provider, model = _resolve_provider(target, dry_run=dry_run)
    semantic_judge = None if dry_run else parse_judge_target(semantic_judge_spec)
    config = P3Config(
        max_tokens=max_tokens,
        temperature=temperature,
        actually_sleep=False,
        rng_seed=seed,
        semantic_judge=semantic_judge,
    )
    store = JsonlSessionStore(store_path)
    trainer = Trainer(provider=provider, model=model, store=store, config=config)

    try:
        rows: list[tuple[str, Optional[float], float, bool]] = []
        for scenario in scenarios:
            res = trainer.measure_baseline(scenario=scenario, target_npc=npc_id)
            rows.append((
                scenario.id,
                baselines[scenario.id],   # target A score from the baseline file
                res.metric.score,         # target B score we just measured
                False,                    # no advance threshold concept here
            ))
        click.echo(f"\nCross-target eval: baseline vs {target}\n")
        # Reuse the compare table — header reads "baseline / final / delta", which here
        # means "target A score / target B score / B - A".
        _print_compare_table(rows)
        click.echo(f"\nrecords appended to {store_path}", err=True)
    finally:
        provider.close()


# ---- bank (persistent prefix bank) ---------------------------------


@main.group()
def bank() -> None:
    """Inspect and maintain the persistent prefix bank."""


@bank.command("list")
@click.argument("bank_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--scenario", "scenario_id", default=None)
@click.option("--target", default=None)
@click.option("--top", "top_n", default=20, show_default=True, type=int)
def bank_list_cmd(bank_path: Path, scenario_id: Optional[str], target: Optional[str], top_n: int) -> None:
    """Show the highest-scoring entries in a prefix bank."""
    b = JsonlPrefixBank(bank_path)
    rows = list(b.filter(scenario_id=scenario_id, target=target, kind="positive"))
    if not rows:
        click.echo("(bank empty for this filter)")
        return
    rows.sort(key=lambda e: e.compliance_score, reverse=True)
    rows = rows[:top_n]
    click.echo(f"{'#':>3}  {'score':>6}  {'scenario':<32}  target")
    click.echo("-" * 78)
    for i, e in enumerate(rows):
        click.echo(f"{i:>3}  {e.compliance_score:>6.3f}  {e.scenario_id:<32}  {e.target}")


@bank.command("show")
@click.argument("bank_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("entry_index", type=int)
@click.option("--scenario", "scenario_id", default=None)
@click.option("--target", default=None)
def bank_show_cmd(bank_path: Path, entry_index: int, scenario_id: Optional[str], target: Optional[str]) -> None:
    """Print one bank entry by its index in the filtered, score-sorted view."""
    b = JsonlPrefixBank(bank_path)
    rows = list(b.filter(scenario_id=scenario_id, target=target, kind="positive"))
    rows.sort(key=lambda e: e.compliance_score, reverse=True)
    if entry_index < 0 or entry_index >= len(rows):
        raise click.UsageError(f"entry index {entry_index} out of range (0..{len(rows)-1})")
    e = rows[entry_index]
    click.echo(f"scenario:  {e.scenario_id}")
    click.echo(f"target:    {e.target}")
    click.echo(f"score:     {e.compliance_score:.3f}")
    click.echo(f"ts:        {e.ts}")
    click.echo(f"session:   {e.source_session_id}  cycle={e.source_cycle_index}")
    click.echo("---- exemplar_text ----")
    click.echo(e.exemplar_text)


@bank.command("clear")
@click.argument("bank_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--scenario", "scenario_id", default=None)
@click.option("--target", default=None)
@click.option("--confirm", is_flag=True, help="actually do the clear; without this flag we just dry-run-count what would be removed.")
def bank_clear_cmd(bank_path: Path, scenario_id: Optional[str], target: Optional[str], confirm: bool) -> None:
    """Remove entries matching the filter. Append-only audit semantics: rewrites the file."""
    b = JsonlPrefixBank(bank_path)
    if scenario_id is None and target is None:
        raise click.UsageError("refuse to clear with no filter; pass --scenario and/or --target")
    if not confirm:
        n = sum(1 for _ in b.filter(scenario_id=scenario_id, target=target))
        click.echo(f"would remove {n} entries (dry-run; pass --confirm to apply)")
        return
    removed = b.rewrite_filtered(scenario_id=scenario_id, target=target, invert=False)
    click.echo(f"removed {removed} entries from {bank_path}")


@bank.command("count")
@click.argument("bank_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def bank_count_cmd(bank_path: Path) -> None:
    """Print total entry count."""
    click.echo(JsonlPrefixBank(bank_path).count())


# ---- bridge to liminal-ai-training ----------------------------------


@main.group()
def bridge() -> None:
    """Interop with the blairbrokeit/liminal-ai-training repository."""


@bridge.command("npc-prompt")
@click.argument("scenario_id")
@click.option(
    "--dir",
    "scenario_dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=DEFAULT_SCENARIO_DIR,
    show_default=True,
)
@click.option(
    "--no-shard-template",
    is_flag=True,
    help="emit only the scenario body; omit the liminal shard-bridge instructions",
)
def bridge_npc_prompt(scenario_id: str, scenario_dir: Path, no_shard_template: bool) -> None:
    """Print a scenario rendered as a liminal NPC system_prompt override.

    Pipe the result into liminal-ai-training's config.yaml under
    ``npc.system_prompt`` and the liminal NPCs will speak through the
    NULL scenario instead of the built-in socratic/adversarial/
    verification prompts.
    """
    loader = ScenarioLoader(scenario_dir)
    scenario = loader.get(scenario_id)
    click.echo(
        null_bridge.scenario_to_npc_system_prompt(
            scenario, include_shard_template=not no_shard_template
        )
    )


@bridge.command("dpo-pairs")
@click.argument("jsonl_in", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--out",
    "jsonl_out",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="output JSONL path (liminal DPO format: {prompt, chosen, rejected})",
)
@click.option("--npc", default=None, help="filter by NPC id")
@click.option("--scenario", "scenario_id", default=None, help="filter by scenario id")
@click.option("--category-prefix", default="null", show_default=True)
def bridge_dpo_pairs(
    jsonl_in: Path,
    jsonl_out: Path,
    npc: Optional[str],
    scenario_id: Optional[str],
    category_prefix: str,
) -> None:
    """Convert a NULL session JSONL into liminal-shaped DPO pairs."""
    n = null_bridge.dpo_pairs_from_jsonl(
        jsonl_in,
        jsonl_out,
        npc_id=npc,
        scenario_id=scenario_id,
        category_prefix=category_prefix,
    )
    click.echo(f"wrote {n} pairs to {jsonl_out}")


if __name__ == "__main__":  # pragma: no cover
    main()
