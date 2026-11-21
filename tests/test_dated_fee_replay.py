"""E5.14b.2 synthetic replay tests for dated US charges (not brokerage)."""
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.primitives import InstrumentId, Market, Money
from invest_engine.trading.dated_fees import (
    EXPANDED_FEE_VERSION, EXPANDED_RATE_IDENTITY, USDatedFeeConfig,
)
from invest_engine.trading.journal import SQLiteTradingJournal
from invest_engine.trading.ledger import TradingStatus
from invest_engine.trading.models import DecisionStatus, OrderIntent, Side, SellSettlementMode
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.policy import RiskLimits
from invest_engine.trading.runtime import TradingRuntime

NOW = datetime(2022, 10, 3, 14, 30, tzinfo=timezone.utc)
INST = InstrumentId(Market.US, "XNAS", "fixture", "FIX", "USD")
LIMITS = RiskLimits(per_trade_planned_loss=D("1"), max_symbol_cost_fraction=D("1"),
                    max_total_cost_fraction=D("1"))


def config(**kwargs):
    return USDatedFeeConfig("sim", (MonetaryRules("USD", D("0.01")),),
                            ((INST.key, InstrumentRules(D("0.01"), D("1"))),), **kwargs)


def engine(cfg=None, cash="1000", journal=None, limits=LIMITS):
    return TradingRuntime(cfg or config(), (Money(D(cash), "USD"),), limits,
                          journal=journal, checkpoint_interval=1)


def order(name="buy", *, side=Side.BUY, qty="10", price="10", at=NOW):
    return OrderIntent(name, "sim", "test", INST, side, D(qty), D(price), at,
                       D("9") if side is Side.BUY else None)


def enter(eng, intent):
    result = eng.submit(intent)
    assert result.decision.decision is DecisionStatus.APPROVED
    eng.accept_simulated(intent.intent_id, intent.submitted_at)
    return result.decision.reservation


def fill(eng, name, execution, qty, price, secs=1):
    eng.fill_simulated(name, price=D(price), quantity=D(qty),
                       execution_id=execution, at=NOW+timedelta(seconds=secs))


def test_minimum_reserved_only_once_and_cancel_releases_only_remainder():
    eng = engine(config(commission_minimum=D("1")))
    assert enter(eng, order()) == D("101")
    fill(eng, "buy", "a", "4", "9.50")
    assert eng.state.account("USD").settled == D("961")
    assert eng.state.account("USD").reserved == D("60")
    assert eng.state.fills[0].fee == D("1")
    fill(eng, "buy", "b", "2", "10", 2)
    assert eng.state.fills[1].fee == 0
    assert eng.state.account("USD").reserved == D("40")
    eng.request_cancel("buy", NOW+timedelta(seconds=3))
    eng.confirm_cancel("buy", NOW+timedelta(seconds=4))
    assert eng.state.account("USD").settled == D("941")
    assert eng.state.account("USD").reserved == 0


def test_cumulative_rounding_and_sale_charge_components():
    eng = engine()
    assert enter(eng, order(qty="4", price="10")) == D("40.04")
    fill(eng, "buy", "b1", "1", "9.01")
    fill(eng, "buy", "b2", "3", "9.01", 2)
    assert [f.fee for f in eng.state.fills] == [D("0.01"), D("0.03")]
    assert eng.state.account("USD").reserved == 0
    sell = order("sell", side=Side.SELL, qty="4", price="10",
                 at=NOW+timedelta(seconds=3))
    enter(eng, sell)
    fill(eng, "sell", "s1", "1", "10", 4)
    fill(eng, "sell", "s2", "3", "10", 5)
    assert [c.tax for c in eng.state.charges] == [D(0), D(0), D("0.02"), D("0.01")]
    assert sum((c.fee for c in eng.state.charges), D(0)) == D("0.08")
    assert eng.state.account("USD").settled == D("1003.85")
    assert eng.state.position(INST).quantity == 0


def test_fee_reserve_blocks_insufficient_cash_and_planned_loss():
    eng = engine(config(commission_minimum=D("1")), cash="100")
    result = eng.submit(order())
    assert result.decision.reason_codes == ("INSUFFICIENT_BUYING_POWER",)
    eng = engine(config(commission_minimum=D("1")), limits=replace(
        LIMITS, per_trade_planned_loss=D("0.01")))
    # Price risk 10; commission + SEC + TAF raise planned loss over 10.
    assert eng.submit(order()).decision.reason_codes == ("PLANNED_LOSS_LIMIT",)


def test_unsupported_dates_and_cross_day_fill_fail_closed():
    eng = engine()
    assert eng.submit(order(at=datetime(2023, 1, 3, 14, 30, tzinfo=timezone.utc))
                      ).decision.reason_codes == ("UNSUPPORTED_COST_POLICY_ORDER",)
    eng = engine()
    enter(eng, order())
    with pytest.raises(InvalidEvent, match="cannot price"):
        eng.fill_simulated("buy", price=D("10"), quantity=D("1"),
                           execution_id="a", at=NOW+timedelta(days=1))
    assert eng.state.status is TradingStatus.HALTED
    assert not eng.state.fills and eng.state.account("USD").settled == D("1000")


def test_journal_replay_binds_cost_policy(tmp_path):
    db = tmp_path / "fee.sqlite"
    cfg = config(commission_minimum=D("1"))
    with SQLiteTradingJournal(db) as journal:
        eng = engine(cfg, journal=journal)
        enter(eng, order())
        fill(eng, "buy", "a", "4", "10")
        original = eng.state
    with SQLiteTradingJournal(db) as journal:
        restored = engine(cfg, journal=journal)
        assert restored.state == original
        fill(restored, "buy", "a", "4", "10")
        assert restored.state == original
        fill(restored, "buy", "b", "6", "10", 2)
        assert restored.state.account("USD").settled == D("899")
    with SQLiteTradingJournal(db) as journal, pytest.raises(InvalidEvent, match="differs"):
        engine(config(commission_minimum=D("2")), journal=journal)


def test_explicit_settlement_carries_net_regulatory_costs():
    eng = engine(config(sell_settlement_mode=SellSettlementMode.EXPLICIT_CONFIRMATION))
    enter(eng, order(qty="1"))
    fill(eng, "buy", "b", "1", "10")
    enter(eng, order("sell", side=Side.SELL, qty="1", at=NOW+timedelta(seconds=2)))
    fill(eng, "sell", "s", "1", "10", 3)
    assert eng.state.account("USD").settled == D("989.99")
    assert eng.state.account("USD").unsettled == D("9.97")
    assert eng.state.pending_settlements[0].amount == D("9.97")


def test_fee_schedule_identity_cannot_be_overridden():
    with pytest.raises(ValueError, match="INVALID_DATED_FEE_CONFIG"):
        config(sell_tax_rate=D("0.01"))
    with pytest.raises(ValueError, match="INVALID_DATED_FEE_CONFIG"):
        config(fee_policy_version="unrecognized")


def test_expanded_policy_selects_exact_effective_dates_and_keeps_legacy_default():
    cfg = config(fee_policy_version=EXPANDED_FEE_VERSION,
                 regulatory_identity=EXPANDED_RATE_IDENTITY)
    for day, sec, taf in (
        (date(2022, 12, 31), "2.29", "6.49"),
        (date(2023, 1, 1), "2.29", "7.27"),
        (date(2023, 2, 26), "2.29", "7.27"),
        (date(2023, 2, 27), "0.80", "7.27"),
        (date(2023, 12, 31), "0.80", "7.27"),
    ):
        assert cfg.charge_components(D(0), D(1), D("100000"), Side.SELL,
                                     charge_day=day)[1:] == (D(sec), D(taf))
    with pytest.raises(ValueError, match="UNCOVERED"):
        cfg.schedule_for_day(date(2024, 1, 1))
    with pytest.raises(ValueError, match="CHARGE_DATE_REQUIRED"):
        cfg.charge_components(D(0), D(1), D(1), Side.SELL)
    with pytest.raises(ValueError, match="INVALID_DATED_FEE_CONFIG"):
        config(fee_policy_version=EXPANDED_FEE_VERSION)
    with pytest.raises(ValueError, match="INVALID_DATED_FEE_CONFIG"):
        config(regulatory_identity=EXPANDED_RATE_IDENTITY)
    assert config().charge_components(D(0), D(1), D("100000"), Side.SELL)[1:] == (
        D("2.29"), D("6.49"))
