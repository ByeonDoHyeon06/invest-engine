"""Bind strict E5 replay reports to preregistered E6 arms.

This is structural reconciliation, not independent verification of a source,
fee policy, execution model or code provenance. Imported arms remain
provisional, even when their arithmetic and identities match.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from invest_engine.core.replay import canonical_bytes
from invest_engine.data.calendar import StaticSessionCalendar
from invest_engine.domain.events import EventEnvelope, MarketPayload
from invest_engine.research.candidates import ArmEvidence, ResearchPlan, _hash
from invest_engine.research.evaluation import EvaluationWindow, validate_window
from invest_engine.research.report import BacktestReport, drawdown, sha256


@dataclass(frozen=True, slots=True)
class ReportBinding:
    plan_sha256: str
    window_id: str
    candidate_id: str
    cost: str
    expected_report_config_sha256: str

    def __post_init__(self) -> None:
        if (not _hash(self.plan_sha256) or not _hash(self.expected_report_config_sha256)
                or not self.window_id or not self.candidate_id
                or self.cost not in ("base", "stress")):
            raise ValueError("INVALID_REPORT_BINDING")


def report_context_sha256(calendar: StaticSessionCalendar, window: EvaluationWindow,
                          scenario_identity: str) -> str:
    """The scenario digest is supplied by an independent experiment planner."""
    if not _hash(scenario_identity):
        raise ValueError("INVALID_SCENARIO_IDENTITY")
    return sha256(("strict-e5-context-v1", calendar, window, scenario_identity))


def evidence_from_report(
    plan: ResearchPlan, binding: ReportBinding, report: BacktestReport,
    events: tuple[EventEnvelope[MarketPayload], ...], calendar: StaticSessionCalendar,
    window: EvaluationWindow, *, scenario_identity: str,
) -> ArmEvidence:
    if plan.digest != binding.plan_sha256 or report.config_sha256 != binding.expected_report_config_sha256:
        raise ValueError("REPORT_PLAN_OR_CONFIG_MISMATCH")
    declared = next((w for w in plan.windows if w.window_id == binding.window_id), None)
    if declared is None or (declared.start, declared.end) != (window.start, window.end):
        raise ValueError("REPORT_WINDOW_MISMATCH")
    if binding.cost not in plan.costs:
        raise ValueError("REPORT_COST_NOT_REGISTERED")
    configs = {**dict(plan.baseline_config_sha256),
               **{c.candidate_id: c.config_sha256 for c in plan.candidates}}
    if binding.candidate_id not in configs:
        raise ValueError("REPORT_CANDIDATE_NOT_REGISTERED")
    context_sha = report_context_sha256(calendar, window, scenario_identity)
    if declared.context_sha256 != context_sha:
        raise ValueError("REPORT_CONTEXT_MISMATCH")
    coverage = validate_window(events, calendar, window)
    inst = events[0].instrument_id
    if inst is None or (inst.key, inst.currency) != (declared.instrument_key, declared.currency):
        raise ValueError("REPORT_INSTRUMENT_MISMATCH")
    data_sha = sha256(tuple(canonical_bytes(e).hex() for e in events))
    if (data_sha != declared.data_sha256 or report.dataset_sha256 != data_sha
            or report.event_count != len(events)):
        raise ValueError("REPORT_DATASET_MISMATCH")
    currency = declared.currency
    if (any(tuple(c for c, _ in values) != (currency,)
            for values in (report.by_currency_start, report.by_currency_end,
                           report.net_pnl, report.max_drawdown))
            or report.fx_base_currency is not None or report.terminal_settlements):
        raise ValueError("REPORT_UNSUPPORTED_CURRENCY_OR_TERMINAL_ACTION")
    if (len(report.decisions) != len(events)
            or any(d.event_id != e.event_id for d, e in zip(report.decisions, events, strict=True))
            or len(report.equity) != coverage.evaluation_bars):
        raise ValueError("REPORT_TRACE_COVERAGE_MISMATCH")
    evaluation = events[coverage.warmup_bars:]
    evaluation_ids = {e.event_id for e in evaluation}
    expected_times = tuple(max(e.available_at, e.received_at) for e in evaluation)
    if tuple(p.at for p in report.equity) != expected_times:
        raise ValueError("REPORT_EQUITY_TIME_MISMATCH")
    complete = all(p.complete for p in report.equity)
    if (any(tuple(c for c, _ in p.by_currency) != (currency,)
            for p in report.equity if p.complete)
            or not report.equity[-1].complete
            or report.equity[-1].by_currency != report.by_currency_end):
        raise ValueError("REPORT_EQUITY_CURRENCY_MISMATCH")
    start, end = report.by_currency_start[0][1], report.by_currency_end[0][1]
    if report.net_pnl[0][1] != end-start or report.max_drawdown[0][1] != drawdown(report.equity, currency):
        raise ValueError("REPORT_METRIC_RECONCILIATION")
    if (len({f.execution_id for f in report.fills}) != len(report.fills)
            or any(f.market_event_id not in evaluation_ids or f.side not in ("BUY", "SELL")
                   or not f.quantity.is_finite() or f.quantity <= 0
                   or not f.price.is_finite() or f.price <= 0
                   or not f.fee.is_finite() or f.fee < 0
                   or not f.tax.is_finite() or f.tax < 0 for f in report.fills)):
        raise ValueError("REPORT_INVALID_FILL_TRACE")
    buys = sum(f.side == "BUY" for f in report.fills)
    sells = sum(f.side == "SELL" for f in report.fills)
    if (buys != report.entry_fill_count or sells != report.exit_fill_count
            or sum((f.fee for f in report.fills), Decimal(0))
            != dict(report.total_fees).get(currency, Decimal(0))
            or sum((f.tax for f in report.fills), Decimal(0))
            != dict(report.total_taxes).get(currency, Decimal(0))):
        raise ValueError("REPORT_FILL_COST_RECONCILIATION")
    return ArmEvidence(
        binding.window_id, binding.candidate_id, binding.cost, data_sha, context_sha,
        report.run_sha256, configs[binding.candidate_id], currency, start,
        report.net_pnl[0][1], report.max_drawdown[0][1], sells, buys,
        False, complete, False, False, sha256(report),
    )
