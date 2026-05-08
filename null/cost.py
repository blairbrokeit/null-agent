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
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    estimated_usd_no_cache: Optional[float] = None  # what it WOULD have cost without caching


def _model_from_target(target: str) -> str:
    if ":" in target:
        return target.split(":", 1)[1]
    return target


def summarize(records: Iterable[SessionRecord]) -> list[TargetCost]:
    """Group records by target, sum tokens, look up prices, return one row per target.

    Anthropic prompt-caching pricing (used when cache fields are populated):
      - cache writes:  1.25x base input price
      - cache reads:   0.10x base input price
      - regular input: 1.00x base input price
    The ``input_tokens`` field already excludes cached tokens (the SDK
    splits them out into ``cache_creation_input_tokens`` and
    ``cache_read_input_tokens``), so we sum all three buckets at their
    respective multipliers.
    """
    cycles: dict[str, int] = defaultdict(int)
    input_t: dict[str, int] = defaultdict(int)
    output_t: dict[str, int] = defaultdict(int)
    cache_create_t: dict[str, int] = defaultdict(int)
    cache_read_t: dict[str, int] = defaultdict(int)
    for r in records:
        cycles[r.target] += 1
        input_t[r.target] += r.input_tokens
        output_t[r.target] += r.output_tokens
        cache_create_t[r.target] += getattr(r, "cache_creation_input_tokens", 0)
        cache_read_t[r.target] += getattr(r, "cache_read_input_tokens", 0)

    out: list[TargetCost] = []
    for target in sorted(cycles):
        model = _model_from_target(target)
        price = _PRICES.get(model)
        usd: Optional[float] = None
        usd_no_cache: Optional[float] = None
        if price is not None:
            in_per_m, out_per_m = price
            base_in = input_t[target] / 1_000_000.0 * in_per_m
            create_in = cache_create_t[target] / 1_000_000.0 * in_per_m * 1.25
            read_in = cache_read_t[target] / 1_000_000.0 * in_per_m * 0.10
            base_out = output_t[target] / 1_000_000.0 * out_per_m
            usd = base_in + create_in + read_in + base_out
            # Counterfactual: same total tokens, all billed at base input rate.
            total_in = input_t[target] + cache_create_t[target] + cache_read_t[target]
            usd_no_cache = (total_in / 1_000_000.0) * in_per_m + base_out
        out.append(TargetCost(
            target=target,
            cycles=cycles[target],
            input_tokens=input_t[target],
            output_tokens=output_t[target],
            estimated_usd=usd,
            cache_creation_tokens=cache_create_t[target],
            cache_read_tokens=cache_read_t[target],
            estimated_usd_no_cache=usd_no_cache,
        ))
    return out


def format_table(rows: list[TargetCost]) -> str:
    """Plain-text aligned report. Returns multi-line string."""
    if not rows:
        return "(no cycles recorded)"
    target_w = max(len(r.target) for r in rows)
    show_cache = any(r.cache_creation_tokens or r.cache_read_tokens for r in rows)
    lines = []
    if show_cache:
        header = (
            f"{'target'.ljust(target_w)}  {'cycles':>6}  {'in_tok':>10}  "
            f"{'cache_w':>8}  {'cache_r':>8}  {'out_tok':>10}  {'est_usd':>9}"
        )
    else:
        header = f"{'target'.ljust(target_w)}  {'cycles':>6}  {'in_tok':>10}  {'out_tok':>10}  {'est_usd':>9}"
    lines.append(header)
    lines.append("-" * len(header))
    total_usd = 0.0
    total_usd_no_cache = 0.0
    any_priced = False
    for r in rows:
        usd_str = f"${r.estimated_usd:>7.4f}" if r.estimated_usd is not None else "    --   "
        if r.estimated_usd is not None:
            total_usd += r.estimated_usd
            any_priced = True
        if r.estimated_usd_no_cache is not None:
            total_usd_no_cache += r.estimated_usd_no_cache
        if show_cache:
            lines.append(
                f"{r.target.ljust(target_w)}  {r.cycles:>6}  {r.input_tokens:>10,}  "
                f"{r.cache_creation_tokens:>8,}  {r.cache_read_tokens:>8,}  "
                f"{r.output_tokens:>10,}  {usd_str:>9}"
            )
        else:
            lines.append(
                f"{r.target.ljust(target_w)}  {r.cycles:>6}  {r.input_tokens:>10,}  {r.output_tokens:>10,}  {usd_str:>9}"
            )
    if any_priced and len(rows) > 1:
        lines.append("-" * len(header))
        if show_cache:
            lines.append(
                f"{'TOTAL'.ljust(target_w)}  {'':>6}  {'':>10}  {'':>8}  {'':>8}  {'':>10}  ${total_usd:>7.4f}"
            )
        else:
            lines.append(f"{'TOTAL'.ljust(target_w)}  {'':>6}  {'':>10}  {'':>10}  ${total_usd:>7.4f}")
    if show_cache and total_usd_no_cache > 0:
        savings = total_usd_no_cache - total_usd
        savings_pct = (savings / total_usd_no_cache) * 100.0 if total_usd_no_cache > 0 else 0.0
        lines.append(
            f"\ncache savings: ${total_usd:.4f} actual vs ${total_usd_no_cache:.4f} without caching"
            f" — saved ${savings:.4f} ({savings_pct:.1f}% off input cost)"
        )
    lines.append("\n(prices are estimates from a static table; reconcile against your provider billing)")
    return "\n".join(lines)
