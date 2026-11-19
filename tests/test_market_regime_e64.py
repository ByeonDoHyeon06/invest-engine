"""E6.4 synthetic causal classification and actual synthetic E5 reconciliation."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.research.evaluation import EvaluationWindow
from invest_engine.research.regime import RegimePolicy, Trend, Volatility, classify_regime
from invest_engine.research.regime_study import attribute_regimes
from test_us_fee_audit_e514b import fixture, INST

NOW = datetime(2022, 9, 1, 14, 30, tzinfo=timezone.utc)
MIN = timedelta(minutes=1)
POL = RegimePolicy(lookback_returns=3)


def sample(prices):
    calendar = StaticSessionCalendar((TradingSession(Market.US, INST.venue,
                                                      NOW, NOW+30*MIN),))
    rows = []
    for i, p in enumerate(prices):
        start, end = NOW+i*MIN, NOW+(i+1)*MIN
        price = D(p)
        bar = Bar(start, end, price, price, price, price, D("100"), interval=MIN)
        rows.append(EventEnvelope(f"b{i}", "market.bar", "fixture", INST,
                                  end, end, end, i, bar))
    return tuple(rows), calendar


@pytest.mark.parametrize("prices,trend,vol,gate", [
    (("100", "100.12", "100.24", "100.36"), Trend.UP, Volatility.NORMAL, False),
    (("100", "99.88", "99.76", "99.64"), Trend.DOWN, Volatility.NORMAL, True),
    (("100", "100.01", "100.02", "100.01"), Trend.RANGE, Volatility.LOW, False),
    (("100", "101", "99", "101"), Trend.UNCERTAIN, Volatility.HIGH, True),
    (("100", "101", "102", "103"), Trend.UP, Volatility.HIGH, True),
])
def test_separate_trend_and_volatility(prices, trend, vol, gate):
    events, calendar = sample(prices)
    result = classify_regime(events, INST, calendar, NOW+4*MIN, POL)
    assert (result.trend, result.volatility, result.no_trade_hypothesis) == (trend, vol, gate)
    assert result.source_event_ids == tuple(e.event_id for e in events)
    assert result.policy_sha256 == POL.digest


def test_future_suffix_does_not_change_past_and_late_receipt_is_missing():
    events, calendar = sample(("100", "100.12", "100.24", "100.36", "900"))
    prior = classify_regime(events[:4], INST, calendar, NOW+4*MIN, POL)
    assert classify_regime(events, INST, calendar, NOW+4*MIN, POL) == prior
    late = replace(events[3], received_at=NOW+4*MIN+timedelta(seconds=1))
    assert classify_regime((*events[:3], late), INST, calendar, NOW+4*MIN, POL).reasons == (
        "MISSING_OR_LATE_BAR",)
    assert classify_regime((*events[:3], late), INST, calendar,
                           NOW+4*MIN+timedelta(seconds=1), POL).trend is Trend.UP


def test_gaps_flags_duplicates_and_sources_fail_closed():
    events, calendar = sample(("100", "101", "102", "103"))
    at = NOW+4*MIN
    assert classify_regime(events[1:], INST, calendar, at, POL).reasons == ("MISSING_OR_LATE_BAR",)
    flagged = replace(events[0], quality_flags=("LOW_QUALITY",))
    assert classify_regime((flagged, *events[1:]), INST, calendar, at, POL).reasons == (
        "INVALID_OR_FLAGGED_BAR",)
    assert classify_regime((*events, events[0]), INST, calendar, at, POL).reasons == (
        "DUPLICATE_BAR_OR_EVENT",)
    assert classify_regime((replace(events[0], source="other"), *events[1:]), INST, calendar,
                           at, POL).reasons == ("MIXED_SOURCE_HISTORY",)
    other = InstrumentId(Market.US, INST.venue, "other", "OTHER", "USD")
    assert classify_regime(events, other, calendar, at, POL).reasons == ("MISSING_OR_LATE_BAR",)
    assert classify_regime(events, INST, calendar, NOW+MIN, POL).reasons == (
        "INSUFFICIENT_SESSION_HISTORY",)
    assert classify_regime(events, INST, calendar, NOW+30*MIN, POL).reasons == ("OUTSIDE_SESSION",)


def test_no_overnight_or_zero_volume_and_bad_threshold():
    events, calendar = sample(("100", "101", "102", "103"))
    bar = events[0].payload
    zero = replace(events[0], payload=replace(bar, volume=D(0)))
    assert classify_regime((zero, *events[1:]), INST, calendar, NOW+4*MIN, POL).reasons == (
        "ZERO_VOLUME_OBSERVATION",)
    with pytest.raises(ValueError, match="INVALID_REGIME_POLICY"):
        replace(POL, high_rms_return=POL.low_rms_return)


def test_actual_report_reconciles_and_never_uses_fill_bar():
    report, events = fixture(dated=True)
    sessions = tuple(TradingSession(Market.US, INST.venue, e.payload.start, e.payload.start+4*MIN)
                     for e in events[::4])
    calendar = StaticSessionCalendar(sessions)
    window = EvaluationWindow(sessions[-1].start, sessions[-1].end)
    result = attribute_regimes(report, events, calendar, window, replace(POL, lookback_returns=2))
    assert sum(g.entry_fills for g in result.groups) == report.entry_fill_count
    assert sum(g.exit_fills for g in result.groups) == report.exit_fill_count
    assert sum(g.realized_exit_pnl for g in result.groups) == dict(report.realized_exit_pnl)["USD"]
    assert sum(g.fees for g in result.groups) == dict(report.total_fees)["USD"]
    assert all(eid not in obs.source_event_ids for eid, obs in result.classifications)
    assert any(obs.trend is Trend.UNCERTAIN for _, obs in result.classifications)
    assert attribute_regimes(report, events, calendar, window, replace(POL, lookback_returns=2)) == result
    with pytest.raises(ValueError, match="GROUP_RECONCILIATION"):
        attribute_regimes(replace(report, entry_fill_count=999), events, calendar, window, POL)
    with pytest.raises(ValueError, match="DATA_MISMATCH"):
        attribute_regimes(replace(report, dataset_sha256="f"*64), events, calendar, window, POL)
