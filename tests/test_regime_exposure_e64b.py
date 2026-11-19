"""Regime denominators and cohort diagnostics, using synthetic data only."""
from dataclasses import replace
from decimal import Decimal as D

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.primitives import Market
from invest_engine.research.evaluation import EvaluationWindow
from invest_engine.research.fold_execution import _engine
from invest_engine.research.regime import RegimePolicy, Trend
from invest_engine.research.regime_exposure import study_regime_exposure
from invest_engine.research.report import FillTrace
from test_fold_execution_e63b import study
from test_us_fee_audit_e514b import INST, MINUTE, fixture

POL = RegimePolicy(lookback_returns=2)


def test_actual_synthetic_report_exposure_and_empty_cash_control():
    for no_trade in (False, True):
        report, events = fixture(no_trade=no_trade, dated=True)
        sessions = tuple(TradingSession(Market.US, INST.venue,
                                        e.payload.start, e.payload.start+4*MINUTE)
                         for e in events[::4])
        calendar = StaticSessionCalendar(sessions)
        window = EvaluationWindow(sessions[-1].start, sessions[-1].end)
        result = study_regime_exposure(report, events, calendar, window, POL)
        assert result.evaluation_minutes == 4
        assert sum(r.observed_minutes for r in result.rows) == 4
        assert sum(r.observed_minutes for r in result.rows if r.trend is Trend.UNCERTAIN) == 3
        assert result.ending_quantity == 0
        assert sum((r.allocated_realized_pnl for r in result.rows), D(0)) == dict(
            report.realized_exit_pnl).get("USD", D(0))
        assert sum(r.exposed_open_minutes for r in result.rows) == (0 if no_trade else 2)
        assert all(r.exposure_fraction is not None for r in result.rows)
        assert study_regime_exposure(report, events, calendar, window, POL) == result


def test_quantity_cohorts_partial_sale_pnl_conservation_and_ending_inventory():
    # Deliberately fabricated fill trace for testing attribution math ONLY,
    # not an actual E5 economic replay. Two buys in different regimes then sell
    # across cohorts, with a remainder held through the second session.
    _, _, cases, _, scenario, _ = study()
    case = cases[0]
    cash = _engine(case, scenario, None, "no-trade", "base").run(case.events)
    evaluation = case.events[-8:]
    fills = (
        FillTrace("buy1", "order1", evaluation[0].event_id, "BUY", D("2"),
                  D("100"), D("0"), D("0"), D("0")),
        FillTrace("buy2", "order2", evaluation[3].event_id, "BUY", D("3"),
                  D("102"), D("0"), D("0"), D("0")),
        FillTrace("sell1", "order3", evaluation[5].event_id, "SELL", D("3"),
                  D("103"), D("0"), D("0"), D("0.05")),
    )
    by_event = {f.market_event_id: f.execution_id for f in fills}
    report = replace(cash, fills=fills, entry_fill_count=2, exit_fill_count=1,
                     turnover=(("USD", D("815")),),
                     realized_exit_pnl=(("USD", D("0.05")),),
                     decisions=tuple(replace(d, fills=(by_event[d.event_id],))
                                     if d.event_id in by_event else d for d in cash.decisions))
    result = study_regime_exposure(report, case.events, case.calendar, case.window, POL)
    assert result.ending_quantity == 2
    assert sum(r.observed_minutes for r in result.rows) == 8
    assert sum(r.exposed_open_minutes for r in result.rows) == 7
    assert sum(r.open_share_minutes for r in result.rows) == 20
    entry_unknown = next(r for r in result.rows if r.trend is Trend.UNCERTAIN)
    assert entry_unknown.entry_quantity == 2
    assert entry_unknown.closed_entry_quantity == 2
    assert entry_unknown.allocated_realized_pnl == D("0.03")
    other = next(r for r in result.rows if r.entry_quantity == 3)
    assert other.closed_entry_quantity == 1 and other.remaining_entry_quantity == 2
    assert other.allocated_realized_pnl == D("0.02")
    assert sum(r.allocated_realized_pnl for r in result.rows) == D("0.05")
    with pytest.raises(ValueError, match="FILL_ORDER_MISMATCH"):
        study_regime_exposure(replace(report, fills=tuple(reversed(fills))), case.events,
                              case.calendar, case.window, POL)


def test_reject_different_interval():
    _, _, cases, _, scenario, _ = study()
    case = cases[0]
    report = _engine(case, scenario, None, "no-trade", "base").run(case.events)
    with pytest.raises(ValueError, match="REQUIRES_MINUTE"):
        study_regime_exposure(report, case.events, case.calendar, case.window,
                              replace(POL, interval=2*MINUTE))
