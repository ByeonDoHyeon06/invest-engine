"""Synthetic E3 scenario tests. These never connect to a brokerage."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.primitives import InstrumentId, Market, Money
from invest_engine.trading.codec import decode_trade_event, encode_trade_event
from invest_engine.trading.journal import SQLiteTradingJournal
from invest_engine.trading.ledger import TradingStatus
from invest_engine.trading.models import (
    DecisionStatus, OrderIntent, OrderStatus, Side, TradingConfig,
)
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.policy import RiskLimits
from invest_engine.trading.runtime import TradingRuntime

NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)
KR = InstrumentId(Market.KR, "KRX", "KR7005930003", "005930", "KRW")
US = InstrumentId(Market.US, "NASDAQ", "US0378331005", "AAPL", "USD")


def config() -> TradingConfig:
    return TradingConfig(
        "sim-account",
        (MonetaryRules("KRW", D("1")), MonetaryRules("USD", D("0.01"))),
        ((KR.key, InstrumentRules(D("1"), D("1"))),
         (US.key, InstrumentRules(D("0.01"), D("1")))),
    )


def runtime(journal=None, limits=None) -> TradingRuntime:
    return TradingRuntime(config(), (Money(D("1000000"), "KRW"), Money(D("1000.00"), "USD")), limits or RiskLimits(), journal=journal, checkpoint_interval=2)


def buy(name="int1", at=NOW, qty="10", price="7000", currency="KR") -> OrderIntent:
    inst = KR if currency == "KR" else US
    stop = D("6800") if currency == "KR" else D("99")
    return OrderIntent(name, "sim-account", "synthetic-test", inst, Side.BUY, D(qty), D(price), at, stop)


def test_contract_sample_full_partial_cancel_and_idempotency():
    eng = runtime()
    intent = buy()
    result = eng.submit(intent)
    assert result.decision.decision is DecisionStatus.APPROVED
    assert result.decision.reservation == D("70070")
    assert len(result.commands) == 1
    assert eng.state.account("KRW").available == D("929930")
    assert eng.submit(intent).commands == ()
    eng.accept_simulated(intent.intent_id, NOW + timedelta(seconds=1))
    eng.fill_simulated(intent.intent_id, price=D("7000"), quantity=D("4"), execution_id="execution-1", at=NOW + timedelta(seconds=2))
    assert eng.state.account("KRW").settled == D("971972")
    assert eng.state.account("KRW").reserved == D("42042")
    assert eng.state.order(intent.intent_id).status is OrderStatus.PARTIALLY_FILLED  # type: ignore[union-attr]
    for _ in range(5):
        eng.fill_simulated(intent.intent_id, price=D("7000"), quantity=D("4"), execution_id="execution-1", at=NOW + timedelta(seconds=2))
    assert len(eng.state.fills) == 1
    eng.request_cancel(intent.intent_id, NOW + timedelta(seconds=3))
    assert eng.state.account("KRW").reserved == D("42042")  # not released until confirmed
    eng.confirm_cancel(intent.intent_id, NOW + timedelta(seconds=4))
    assert eng.state.account("KRW").settled == D("971972")
    assert eng.state.account("KRW").available == D("971972")
    assert eng.state.account("KRW").reserved == 0
    assert eng.state.position(KR).quantity == D("4")  # type: ignore[union-attr]


def test_unknown_blocks_new_orders_and_restores_after_reconciliation():
    eng = runtime()
    eng.submit(buy())
    eng.mark_unknown("int1", NOW + timedelta(seconds=1))
    reject = eng.submit(buy("int2", NOW + timedelta(seconds=2)))
    assert reject.decision.decision is DecisionStatus.HALTED
    assert reject.commands == ()
    eng.reconcile("int1", OrderStatus.CANCELED, NOW + timedelta(seconds=3))
    assert eng.state.account("KRW").reserved == 0
    allowed = eng.submit(buy("int3", NOW + timedelta(seconds=4)))
    assert allowed.decision.decision is DecisionStatus.APPROVED


def test_sell_has_its_own_position_reservation_and_realized_pnl():
    eng = runtime()
    eng.submit(buy())
    eng.accept_simulated("int1", NOW + timedelta(seconds=1))
    eng.fill_simulated("int1", price=D("7000"), quantity=D("10"), execution_id="f-buy", at=NOW + timedelta(seconds=2))
    sale = OrderIntent("sell1", "sim-account", "fixture", KR, Side.SELL, D("5"), D("8000"), NOW + timedelta(seconds=3))
    assert eng.submit(sale).decision.decision is DecisionStatus.APPROVED
    second = OrderIntent("sell2", "sim-account", "fixture", KR, Side.SELL, D("6"), D("8000"), NOW + timedelta(seconds=4))
    assert eng.submit(second).decision.reason_codes == ("INSUFFICIENT_POSITION",)
    eng.accept_simulated("sell1", NOW + timedelta(seconds=5))
    eng.fill_simulated("sell1", price=D("8000"), quantity=D("5"), execution_id="f-sell", at=NOW + timedelta(seconds=6))
    pos = eng.state.position(KR)
    assert pos.quantity == D("5")  # type: ignore[union-attr]
    assert pos.reserved_sell == 0  # type: ignore[union-attr]
    assert pos.realized_pnl == D("4925")  # type: ignore[union-attr]  # proceeds 39960 - cost 35035


def test_unsupported_cross_currency_and_broker_identity():
    eng = runtime()
    us = buy("us1", price="100", currency="US")
    assert eng.submit(us).decision.reason_codes == ("INSUFFICIENT_BUYING_POWER",)
    over = buy("kr-big", qty="1000")
    assert eng.submit(over).decision.reason_codes == ("INSUFFICIENT_BUYING_POWER",)
    assert eng.state.account("USD").settled == D("1000")
    assert eng.state.account("KRW").settled == D("1000000")


def test_price_tick_reject_and_missing_stop_policy():
    eng = runtime()
    bad = buy("bad1", price="7000.25")
    assert eng.submit(bad).decision.reason_codes == ("INVALID_INSTRUMENT_RULES",)
    nostop = OrderIntent("bad2", "sim-account", "fixture", KR, Side.BUY, D("10"), D("7000"), NOW + timedelta(seconds=1))
    assert eng.submit(nostop).decision.reason_codes == ("STOP_PLAN_REQUIRED",)


def test_duplicate_order_conflict_and_duplicate_execution_conflict_halt():
    eng = runtime()
    eng.submit(buy())
    with pytest.raises(InvalidEvent, match="conflicting repeated order"):
        eng.submit(buy(qty="7"))
    assert eng.state.status is TradingStatus.HALTED

    other = runtime()
    other.submit(buy())
    other.accept_simulated("int1", NOW+timedelta(seconds=1))
    other.fill_simulated("int1", price=D("7000"), quantity=D("4"), execution_id="fill1", at=NOW+timedelta(seconds=2))
    with pytest.raises(InvalidEvent, match="conflicting repeated fill"):
        other.fill_simulated("int1", price=D("6999"), quantity=D("4"), execution_id="fill1", at=NOW+timedelta(seconds=2))
    assert other.state.status is TradingStatus.HALTED


def test_invalid_fill_over_order_remainder_fails_closed():
    eng = runtime()
    eng.submit(buy())
    eng.accept_simulated("int1", NOW + timedelta(seconds=1))
    with pytest.raises(InvalidEvent):
        eng.fill_simulated("int1", price=D("7000"), quantity=D("11"), execution_id="huge", at=NOW+timedelta(seconds=2))
    assert eng.state.status is TradingStatus.HALTED
    assert eng.state.position(KR) is None


def test_journal_restart_atomic_outbox_checkpoint_and_event_roundtrip(tmp_path):
    db = tmp_path / "ledger.sqlite"
    with SQLiteTradingJournal(db) as journal:
        eng = runtime(journal)
        eng.submit(buy())
        assert journal.outbox() == (("int1", "PENDING"),)
        eng.accept_simulated("int1", NOW + timedelta(seconds=1))
        eng.fill_simulated("int1", price=D("7000"), quantity=D("4"), execution_id="f1", at=NOW + timedelta(seconds=2))
        before_hash = eng.state.digest
        assert journal.outbox() == ()
        events = journal._read()
        assert all(decode_trade_event(encode_trade_event(e)) == e for e in events)
    with SQLiteTradingJournal(db) as journal:
        restored = runtime(journal)
        assert restored.state.digest == before_hash
        assert restored.state.account("KRW").reserved == D("42042")
        assert restored.state.position(KR).quantity == D("4")  # type: ignore[union-attr]
        assert restored.submit(buy()).commands == ()  # retry must not create another command
        restored.request_cancel("int1", NOW + timedelta(seconds=3))
        restored.confirm_cancel("int1", NOW + timedelta(seconds=4))
        assert restored.state.account("KRW").reserved == 0


def test_journal_rejects_changed_risk_config_and_corruption(tmp_path):
    db = tmp_path / "r.sqlite"
    with SQLiteTradingJournal(db) as journal:
        runtime(journal).submit(buy())
    with SQLiteTradingJournal(db) as journal:
        with pytest.raises(InvalidEvent, match="differs"):
            runtime(journal, RiskLimits(max_open_positions=5))
    with SQLiteTradingJournal(db) as journal:
        journal.connection.execute("UPDATE trading_events SET checksum='garbage' WHERE ordinal=0")
        journal.connection.commit()
    with SQLiteTradingJournal(db) as journal:
        with pytest.raises(InvalidEvent, match="checksum"):
            runtime(journal)


def test_restart_recovers_halt_after_invalid_execution(tmp_path):
    db = tmp_path / "h.sqlite"
    with SQLiteTradingJournal(db) as journal:
        eng = runtime(journal)
        eng.submit(buy())
        eng.accept_simulated("int1", NOW + timedelta(seconds=1))
        with pytest.raises(InvalidEvent):
            eng.fill_simulated("int1", price=D("7100"), quantity=D("1"), execution_id="bad", at=NOW + timedelta(seconds=2))
        assert eng.state.status is TradingStatus.HALTED
    with SQLiteTradingJournal(db) as journal:
        eng = runtime(journal)
        assert eng.state.status is TradingStatus.HALTED
        with pytest.raises(PermissionError):
            eng.resume_after_review()
        eng.resume_after_review(reviewed=True)
        assert eng.state.status is TradingStatus.RUNNING
        assert eng.state.account("KRW").reserved == D("70070")


def test_existing_e2_market_journal_and_e3_trade_journal_coexist(tmp_path):
    """E3 adds a versioned namespace instead of rewriting legacy E2 market rows."""
    from invest_engine.core.fixtures import synthetic_ticks
    from invest_engine.core.journal import SQLiteEventJournal
    from invest_engine.core.runtime import EventRuntime, RuntimeConfig

    db = tmp_path / "shared.sqlite"
    with SQLiteEventJournal(db) as market_journal:
        market_runtime = EventRuntime(RuntimeConfig("shared"), journal=market_journal)
        market_runtime.accept(synthetic_ticks(KR, count=1)[0])
        market_hash = market_runtime.state.digest
    with SQLiteTradingJournal(db) as trade_journal:
        trading_runtime = runtime(trade_journal)
        trading_runtime.submit(buy())
        trade_hash = trading_runtime.state.digest
    with SQLiteEventJournal(db) as market_journal:
        market_runtime = EventRuntime(RuntimeConfig("shared"), journal=market_journal)
        assert market_runtime.state.digest == market_hash
    with SQLiteTradingJournal(db) as trade_journal:
        trading_runtime = runtime(trade_journal)
        assert trading_runtime.state.digest == trade_hash


def test_cash_quantization_non_decimal_power_increment():
    # Values like 0.05 must really quantize to multiples of the step.
    rule = MonetaryRules("USD", D("0.05"))
    assert rule.settle(D("0.074")) == D("0.05")
    assert rule.settle(D("0.076")) == D("0.10")


def test_pending_buy_orders_consume_cash_and_allocation_budget():
    # Initial account 1m KRW; each order is 70k notional.
    eng = runtime()
    eng.submit(buy())
    second = eng.submit(buy("second", NOW + timedelta(seconds=1)))
    assert second.decision.reason_codes == ("SYMBOL_COST_LIMIT",)
    assert eng.state.account("KRW").reserved == D("70070")


def test_cancel_pending_partial_fill_preserves_cancel_state():
    eng = runtime()
    eng.submit(buy())
    eng.accept_simulated("int1", NOW + timedelta(seconds=1))
    eng.request_cancel("int1", NOW + timedelta(seconds=2))
    eng.fill_simulated("int1", price=D("7000"), quantity=D("4"), execution_id="fp", at=NOW + timedelta(seconds=3))
    order = eng.state.order("int1")
    assert order is not None and order.status is OrderStatus.CANCEL_PENDING
    eng.confirm_cancel("int1", NOW + timedelta(seconds=4))
    assert eng.state.account("KRW").reserved == 0
