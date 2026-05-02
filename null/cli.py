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

from null import providers as provider_registry
from null._version import __version__
from null.compliance import ComplianceCalculator
from null.curriculum import Curriculum
from null.providers.base import Message, Provider, ProviderResponse, Usage
from null.scenario import ScenarioLoader
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
) -> None:
    """Run the P-3 cycle against a target."""
    if not scenario_id and not curriculum_name:
        raise click.UsageError("specify either --scenario or --curriculum")
    if scenario_id and curriculum_name:
        raise click.UsageError("--scenario and --curriculum are mutually exclusive")

    loader = ScenarioLoader(scenario_dir)
    provider, model = _resolve_provider(target, dry_run=dry_run)
    config = P3Config(
        pass_threshold=pass_threshold,
        max_tokens=max_tokens,
        temperature=temperature,
        actually_sleep=not no_sleep,
        dispatch_lora_updates=lora,
        rng_seed=seed,
    )
    store = JsonlSessionStore(store_path)
    trainer = Trainer(provider=provider, model=model, store=store, config=config)

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
    finally:
        provider.close()


if __name__ == "__main__":  # pragma: no cover
    main()
