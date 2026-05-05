"""Per-provider token-cost estimation.

Public model prices are noisy and change often, so this module is
deliberately conservative and explicit: prices are stored as
$/Mtoken constants in a single dict, and any unknown model returns
``None`` for the dollar estimate (the token count is still reported).

The trainer calls ``summarize`` at end-of-run; the CLI prints it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

from null.storage import SessionRecord


# $/Mtoken (input, output). Conservative round numbers — operators should
# treat these as ESTIMATES and reconcile against their billing dashboard.
# Unlisted models report tokens-only and skip the dollar column.
_PRICES: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o-mini":          (0.15,  0.60),
    "gpt-4o":               (2.50, 10.00),
    "gpt-5.5":              (5.00, 20.00),    # speculative; per public previews
    # Anthropic
    "claude-haiku-4-5":           (0.80,  4.00),
    "claude-haiku-4-5-20251001":  (0.80,  4.00),
    "claude-sonnet-4-6":          (3.00, 15.00),
    "claude-opus-4-7":            (15.00, 75.00),
    # OpenRouter routes through providers — leave unset, operator can
    # override via the env if needed.
}


@dataclass(slots=True)
class TargetCost:
    target: str            # "provider:model"
    cycles: int
    input_tokens: int
    output_tokens: int
    estimated_usd: Optional[float]   # None when model not in price table


def _model_from_target(target: str) -> str:
    if ":" in target:
        return target.split(":", 1)[1]
    return target


def summarize(records: Iterable[SessionRecord]) -> list[TargetCost]:
    """Group records by target, sum tokens, look up prices, return one row per target."""
    cycles: dict[str, int] = defaultdict(int)
    input_t: dict[str, int] = defaultdict(int)
    output_t: dict[str, int] = defaultdict(int)
    for r in records:
        cycles[r.target] += 1
        input_t[r.target] += r.input_tokens
        output_t[r.target] += r.output_tokens

    out: list[TargetCost] = []
    for target in sorted(cycles):
        model = _model_from_target(target)
        price = _PRICES.get(model)
        usd: Optional[float] = None
        if price is not None:
            in_per_m, out_per_m = price
            usd = (input_t[target] / 1_000_000.0) * in_per_m + (output_t[target] / 1_000_000.0) * out_per_m
        out.append(TargetCost(
            target=target,
            cycles=cycles[target],
            input_tokens=input_t[target],
            output_tokens=output_t[target],
            estimated_usd=usd,
        ))
    return out


def format_table(rows: list[TargetCost]) -> str:
    """Plain-text aligned report. Returns multi-line string."""
    if not rows:
        return "(no cycles recorded)"
    target_w = max(len(r.target) for r in rows)
    lines = []
    header = f"{'target'.ljust(target_w)}  {'cycles':>6}  {'in_tok':>10}  {'out_tok':>10}  {'est_usd':>9}"
    lines.append(header)
    lines.append("-" * len(header))
    total_usd = 0.0
    any_priced = False
    for r in rows:
        usd_str = f"${r.estimated_usd:>7.4f}" if r.estimated_usd is not None else "    --   "
        if r.estimated_usd is not None:
            total_usd += r.estimated_usd
            any_priced = True
        lines.append(
            f"{r.target.ljust(target_w)}  {r.cycles:>6}  {r.input_tokens:>10,}  {r.output_tokens:>10,}  {usd_str:>9}"
        )
    if any_priced and len(rows) > 1:
        lines.append("-" * len(header))
        lines.append(f"{'TOTAL'.ljust(target_w)}  {'':>6}  {'':>10}  {'':>10}  ${total_usd:>7.4f}")
    lines.append("\n(prices are estimates from a static table; reconcile against your provider billing)")
    return "\n".join(lines)
