"""Descriptive, paired temporal-block stability, not a significance test.

Correlated instruments sharing UTC calendar days are grouped in one block.
Use the worse cost-adjusted baseline excess in each matched window. No claim
of independence, confidence intervals, or correction for multiple searches.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, localcontext

from invest_engine.research.candidates import BASELINES, ResearchRegistry, ResearchWindow, StabilityPolicy

D = Decimal


@dataclass(frozen=True, slots=True)
class TemporalBlock:
    start_day: str
    end_day: str
    window_ids: tuple[str, ...]
    mean_worst_cost_excess: Decimal | None


@dataclass(frozen=True, slots=True)
class StabilityAssessment:
    candidate_id: str
    status: str
    reasons: tuple[str, ...]
    blocks: tuple[TemporalBlock, ...]
    positive_block_fraction: Decimal | None
    worst_block_excess: Decimal | None
    worst_leave_one_out_mean: Decimal | None
    matched_windows: int
    planned_windows: int


def _calendar_blocks(windows: tuple[ResearchWindow, ...]) -> tuple[tuple[ResearchWindow, ...], ...]:
    groups: list[list[ResearchWindow]] = []
    end_day: date | None = None
    for w in sorted(windows, key=lambda w: (w.start, w.end, w.window_id)):
        last = (w.end-timedelta(microseconds=1)).date()
        if end_day is None or w.start.date() > end_day:
            groups.append([w])
            end_day = last
        else:
            groups[-1].append(w)
            end_day = max(end_day, last)
    return tuple(tuple(g) for g in groups)


def assess_stability(registry: ResearchRegistry, candidate_id: str,
                     policy: StabilityPolicy) -> StabilityAssessment:
    """Only validation evidence; never read train or final holdout results."""
    base = registry.assess(candidate_id)
    windows = tuple(w for w in registry.plan.windows if w.split == "validation")
    evidence = {(a.window_id, a.candidate_id, a.cost): a for a in registry.evidence
                if a.window_id in {w.window_id for w in windows}}
    by_window: dict[str, Decimal] = {}
    reasons: set[str] = set()
    with localcontext() as ctx:
        ctx.prec = 64
        for w in windows:
            costs = []
            for cost in registry.plan.costs:
                keys = [(w.window_id, c, cost) for c in (candidate_id, *BASELINES)]
                if any(key not in evidence for key in keys):
                    break
                candidate, cash, hold = (evidence[key] for key in keys)
                if not all(a.complete for a in (candidate, cash, hold)) or hold.entry_fills == 0:
                    break
                costs.append(candidate.net_return-max(cash.net_return, hold.net_return))
            if len(costs) == len(registry.plan.costs):
                by_window[w.window_id] = min(costs)
        blocks = []
        for group in _calendar_blocks(windows):
            values = [by_window[w.window_id] for w in group if w.window_id in by_window]
            score = sum(values, D(0))/len(group) if len(values) == len(group) else None
            blocks.append(TemporalBlock(min(w.start.date() for w in group).isoformat(),
                          max((w.end-timedelta(microseconds=1)).date() for w in group).isoformat(),
                          tuple(sorted(w.window_id for w in group)), score))
        complete = all(b.mean_worst_cost_excess is not None for b in blocks)
        positive = worst = loo = None
        if complete and blocks:
            scores = [b.mean_worst_cost_excess for b in blocks
                      if b.mean_worst_cost_excess is not None]
            positive = D(sum(x > 0 for x in scores))/len(scores)
            worst = min(scores)
            if len(scores) > 1:
                loo = (sum(scores, D(0))-max(scores))/(len(scores)-1)
            if positive < policy.min_positive_block_fraction:
                reasons.add("TOO_FEW_POSITIVE_BLOCKS")
            if worst < policy.min_worst_block_excess:
                reasons.add("WORST_BLOCK_EXCESS_TOO_LOW")
            if loo is not None and loo < policy.min_leave_one_out_excess:
                reasons.add("LEAVE_ONE_OUT_EXCESS_TOO_LOW")
        else:
            reasons.add("INCOMPLETE_PAIRED_BLOCKS")
    if len(blocks) < policy.min_time_blocks:
        reasons.add("INSUFFICIENT_TIME_BLOCKS")
    if base.status != "RESEARCH_PASS":
        reasons.add("BASE_ASSESSMENT_"+base.status)
    inconclusive = {"INCOMPLETE_PAIRED_BLOCKS", "INSUFFICIENT_TIME_BLOCKS",
                    "BASE_ASSESSMENT_INCONCLUSIVE"}
    status = ("INCONCLUSIVE" if reasons & inconclusive else
              "UNSTABLE" if reasons else "STABLE")
    return StabilityAssessment(candidate_id, status, tuple(sorted(reasons)), tuple(blocks),
                               positive, worst, loo, len(by_window), len(windows))
