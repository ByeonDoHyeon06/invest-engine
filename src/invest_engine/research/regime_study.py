"""Retrospective regime attribution of E5 fills, not strategy selection.

Classify against information received by the start of each execution bar,
not its close or the exit outcome. An exit is attributed to the exit-bar
open regime, not the entry regime. No attribution of mark-to-market PnL.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext

from invest_engine.core.replay import canonical_bytes
from invest_engine.data.calendar import StaticSessionCalendar
from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.research.evaluation import EvaluationWindow, validate_window
from invest_engine.research.regime import RegimeObservation, RegimePolicy, Trend, Volatility, classify_regime
from invest_engine.research.report import BacktestReport, sha256

D = Decimal


@dataclass(frozen=True, slots=True)
class RegimeFillGroup:
    trend: Trend
    volatility: Volatility
    entry_fills: int
    exit_fills: int
    gross_turnover: Decimal
    fees: Decimal
    taxes: Decimal
    realized_exit_pnl: Decimal
    no_trade_hypothesis_fills: int


@dataclass(frozen=True, slots=True)
class RegimeStudy:
    run_sha256: str
    dataset_sha256: str
    report_sha256: str
    policy_sha256: str
    currency: str
    groups: tuple[RegimeFillGroup, ...]
    classifications: tuple[tuple[str, RegimeObservation], ...]

    @property
    def digest(self) -> str:
        return sha256(self)


def attribute_regimes(
    report: BacktestReport, events: tuple[EventEnvelope[MarketPayload], ...],
    calendar: StaticSessionCalendar, window: EvaluationWindow, policy: RegimePolicy,
) -> RegimeStudy:
    coverage = validate_window(events, calendar, window)
    data_sha = sha256(tuple(canonical_bytes(e).hex() for e in events))
    if report.dataset_sha256 != data_sha or report.event_count != len(events):
        raise ValueError("REGIME_REPORT_DATA_MISMATCH")
    inst = events[0].instrument_id
    assert inst is not None
    if (tuple(c for c, _ in report.by_currency_start) != (inst.currency,)
            or report.fx_base_currency is not None or report.terminal_settlements):
        raise ValueError("REGIME_UNSUPPORTED_REPORT")
    evaluated = {e.event_id: e for e in events[coverage.warmup_bars:]}
    if (len(evaluated) != coverage.evaluation_bars
            or len({e.event_id for e in events}) != len(events)
            or len({f.execution_id for f in report.fills}) != len(report.fills)):
        raise ValueError("REGIME_REPORT_DUPLICATE_ID")
    classifications: dict[str, RegimeObservation] = {}
    groups: dict[tuple[Trend, Volatility], RegimeFillGroup] = {}
    with localcontext() as ctx:
        ctx.prec = 64
        for fill in report.fills:
            e = evaluated.get(fill.market_event_id)
            if e is None or not isinstance(e.payload, Bar) or fill.side not in ("BUY", "SELL"):
                raise ValueError("REGIME_FILL_NOT_EVALUATED_BAR")
            if (not fill.price.is_finite() or fill.price <= 0
                    or not fill.quantity.is_finite() or fill.quantity <= 0
                    or not fill.fee.is_finite() or fill.fee < 0
                    or not fill.tax.is_finite() or fill.tax < 0
                    or not fill.realized_pnl.is_finite()
                    or (fill.side == "BUY" and fill.realized_pnl)):
                raise ValueError("REGIME_INVALID_FILL")
            if e.event_id not in classifications:
                classifications[e.event_id] = classify_regime(events, inst, calendar, e.payload.start, policy)
            obs = classifications[e.event_id]
            key = (obs.trend, obs.volatility)
            previous = groups.get(key, RegimeFillGroup(*key, 0, 0, D(0), D(0), D(0), D(0), 0))
            groups[key] = RegimeFillGroup(
                *key, previous.entry_fills + int(fill.side == "BUY"),
                previous.exit_fills + int(fill.side == "SELL"),
                previous.gross_turnover + fill.price*fill.quantity,
                previous.fees + fill.fee, previous.taxes + fill.tax,
                previous.realized_exit_pnl + fill.realized_pnl,
                previous.no_trade_hypothesis_fills + int(obs.no_trade_hypothesis),
            )
        rows = tuple(groups[k] for k in sorted(groups, key=lambda k: (k[0].value, k[1].value)))
        if (sum(g.entry_fills for g in rows) != report.entry_fill_count
                or sum(g.exit_fills for g in rows) != report.exit_fill_count
                or any(sum((getattr(g, attr) for g in rows), D(0)) !=
                       dict(values).get(inst.currency, D(0)) for attr, values in (
                           ("gross_turnover", report.turnover), ("fees", report.total_fees),
                           ("taxes", report.total_taxes), ("realized_exit_pnl", report.realized_exit_pnl)))):
            raise ValueError("REGIME_GROUP_RECONCILIATION_FAILED")
    return RegimeStudy(report.run_sha256, data_sha, sha256(report), policy.digest, inst.currency,
                       rows, tuple(sorted(classifications.items())))
