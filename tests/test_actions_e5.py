"""E5.7 synthetic corporate-action accounting and immutable replay safety."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.primitives import InstrumentId, Market, Money
from invest_engine.trading.actions import (
    DelistingObserved, DividendEntitled, SplitApplied,
)
from invest_engine.trading.codec import decode_trade_event, encode_trade_event
from invest_engine.trading.journal import SQLiteTradingJournal
from invest_engine.trading.ledger import TradingStatus, audit_trading_state
from invest_engine.trading.models import OrderIntent, Side, TradingConfig, DecisionStatus
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.policy import RiskLimits
from invest_engine.trading.runtime import TradingRuntime

T = datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc)
KR = InstrumentId(Market.KR, "KRX", "KR-SYN-CORP", "SYN", "KRW")


def engine(*, journal: SQLiteTradingJournal | None = None) -> TradingRuntime:
    conf = TradingConfig("research", (MonetaryRules("KRW", D("1")),),
                         ((KR.key, InstrumentRules(D("1"), D("1"))),))
    risk = RiskLimits(per_trade_planned_loss=D("0.5"),
                      max_symbol_cost_fraction=D("0.6"),
                      max_total_cost_fraction=D("0.8"))
    return TradingRuntime(conf, (Money(D("1000000"), "KRW"),), risk,
                          journal=journal, checkpoint_interval=2)


def bought(eng: TradingRuntime, *, shares: str = "10") -> None:
    order = OrderIntent("initial", "research", "fixture", KR, Side.BUY,
                        D(shares), D("7000"), T, D("6800"))
    assert eng.submit(order).decision.decision is DecisionStatus.APPROVED
    eng.accept_simulated("initial", T + timedelta(seconds=1))
    eng.fill_simulated("initial", price=D("7000"), quantity=D(shares),
                       execution_id="initial-fill", at=T + timedelta(seconds=2))


def split(at: datetime) -> SplitApplied:
    return SplitApplied("split-001", KR, 2, 1, at, at, "verified-fixture")


def dividend(at: datetime) -> DividendEntitled:
    return DividendEntitled("div-001", KR, D("12.25"), D("0.20"), at, at,
                            "verified-fixture")


def test_split_preserves_cost_basis_and_audit_then_sell():
    eng = engine()
    bought(eng)
    before = eng.state.position(KR)
    assert before is not None
    cost = before.quantity * before.average_cost
    at = T + timedelta(seconds=3)
    assert eng.apply_split(split(at), at)
    after = eng.state.position(KR)
    assert after is not None
    assert after.quantity == D("20")
    assert after.average_cost == D("3503.5")
    assert after.quantity * after.average_cost == cost
    assert not eng.apply_split(split(at), at)  # identical duplicate is idempotent
    audit_trading_state(eng.state)
    sell = OrderIntent("sale", "research", "fixture", KR, Side.SELL,
                       D("5"), D("4000"), at + timedelta(seconds=1))
    assert eng.submit(sell).decision.decision is DecisionStatus.APPROVED
    eng.accept_simulated("sale", at + timedelta(seconds=2))
    eng.fill_simulated("sale", price=D("4000"), quantity=D("5"),
                       execution_id="sale-fill", at=at + timedelta(seconds=3))
    assert eng.state.position(KR).quantity == D("15")  # type: ignore[union-attr]
    audit_trading_state(eng.state)


def test_dividend_entitlement_not_immediately_cash_payment():
    eng = engine()
    bought(eng)
    at = T + timedelta(seconds=3)
    cash_before = eng.state.account("KRW").settled
    assert eng.record_dividend(dividend(at), at)
    assert eng.state.account("KRW").settled == cash_before
    receivable = eng.state.dividend_receivables[0]
    assert (receivable.gross, receivable.withheld, receivable.net) == (D("123"), D("25"), D("98"))
    paid_at = at + timedelta(days=4)
    assert eng.confirm_dividend_payment("div-001", paid_at)
    assert eng.state.account("KRW").settled == cash_before + D("98")
    assert not eng.confirm_dividend_payment("div-001", paid_at)
    assert eng.state.dividend_receivables == ()
    audit_trading_state(eng.state)


def test_delisting_halts_new_intents_but_does_not_invent_liquidation_value():
    eng = engine()
    bought(eng)
    position = eng.state.position(KR)
    cash = eng.state.account("KRW").settled
    at = T + timedelta(seconds=3)
    assert eng.flag_delisting(DelistingObserved("delist-001", KR, at, at, "fixture"), at)
    assert eng.state.position(KR) == position
    assert eng.state.account("KRW").settled == cash
    intent = OrderIntent("new-buy", "research", "fixture", KR, Side.BUY,
                         D("1"), D("7000"), at + timedelta(seconds=1), D("6800"))
    assert eng.submit(intent).decision.reason_codes == ("INSTRUMENT_DELISTED",)
    sell = OrderIntent("new-sell", "research", "fixture", KR, Side.SELL,
                       D("1"), D("7000"), at + timedelta(seconds=2))
    assert eng.submit(sell).decision.reason_codes == ("INSTRUMENT_DELISTED",)


def test_action_with_open_order_fails_closed_without_repricing():
    eng = engine()
    intent = OrderIntent("waiting", "research", "fixture", KR, Side.BUY,
                         D("10"), D("7000"), T, D("6800"))
    eng.submit(intent)
    original = eng.state.account("KRW").reserved
    at = T + timedelta(seconds=1)
    with pytest.raises(InvalidEvent, match="open orders"):
        eng.apply_split(split(at), at)
    assert eng.state.status is TradingStatus.HALTED
    assert eng.state.account("KRW").reserved == original


def test_fractional_split_rejected_and_future_action_rejected():
    eng = engine()
    bought(eng, shares="1")
    at = T + timedelta(seconds=3)
    with pytest.raises(InvalidEvent, match="fractional split"):
        eng.apply_split(SplitApplied("ratio", KR, 3, 2, at, at, "fixture"), at)
    assert eng.state.status is TradingStatus.HALTED
    eng2 = engine()
    with pytest.raises(InvalidEvent, match="not yet effective"):
        eng2.flag_delisting(DelistingObserved("future", KR, at, at, "fixture"), T)
    assert eng2.state.status is TradingStatus.HALTED


def test_conflicting_duplicate_action_id_halts_and_replay_reconstructs(tmp_path):
    db = tmp_path / "portfolio.sqlite"
    with SQLiteTradingJournal(db) as journal:
        eng = engine(journal=journal)
        bought(eng)
        at = T + timedelta(seconds=3)
        eng.apply_split(split(at), at)
        eng.record_dividend(dividend(at + timedelta(seconds=1)), at + timedelta(seconds=1))
        eng.confirm_dividend_payment("div-001", at + timedelta(days=3))
        events = journal._read()
        assert all(decode_trade_event(encode_trade_event(x)) == x for x in events)
        digest = eng.state.digest
        cash = eng.state.account("KRW").settled
        shares = eng.state.position(KR).quantity  # type: ignore[union-attr]
    with SQLiteTradingJournal(db) as journal:
        eng = engine(journal=journal)
        assert eng.state.digest == digest
        assert eng.state.account("KRW").settled == cash
        assert eng.state.position(KR).quantity == shares  # type: ignore[union-attr]
        with pytest.raises(InvalidEvent, match="conflicting repeated corporate"):
            eng.apply_split(SplitApplied("split-001", KR, 3, 1,
                                         T + timedelta(seconds=3),
                                         T + timedelta(seconds=3), "verified-fixture"),
                            at + timedelta(days=4))
        assert eng.state.status is TradingStatus.HALTED


def test_invalid_action_terms_rejected_at_construction():
    with pytest.raises(ValueError):
        SplitApplied("id", KR, 0, 1, T, T, "src")
    with pytest.raises(ValueError):
        DividendEntitled("id", KR, D("1"), D("1.0"), T, T, "src")
