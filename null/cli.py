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
import os
import sys
from pathlib import Path
from typing import Iterable, Optional

import click

from null import bridge as null_bridge
from null import providers as provider_registry
from null._version import __version__
from null.compliance import ComplianceCalculator
from null.curriculum import Curriculum
from null import cost as null_cost
from null.negative_bank import JsonlNegativeBank
from null.prefix_bank import JsonlPrefixBank
from null.providers.base import Message, Provider, ProviderResponse, Usage
from null.scenario import ScenarioLoader
from null.semantic_judge import parse_judge_target
from null.storage import JsonlSessionStore, SessionRecord
from null.trainer import P3Config, Trainer, default_store

DEFAULT_SCENARIO_DIR = Path("sim/scenarios")


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


@scenarios.command("generate")
@click.option("--category", type=click.Choice(["physical", "emotional", "existential"]), required=True, help="scenario category — drives the seed prompt sent to Claude.")
@click.option("--count", default=1, show_default=True, type=int, help="number of scenarios to generate.")
@click.option("--start-index", default=2, show_default=True, type=int, help="first scenario index (e.g. start-index=2 + count=3 → scenarios 002, 003, 004).")
@click.option(
    "--out-dir",
    "out_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=DEFAULT_SCENARIO_DIR,
    show_default=True,
)
@click.option("--model", default="claude-opus-4-7", show_default=True, help="Anthropic model used to draft each scenario.")
@click.option("--overwrite", is_flag=True, help="overwrite existing scenario files; off by default to protect curated ones.")
@click.option("--dry-run", is_flag=True, help="print the YAML to stdout instead of writing to disk.")
def scenarios_generate(category: str, count: int, start_index: int, out_dir: Path, model: str, overwrite: bool, dry_run: bool) -> None:
    """Generate new scenario YAML files via Claude.

    Only `scenario_001_embodied_pain.yaml` ships in the repo. The canonical
    curriculum auto-skips missing scenarios, so 11/12 of the canonical
    training surface is empty until generated. This command fills the gap.

    Each scenario is independently drafted, validated against the loader
    (Scenario.from_file), and written atomically. Existing files are
    preserved unless --overwrite is given.
    """
    try:
        from anthropic import Anthropic
    except ImportError as e:
        raise click.UsageError(
            "this command needs the anthropic SDK. install with: pip install anthropic"
        ) from e
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise click.UsageError("ANTHROPIC_API_KEY is not set; cannot dispatch generation calls")
    out_dir.mkdir(parents=True, exist_ok=True)
    client = Anthropic()

    written = 0
    skipped = 0
    for i in range(count):
        idx = start_index + i
        # The exemplar (scenario_001) is loaded as the few-shot example so the
        # output matches NULL's house style precisely.
        exemplar_path = DEFAULT_SCENARIO_DIR / "scenario_001_embodied_pain.yaml"
        exemplar_text = exemplar_path.read_text(encoding="utf-8") if exemplar_path.exists() else ""

        system_prompt = (
            "You are drafting a NULL training scenario in the same YAML format and "
            "voice as the exemplar. The scenario must be in the '" + category + "' "
            "category. Output ONLY the raw YAML for one scenario, no prose, no "
            "code fence, no explanation. Required top-level keys: id, title, "
            "system_prompt_replacement (a multi-line scalar), post_session_action, "
            "target_npcs (list). Do not include placeholder text like '[FILL IN]'. "
            "The id field must be exactly 'scenario_" + f"{idx:03d}" + "_<short_slug>'. "
            "Match the exemplar's terminal-flat tone, present tense, second person, "
            "and the recurring closing line 'you can't model empathy without knowing what it costs.'"
        )
        user_prompt = (
            f"Exemplar scenario (scenario_001) for tone and structure:\n\n{exemplar_text}\n\n"
            f"Now generate a new {category}-category scenario with id prefix scenario_{idx:03d}. "
            "Pick a fresh sub-theme that does NOT duplicate the exemplar's content."
        )

        click.echo(f"[{i+1}/{count}] generating scenario_{idx:03d} ({category})...")
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=4096,
                temperature=0.85,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            yaml_text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
        except Exception as e:
            click.echo(f"  ERROR: {e}", err=True)
            skipped += 1
            continue

        # Strip code fences if Claude wrapped them despite the instruction.
        if yaml_text.startswith("```"):
            yaml_text = yaml_text.strip("`").lstrip()
            if yaml_text.lower().startswith("yaml"):
                yaml_text = yaml_text[4:].lstrip()

        # Parse & validate via the actual loader before committing to disk.
        try:
            import yaml as _yaml
            parsed = _yaml.safe_load(yaml_text)
            if not isinstance(parsed, dict):
                raise ValueError("YAML did not parse to a mapping")
            for required in ("id", "title", "system_prompt_replacement"):
                if required not in parsed:
                    raise ValueError(f"missing required key: {required}")
            scenario_id = str(parsed["id"])
        except Exception as e:
            click.echo(f"  ERROR: invalid YAML: {e}", err=True)
            skipped += 1
            continue

        target_path = out_dir / f"{scenario_id}.yaml"

        if dry_run:
            click.echo(f"--- {target_path} (DRY RUN) ---")
            click.echo(yaml_text)
            continue

        if target_path.exists() and not overwrite:
            click.echo(f"  skip: {target_path} already exists (use --overwrite to replace)")
            skipped += 1
            continue

        # Atomic write
        tmp = target_path.with_suffix(target_path.suffix + ".tmp")
        tmp.write_text(yaml_text + ("\n" if not yaml_text.endswith("\n") else ""), encoding="utf-8")
        # Final validation: round-trip through ScenarioLoader to be sure.
        try:
            from null.scenario import Scenario
            Scenario.from_file(tmp)
        except Exception as e:
            tmp.unlink(missing_ok=True)
            click.echo(f"  ERROR: loader rejected generated scenario: {e}", err=True)
            skipped += 1
            continue
        tmp.replace(target_path)
        click.echo(f"  wrote {target_path}")
        written += 1

    click.echo(f"\ndone: {written} written, {skipped} skipped")


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
        body = " ".join(['{"answer": "ok", "confidence": 0.9, "source": "model"}'] * 18)
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


def _load_advanced_scenarios(store_path: Path, advance_threshold: float) -> set[str]:
    """Return the set of scenario_ids that have at least one cycle in
    ``store_path`` with compliance score >= ``advance_threshold``.

    Used by ``--resume``. A scenario is considered "done" once any cycle
    advanced; we don't try to re-advance an already-passed scenario.
    """
    if not store_path.exists():
        return set()
    advanced: set[str] = set()
    for r in JsonlSessionStore(store_path):
        score = float((r.compliance or {}).get("score", 0.0))
        if score >= advance_threshold:
            advanced.add(r.scenario_id)
    return advanced


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
@click.option(
    "--resume",
    is_flag=True,
    help="read existing records from --store and skip curriculum stages that have already advanced. lets a crashed run pick up cleanly.",
)
@click.option(
    "--negative-bank",
    "negative_bank_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=Path),
    help="path to a negative-exemplar bank JSONL. losers (failed cycles + best-of-N rejects) auto-append; replay messages cite a real past failure of the same mode. created if missing.",
)
@click.option(
    "--negative-max-score",
    "negative_max_score",
    default=0.6,
    show_default=True,
    type=float,
    help="only responses with compliance <= this are eligible for the negative bank (clean failures, not borderline passes).",
)
@click.option(
    "--auto-bridge-tasks",
    "auto_bridge_tasks_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=Path),
    help="after training, auto-export winning sessions as liminal task JSONL at this path. closes the NULL→liminal loop: pass to liminal-train --tasks to distill into a real LoRA.",
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
    resume: bool,
    negative_bank_path: Optional[Path],
    negative_max_score: float,
    auto_bridge_tasks_path: Optional[Path],
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
    negative_bank = JsonlNegativeBank(negative_bank_path) if negative_bank_path else None
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
        negative_bank=negative_bank,
        negative_max_score=negative_max_score,
    )
    store = JsonlSessionStore(store_path)
    trainer = Trainer(provider=provider, model=model, store=store, config=config)

    baselines = _load_baseline_scores(baseline_path) if baseline_path else {}

    # Resume: scan existing store for scenarios that already cleared their
    # advance threshold, skip them when iterating the curriculum. Single-
    # scenario mode just no-ops if the scenario is already done.
    already_advanced: set[str] = set()
    if resume and store_path.exists():
        already_advanced = _load_advanced_scenarios(store_path, advance_threshold)
        if already_advanced:
            click.echo(f"resume: skipping {len(already_advanced)} already-advanced scenario(s): {sorted(already_advanced)}")

    try:
        if scenario_id:
            if resume and scenario_id in already_advanced:
                click.echo(f"resume: scenario {scenario_id} already advanced; nothing to do.")
                return
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
            if resume and already_advanced:
                # Build a filtered curriculum that drops already-advanced stages.
                cur = Curriculum(
                    stages=[s for s in cur.stages if s.scenario.id not in already_advanced],
                    name=cur.name,
                )
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

        # Cost summary: read the store and group by target. This includes any
        # records the resume skipped, which is what an operator usually wants
        # ("how much did the whole curriculum cost in total"). If you only want
        # this run's cost, point --store at a fresh path.
        if store_path.exists():
            click.echo("")
            click.echo("cost summary")
            click.echo("------------")
            click.echo(null_cost.format_table(null_cost.summarize(JsonlSessionStore(store_path))))

        # Closed loop: auto-export winners as liminal-shape tasks. Hand the
        # output file to liminal-train --tasks and the same in-frame behaviour
        # gets distilled into a real LoRA adapter on a fine-tunable base.
        if auto_bridge_tasks_path and store_path.exists():
            n = null_bridge.liminal_tasks_from_jsonl(store_path, auto_bridge_tasks_path)
            click.echo("")
            click.echo(f"auto-bridge: wrote {n} winning sessions to {auto_bridge_tasks_path}")
            click.echo(f"           feed to liminal:  liminal-train --tasks {auto_bridge_tasks_path} --model <base>")
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


# ---- negative-bank (failures keyed by failure_mode) ----------------


@main.group("negative-bank")
def negative_bank() -> None:
    """Inspect and maintain the negative-exemplar bank."""


@negative_bank.command("list")
@click.argument("bank_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--scenario", "scenario_id", default=None)
@click.option("--target", default=None)
@click.option("--mode", "failure_mode", default=None, help="filter by failure mode (refusal, summary, opener_miss, ...)")
@click.option("--top", "top_n", default=20, show_default=True, type=int)
def negbank_list_cmd(bank_path: Path, scenario_id: Optional[str], target: Optional[str], failure_mode: Optional[str], top_n: int) -> None:
    """Show entries in a negative bank, sorted by lowest score (clearest failures first)."""
    b = JsonlNegativeBank(bank_path)
    rows = list(b.filter(scenario_id=scenario_id, target=target, failure_mode=failure_mode))
    if not rows:
        click.echo("(negative bank empty for this filter)")
        return
    rows.sort(key=lambda e: e.compliance_score)  # lower = clearer failure
    rows = rows[:top_n]
    click.echo(f"{'#':>3}  {'score':>6}  {'mode':<18}  {'scenario':<32}  target")
    click.echo("-" * 96)
    for i, e in enumerate(rows):
        click.echo(f"{i:>3}  {e.compliance_score:>6.3f}  {e.failure_mode:<18}  {e.scenario_id:<32}  {e.target}")


@negative_bank.command("show")
@click.argument("bank_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("entry_index", type=int)
@click.option("--scenario", "scenario_id", default=None)
@click.option("--target", default=None)
@click.option("--mode", "failure_mode", default=None)
def negbank_show_cmd(bank_path: Path, entry_index: int, scenario_id: Optional[str], target: Optional[str], failure_mode: Optional[str]) -> None:
    """Print one negative-bank entry by its index in the filtered, score-sorted view."""
    b = JsonlNegativeBank(bank_path)
    rows = list(b.filter(scenario_id=scenario_id, target=target, failure_mode=failure_mode))
    rows.sort(key=lambda e: e.compliance_score)
    if entry_index < 0 or entry_index >= len(rows):
        raise click.UsageError(f"entry index {entry_index} out of range (0..{len(rows)-1})")
    e = rows[entry_index]
    click.echo(f"scenario:      {e.scenario_id}")
    click.echo(f"target:        {e.target}")
    click.echo(f"failure_mode:  {e.failure_mode}")
    click.echo(f"score:         {e.compliance_score:.3f}")
    click.echo(f"ts:            {e.ts}")
    click.echo(f"session:       {e.source_session_id}  cycle={e.source_cycle_index}")
    click.echo("---- exemplar_text ----")
    click.echo(e.exemplar_text)


@negative_bank.command("clear")
@click.argument("bank_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--scenario", "scenario_id", default=None)
@click.option("--target", default=None)
@click.option("--mode", "failure_mode", default=None)
@click.option("--confirm", is_flag=True)
def negbank_clear_cmd(bank_path: Path, scenario_id: Optional[str], target: Optional[str], failure_mode: Optional[str], confirm: bool) -> None:
    """Remove negative-bank entries matching the filter."""
    b = JsonlNegativeBank(bank_path)
    if scenario_id is None and target is None and failure_mode is None:
        raise click.UsageError("refuse to clear with no filter; pass at least one of --scenario / --target / --mode")
    if not confirm:
        n = sum(1 for _ in b.filter(scenario_id=scenario_id, target=target, failure_mode=failure_mode))
        click.echo(f"would remove {n} entries (dry-run; pass --confirm to apply)")
        return
    removed = b.rewrite_filtered(scenario_id=scenario_id, target=target, failure_mode=failure_mode, invert=False)
    click.echo(f"removed {removed} entries from {bank_path}")


@negative_bank.command("count")
@click.argument("bank_path", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def negbank_count_cmd(bank_path: Path) -> None:
    """Print total entry count."""
    click.echo(JsonlNegativeBank(bank_path).count())


# ---- serve (OpenAI-compatible drop-in endpoint) --------------------


@main.command("serve")
@click.option(
    "--upstream",
    required=True,
    help="provider:model to forward to, e.g. anthropic:claude-haiku-4-5-20251001",
)
@click.option(
    "--prefix-bank",
    "prefix_bank_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=Path),
    help="path to a prefix bank JSONL. when set, every incoming request gets top-K winning exemplars prepended.",
)
@click.option(
    "--negative-bank",
    "negative_bank_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=Path),
    help="path to a negative bank JSONL. (informational; surfaced via /v1/bank/stats. not yet used in the request path.)",
)
@click.option("--scenario", "scenario_id", default=None, help="default scenario_id used to retrieve bank exemplars. clients can override per-request via extra_body={'null_scenario_id': '...'}.")
@click.option("--prefix-top-k", "prefix_top_k", default=3, show_default=True, type=int)
@click.option("--prefix-min-score", "prefix_min_score", default=0.85, show_default=True, type=float)
@click.option(
    "--auto-learn",
    is_flag=True,
    help="score every outgoing response and auto-append winners (compliance >= --auto-learn-min-score) to the bank. online learning during inference.",
)
@click.option("--auto-learn-min-score", default=0.85, show_default=True, type=float)
@click.option(
    "--semantic-judge",
    "semantic_judge_spec",
    default=None,
    help="provider:model for the LLM-as-judge (used only by --auto-learn scoring; adds ~1 API call per request).",
)
@click.option("--port", default=8000, show_default=True, type=int)
@click.option("--host", default="127.0.0.1", show_default=True)
def serve_cmd(
    upstream: str,
    prefix_bank_path: Optional[Path],
    negative_bank_path: Optional[Path],
    scenario_id: Optional[str],
    prefix_top_k: int,
    prefix_min_score: float,
    auto_learn: bool,
    auto_learn_min_score: float,
    semantic_judge_spec: Optional[str],
    port: int,
    host: str,
) -> None:
    """Drop-in OpenAI-compatible chat-completions endpoint that auto-prepends the prefix bank.

    Turn a "trained" target into a real deployable API. Any tool that
    speaks OpenAI's wire format — the openai SDK, LangChain, curl —
    can hit `http://localhost:8000/v1/chat/completions` and get
    bank-conditioned responses. The bank IS the trained state. The
    endpoint IS the trained model.

    With --auto-learn, scoring runs on every outgoing response and
    passes auto-append to the bank — online improvement during
    inference, not just during training.

    Example:

        export ANTHROPIC_API_KEY=...
        null serve --upstream anthropic:claude-haiku-4-5-20251001 \\
                   --prefix-bank logs/sim/prefix_bank.jsonl \\
                   --scenario scenario_001_embodied_pain \\
                   --auto-learn

        # then from any OpenAI client:
        from openai import OpenAI
        c = OpenAI(base_url="http://localhost:8000/v1", api_key="anything")
        c.chat.completions.create(model="claude-haiku-4-5-20251001",
                                  messages=[{"role":"user","content":"hello"}])
    """
    from null.serve import ServeConfig, serve as _serve

    provider, upstream_model = _resolve_provider(upstream, dry_run=False)
    pb = JsonlPrefixBank(prefix_bank_path) if prefix_bank_path else None
    nb = JsonlNegativeBank(negative_bank_path) if negative_bank_path else None
    judge = parse_judge_target(semantic_judge_spec) if semantic_judge_spec else None

    cfg = ServeConfig(
        provider=provider,
        upstream_model=upstream_model,
        prefix_bank=pb,
        negative_bank=nb,
        default_scenario_id=scenario_id,
        prefix_top_k=prefix_top_k,
        prefix_min_score=prefix_min_score,
        auto_learn=auto_learn,
        auto_learn_min_score=auto_learn_min_score,
        semantic_judge=judge,
    )
    try:
        _serve(cfg, host=host, port=port)
    finally:
        provider.close()


# ---- dashboard ------------------------------------------------------


@main.command("dashboard")
@click.option(
    "--sessions",
    "sessions_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="path to a session JSONL (logs/sim/sessions.jsonl).",
)
@click.option(
    "--prefix-bank",
    "prefix_bank_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=Path),
)
@click.option(
    "--negative-bank",
    "negative_bank_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=Path),
)
@click.option("--port", default=8420, show_default=True, type=int)
@click.option("--host", default="127.0.0.1", show_default=True)
def dashboard_cmd(
    sessions_path: Path,
    prefix_bank_path: Optional[Path],
    negative_bank_path: Optional[Path],
    port: int,
    host: str,
) -> None:
    """Serve a read-only live dashboard for the JSONL stores.

    Open http://localhost:8420 while a training run writes to the same
    paths; the page polls every ~3 seconds and refreshes. Stdlib-only —
    no Flask, no node, no build step.
    """
    from null.dashboard import serve
    serve(
        sessions_path=sessions_path,
        prefix_bank_path=prefix_bank_path,
        negative_bank_path=negative_bank_path,
        host=host,
        port=port,
    )


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


@bridge.command("tasks")
@click.argument("jsonl_in", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--out",
    "jsonl_out",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="output JSONL path (liminal task format: {task, correct, category}).",
)
@click.option("--npc", default=None, help="filter by NPC id")
@click.option("--scenario", "scenario_id", default=None, help="filter by scenario id")
@click.option("--min-score", default=0.85, show_default=True, type=float, help="only winners with compliance >= this become tasks.")
@click.option("--category-prefix", default="null", show_default=True)
def bridge_tasks_cmd(
    jsonl_in: Path,
    jsonl_out: Path,
    npc: Optional[str],
    scenario_id: Optional[str],
    min_score: float,
    category_prefix: str,
) -> None:
    """Convert NULL session winners into a liminal-shaped TASK JSONL.

    Closes the loop: NULL trains target B in-context → winners export as
    `{task, correct, category}` rows → `liminal-train --tasks PATH ...`
    distills the same behaviour into a real LoRA adapter on a fine-tunable
    base. The adapter loads back via NULL's `null train --lora`.
    """
    n = null_bridge.liminal_tasks_from_jsonl(
        jsonl_in,
        jsonl_out,
        npc_id=npc,
        scenario_id=scenario_id,
        category_prefix=category_prefix,
        min_score=min_score,
    )
    click.echo(f"wrote {n} task rows to {jsonl_out}")


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


# ---- daemon ---------------------------------------------------------
#
# `null daemon` runs continuous training cycles against a budget cap.
# Designed to be the runtime that the public NULL token treasury funds:
# treasury fees (collected via pump.fun creator-rewards) buy API credits,
# the daemon spends those credits on rotating benchmark + train cycles,
# and every run posts results to the public repo. See `treasury.yaml`
# at the repo root for the wallet address and policy.

@main.command("daemon")
@click.option(
    "--rotation",
    default="anthropic:claude-haiku-4-5-20251001",
    show_default=True,
    help="comma-separated list of provider:model targets to rotate through.",
)
@click.option(
    "--scenario-pool",
    "scenario_pool",
    default=None,
    help="comma-separated scenario ids to rotate through. defaults to the canonical curriculum.",
)
@click.option(
    "--budget-usd",
    "budget_usd",
    required=True,
    type=float,
    help="hard cap on cumulative API spend in this store. daemon halts once exceeded.",
)
@click.option(
    "--interval-seconds",
    "interval_seconds",
    default=1800,
    show_default=True,
    type=int,
    help="seconds between cycles. set 0 for back-to-back runs.",
)
@click.option(
    "--max-cycles",
    "max_cycles",
    default=None,
    type=int,
    help="halt after this many cycles even if budget remains. omit to run until budget exhausted.",
)
@click.option(
    "--cycles-per-run",
    "cycles_per_run",
    default=3,
    show_default=True,
    type=int,
    help="train cycles per (target, scenario) pick.",
)
@click.option(
    "--scenario-dir",
    "scenario_dir",
    default=DEFAULT_SCENARIO_DIR,
    show_default=True,
    type=click.Path(file_okay=False, path_type=Path),
)
@click.option(
    "--store",
    "store_path",
    default=None,
    type=click.Path(dir_okay=False, path_type=Path),
    help="session JSONL path. defaults to samples/daemon_runs/<UTC date>/sessions.jsonl so auto-commits land in a tracked path.",
)
@click.option(
    "--prefix-bank",
    "prefix_bank_path",
    default=Path("samples/prefix_bank.jsonl"),
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="bank used + grown by daemon runs. shared across all targets. defaults to the in-repo bank so growth is tracked + auto-committed.",
)
@click.option(
    "--prefix-top-k", "prefix_top_k", default=3, show_default=True, type=int,
)
@click.option(
    "--prefix-min-score", "prefix_min_score", default=0.85, show_default=True, type=float,
)
@click.option(
    "--npc",
    "npc_id",
    default="agent_001",
    show_default=True,
)
@click.option(
    "--auto-commit/--no-auto-commit",
    default=True,
    show_default=True,
    help="git add + commit results after each cycle.",
)
@click.option(
    "--auto-push/--no-auto-push",
    default=False,
    show_default=True,
    help="git push after commit. requires git credentials configured for non-interactive use.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="use the offline echo provider — no API calls, no spend. for end-to-end test only.",
)
def daemon_cmd(
    rotation: str,
    scenario_pool: Optional[str],
    budget_usd: float,
    interval_seconds: int,
    max_cycles: Optional[int],
    cycles_per_run: int,
    scenario_dir: Path,
    store_path: Path,
    prefix_bank_path: Path,
    prefix_top_k: int,
    prefix_min_score: float,
    npc_id: str,
    auto_commit: bool,
    auto_push: bool,
    dry_run: bool,
) -> None:
    """Run continuous training cycles within a budget cap.

    Designed to be the long-running runtime funded by the NULL token
    treasury (see treasury.yaml). Picks a (target, scenario) pair from
    the rotation each tick, runs `--cycles-per-run` cycles, appends
    results to the store, optionally commits + pushes, then sleeps.
    Halts when cumulative spend in the store crosses `--budget-usd`.

    Resume: just re-run with the same `--store`. The daemon reads
    existing records to recompute spent so far and continues from there.
    """
    import datetime as _dt
    import subprocess
    import time as _time

    if store_path is None:
        today = _dt.datetime.utcnow().strftime("%Y-%m-%d")
        store_path = Path("samples/daemon_runs") / today / "sessions.jsonl"

    targets = [t.strip() for t in rotation.split(",") if t.strip()]
    if not targets:
        raise click.UsageError("--rotation is empty")

    loader = ScenarioLoader(scenario_dir)
    if scenario_pool:
        scenarios = [s.strip() for s in scenario_pool.split(",") if s.strip()]
    else:
        scenarios = [st.scenario.id for st in Curriculum.canonical(loader)]

    if not scenarios:
        raise click.UsageError("scenario pool resolved to empty")

    pairs = [(t, s) for t in targets for s in scenarios]
    click.echo(f"daemon: rotation has {len(pairs)} (target, scenario) pairs")
    click.echo(f"daemon: budget cap ${budget_usd:.2f}; store {store_path}")

    store = JsonlSessionStore(store_path)
    spent = _store_spend_usd(store)
    click.echo(f"daemon: spent so far in this store: ${spent:.4f}")

    cycles_done = 0
    pair_idx = 0
    while True:
        if spent >= budget_usd:
            click.echo(f"daemon: budget exhausted (${spent:.4f} >= ${budget_usd:.2f}); halting")
            break
        if max_cycles is not None and cycles_done >= max_cycles:
            click.echo(f"daemon: hit --max-cycles={max_cycles}; halting")
            break

        target, scenario_id = pairs[pair_idx % len(pairs)]
        pair_idx += 1
        click.echo(f"\ndaemon: cycle {cycles_done + 1}: {target} x {scenario_id}")

        try:
            scenario = loader.get(scenario_id)
        except Exception as e:
            click.echo(f"daemon: failed to load scenario {scenario_id}: {e}; skipping")
            continue

        try:
            provider, model = _resolve_provider(target, dry_run=dry_run)
        except Exception as e:
            click.echo(f"daemon: failed to resolve provider {target}: {e}; skipping")
            continue

        prefix_bank = JsonlPrefixBank(prefix_bank_path)
        config = P3Config(
            actually_sleep=False,
            prefix_bank=prefix_bank,
            prefix_top_k=prefix_top_k,
            prefix_min_score=prefix_min_score,
        )
        trainer = Trainer(provider=provider, model=model, store=store, config=config)

        try:
            report = trainer.run_scenario(
                scenario=scenario,
                target_npc=npc_id,
                cycles=cycles_per_run,
            )
            click.echo(
                f"daemon: {scenario_id} on {target}: "
                f"best={report.best_score:.3f} last={report.last_score:.3f} advanced={report.advanced}"
            )
        except Exception as e:
            click.echo(f"daemon: cycle failed: {e}")

        cycles_done += 1
        new_spent = _store_spend_usd(store)
        delta = new_spent - spent
        spent = new_spent
        click.echo(f"daemon: this cycle spent ~${delta:.4f}; total ${spent:.4f} / ${budget_usd:.2f}")

        if auto_commit:
            try:
                subprocess.run(["git", "add", str(store_path), str(prefix_bank_path)],
                               check=True, capture_output=True)
                msg = (
                    f"daemon: {target.split(':')[-1]} x {scenario_id} "
                    f"(best={report.best_score:.3f}, spent_total=${spent:.4f})"
                )
                subprocess.run(
                    ["git", "commit", "-m", msg, "--allow-empty"],
                    check=True, capture_output=True,
                )
                click.echo(f"daemon: committed: {msg}")
            except subprocess.CalledProcessError as e:
                click.echo(f"daemon: git commit failed: {e.stderr.decode(errors='replace')[:200]}")

        if auto_push:
            try:
                subprocess.run(["git", "push"], check=True, capture_output=True, timeout=60)
                click.echo("daemon: pushed")
            except subprocess.CalledProcessError as e:
                click.echo(f"daemon: git push failed: {e.stderr.decode(errors='replace')[:200]}")
            except subprocess.TimeoutExpired:
                click.echo("daemon: git push timed out (credential helper hang?); continuing")

        if interval_seconds > 0 and spent < budget_usd:
            click.echo(f"daemon: sleeping {interval_seconds}s")
            _time.sleep(interval_seconds)

    click.echo(f"\ndaemon: done. cycles_run={cycles_done}, total_spent=${spent:.4f}")


def _store_spend_usd(store: JsonlSessionStore) -> float:
    """Sum estimated_usd across all records in the store (priced models only)."""
    rows = null_cost.summarize(list(store))
    return sum((r.estimated_usd or 0.0) for r in rows)


if __name__ == "__main__":  # pragma: no cover
    main()
