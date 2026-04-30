"""Aggregate statistics over a rule store."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable

from .store import Rule


@dataclass(slots=True)
class RuleStats:
    total_rules: int = 0
    total_uses: int = 0
    total_successes: int = 0
    total_failures: int = 0
    by_provider: dict[str, int] = field(default_factory=dict)
    by_model: dict[str, int] = field(default_factory=dict)
    top_by_usage: list[tuple[str, int]] = field(default_factory=list)
    oldest_created: datetime | None = None
    newest_created: datetime | None = None
    last_used: datetime | None = None

    @property
    def success_rate(self) -> float | None:
        decided = self.total_successes + self.total_failures
        if decided == 0:
            return None
        return self.total_successes / decided


def compute_stats(rules: Iterable[Rule], *, top: int = 5) -> RuleStats:
    """Aggregate stats over an iterable of :class:`Rule`."""
    stats = RuleStats()
    by_provider: Counter[str] = Counter()
    by_model: Counter[str] = Counter()
    usage: list[tuple[str, int]] = []

    for r in rules:
        stats.total_rules += 1
        stats.total_uses += r.use_count
        stats.total_successes += r.success_count
        stats.total_failures += r.failure_count
        by_provider[r.provider] += 1
        by_model[r.model] += 1
        usage.append((r.key, r.use_count))

        if stats.oldest_created is None or r.created_at < stats.oldest_created:
            stats.oldest_created = r.created_at
        if stats.newest_created is None or r.created_at > stats.newest_created:
            stats.newest_created = r.created_at
        if stats.last_used is None or r.last_used_at > stats.last_used:
            stats.last_used = r.last_used_at

    stats.by_provider = dict(by_provider.most_common())
    stats.by_model = dict(by_model.most_common())
    usage.sort(key=lambda t: t[1], reverse=True)
    stats.top_by_usage = usage[:top]
    return stats


def format_stats(stats: RuleStats, *, key_width: int = 60) -> str:
    """Render :class:`RuleStats` as a multi-line text block."""
    lines: list[str] = []
    lines.append(f"Rules:            {stats.total_rules}")
    lines.append(f"Uses:             {stats.total_uses}")
    lines.append(f"  successes:      {stats.total_successes}")
    lines.append(f"  failures:       {stats.total_failures}")
    rate = stats.success_rate
    lines.append(f"  success rate:   {rate:.1%}" if rate is not None else "  success rate:   n/a")
    lines.append(f"Created (oldest): {_fmt_dt(stats.oldest_created)}")
    lines.append(f"Created (newest): {_fmt_dt(stats.newest_created)}")
    lines.append(f"Last used:        {_fmt_dt(stats.last_used)}")

    if stats.by_provider:
        lines.append("By provider:")
        for name, count in stats.by_provider.items():
            lines.append(f"  {name:<20} {count}")
    if stats.by_model:
        lines.append("By model:")
        for name, count in stats.by_model.items():
            lines.append(f"  {name:<40} {count}")
    if stats.top_by_usage:
        lines.append(f"Top {len(stats.top_by_usage)} by usage:")
        for key, count in stats.top_by_usage:
            shown = key if len(key) <= key_width else key[: key_width - 1] + "…"
            lines.append(f"  {shown:<{key_width}} {count}")
    return "\n".join(lines)


def _fmt_dt(dt: datetime | None) -> str:
    if dt is None:
        return "n/a"
    return dt.isoformat(timespec="seconds")
