"""Tests for E5.14b fixed-tape fee repricing; no retail fee certification."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, Market, Money
from invest_engine.research.backtest import HistoricalBacktest
from invest_engine.research.evaluation import EvaluationWindow
from invest_engine.research.protection import ProtectionPolicy
from invest_engine.research.report import FillTrace
from invest_engine.research.us_fee_audit import FeeAssumption, US_2022, audit_us_fixed_fills
from invest_engine.strategies.baselines import BuyHoldBaseline, NoTradeStrategy
from invest_engine.strategies.contracts import DataRequirement
from invest_engine.trading.dated_fees import USDatedFeeConfig
from invest_engine.trading.models import TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.policy import RiskLimits

INST = InstrumentId(Market.US, "XNAS", "fixture", "FIX", "USD")
MINUTE = timedelta(minutes=1)


def fixture(*, start=datetime(2022, 9, 1, 14, 30, tzinfo=timezone.utc), no_trade=False, dated=False):
    sessions = tuple(TradingSession(Market.US, "XNAS", start+timedelta(days=i),
                                    start+timedelta(days=i, minutes=4))
                     for i in range(21))
    events = []
    for session in sessions:
        for j in range(4):
            at = session.start + j*MINUTE
            end = at+MINUTE
            bar = Bar(at, end, D("100"), D("104"), D("96"), D("100"),
                      D("4000"), interval=MINUTE)
            i = len(events)
            events.append(EventEnvelope(f"b{i}", "market.bar", "fixture", INST,
                                        end, end, end, i, bar))
    strategy = (NoTradeStrategy(DataRequirement("market.bar", MINUTE)) if no_trade else
                BuyHoldBaseline(MINUTE, D("0.05"), D("0.1")))
    config_cls = USDatedFeeConfig if dated else TradingConfig
    config = config_cls("sim", (MonetaryRules("USD", D("0.01")),),
                           ((INST.key, InstrumentRules(D("0.01"), D("1"))),))
    report = HistoricalBacktest(
        calendar=StaticSessionCalendar(sessions), strategies=(strategy,), config=config,
        opening_cash=(Money(D("100000"), "USD"),),
        risk=RiskLimits(per_trade_planned_loss=D("0.5")),
        evaluation_window=EvaluationWindow(sessions[-1].start, sessions[-1].end),
        protection_policy=ProtectionPolicy(enabled=True, adverse_bps=D("10")),
        session_flat=True,
    ).run(tuple(events))
    return report, tuple(events)


def test_effective_interval_is_not_extrapolated():
    assert US_2022.covers(date(2022, 5, 14))
    assert US_2022.covers(date(2022, 12, 31))
    assert not US_2022.covers(date(2022, 5, 13))
    assert not US_2022.covers(date(2023, 1, 1))


def test_fee_audit_does_not_change_original_run():
    report, events = fixture()
    assumption = FeeAssumption(D("0.001"))
    result = audit_us_fixed_fills(report, events, assumption)
    buy = next(o for o in result.orders if o.side == "BUY")
    sell = next(o for o in result.orders if o.side == "SELL")
    assert buy.gross == D("5000") and buy.commission == D("5")
    assert buy.sec_fee == buy.taf == 0
    assert sell.gross == D("4995") and sell.commission == D("5")
    assert sell.sec_fee == D("0.12") and sell.taf == D("0.01")
    assert result.original_total == D("10") and result.repriced_total == D("10.13")
    assert result.fixed_fill_net_pnl == result.original_net_pnl - D("0.13")
    assert result.source_run_sha256 == report.run_sha256
    assert not result.broker_verified and not result.charge_date_verified
    assert not result.replayed_with_cost_policy
    assert result == audit_us_fixed_fills(report, events, assumption)
    other = audit_us_fixed_fills(report, events, FeeAssumption(D("0.0025")))
    assert other.policy_sha256 != result.policy_sha256
    assert other.audit_sha256 != result.audit_sha256


def test_no_trade_has_no_fees_even_with_minimum():
    report, events = fixture(no_trade=True)
    result = audit_us_fixed_fills(report, events, FeeAssumption(D("0"), D("1")))
    assert result.orders == () and result.repriced_total == result.fixed_fill_net_pnl == 0


def test_order_minimum_once_and_taf_per_execution_cap():
    report, events = fixture()
    # Explicit fixed-tape fixture for multi-fill orders: no fabricated replay.
    # Preserve aggregate original fees to exercise reconciliation only.
    f1 = FillTrace("x1", "same", events[-3].event_id, "SELL", D("100000"), D("1"),
                   D("5"), D("0"), D(0))
    f2 = replace(f1, execution_id="x2", market_event_id=events[-2].event_id)
    fixture_report = replace(report, fills=(f1, f2), total_fees=(("USD", D("10")),))
    result = audit_us_fixed_fills(fixture_report, events, FeeAssumption(D(0), D("1")))
    order = result.orders[0]
    assert order.executions == 2 and order.commission == D("1")
    assert order.taf == D("12.98") and order.sec_fee == D("4.58")
    assert result.repriced_total == D("18.56")


def test_reject_uncovered_history():
    report, events = fixture(start=datetime(2023, 1, 1, 14, 30, tzinfo=timezone.utc))
    with pytest.raises(ValueError, match="UNCOVERED_CHARGE_DATE"):
        audit_us_fixed_fills(report, events, FeeAssumption(D("0.001")))


def test_reject_mismatched_dataset_and_duplicate_execution():
    report, events = fixture()
    with pytest.raises(ValueError, match="DATASET_MISMATCH"):
        audit_us_fixed_fills(report, (replace(events[0], source="changed"),)+events[1:],
                             FeeAssumption(D("0.001")))
    with pytest.raises(ValueError, match="DUPLICATE_OR_INVALID_FILL"):
        audit_us_fixed_fills(replace(report, fills=report.fills+report.fills[:1]),
                             events, FeeAssumption(D("0.001")))
    with pytest.raises(ValueError, match="LEDGER_TOTAL_MISMATCH"):
        audit_us_fixed_fills(replace(report, total_fees=(("USD", D("0")),)),
                             events, FeeAssumption(D("0.001")))


@pytest.mark.parametrize("rate,minimum", [(D("-1"), D("0")), (D("1"), D("0")),
                                           (D("0"), D("0.001"))])
def test_reject_invalid_fee_assumptions(rate, minimum):
    with pytest.raises(ValueError, match="INVALID_FEE_ASSUMPTION"):
        FeeAssumption(rate, minimum)


def test_dated_policy_replay_costs_flow_into_equity_and_attribution():
    old, _ = fixture()
    report, events = fixture(dated=True)
    assert report.config_sha256 != old.config_sha256
    assert report.run_sha256 != old.run_sha256
    assert report.fills[1].tax == D("0.13")
    assert dict(report.total_taxes)["USD"] == D("0.13")
    assert dict(report.net_pnl)["USD"] == dict(old.net_pnl)["USD"] - D("0.13")
    assert report.run_sha256 == fixture(dated=True)[0].run_sha256
    checked = audit_us_fixed_fills(report, events, FeeAssumption(D("0.001")))
    assert checked.original_total == checked.repriced_total
