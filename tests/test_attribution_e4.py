"""Virtual strategy accounting for synthetic shared orders, not broker positions."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.domain.primitives import InstrumentId, Market, Money
from invest_engine.strategies.allocation import allocate_targets, propose_simulated_intents
from invest_engine.strategies.attribution import (
    AttributionTicket, VirtualLedger, audit_virtual_against_account,
    record_simulated_fill, ticket_for_plan,
)
from invest_engine.strategies.contracts import SignalDirection, StrategySignal
from invest_engine.trading.models import OrderIntent, Side, SimulatedFill, TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.monitoring import MarketMark
from invest_engine.trading.runtime import TradingRuntime

NOW = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
INST = InstrumentId(Market.KR, "KRX", "SYN-111", "SYN", "KRW")


def ticket(side=Side.BUY, qty="10"):
    return AttributionTicket(
        "order-buy" if side is Side.BUY else "order-sell", INST, side, D(qty),
        (("orb", D("0.06")), ("ema", D("0.04"))) if side is Side.BUY else (),
    )


def buy_fill(qty="10", fee="10"):
    return SimulatedFill("buy-1", "order-buy", D(qty), D("100"), D(fee), NOW)


def test_buy_allocation_conserves_fees_and_quantities():
    initial = VirtualLedger()
    book = record_simulated_fill(initial, ticket(), buy_fill())
    assert book.position("orb", INST).quantity == D("6")
    assert book.position("ema", INST).quantity == D("4")
    assert book.position("orb", INST).average_cost == D("101")
    assert book.position("ema", INST).average_cost == D("101")
    assert book.instrument_quantity(INST) == D("10")
    assert initial.positions == ()
    assert record_simulated_fill(book, ticket(), buy_fill()) is book


def test_sell_proportional_realized_pnl_and_duplicate_dedup():
    bought = record_simulated_fill(VirtualLedger(), ticket(), buy_fill())
    sell = SimulatedFill("sell-1", "order-sell", D("5"), D("120"), D("5"), NOW + timedelta(seconds=1))
    after = record_simulated_fill(bought, ticket(Side.SELL, "5"), sell)
    assert after.position("orb", INST).quantity == D("3")
    assert after.position("ema", INST).quantity == D("2")
    assert sum((p.realized_pnl for p in after.positions), D(0)) == D("90")
    assert record_simulated_fill(after, ticket(Side.SELL, "5"), sell) == after


def test_conflicting_fill_ids_and_overfill_rejected():
    first = record_simulated_fill(VirtualLedger(), ticket(), buy_fill(qty="4", fee="4"))
    with pytest.raises(ValueError, match="conflicting duplicate"):
        record_simulated_fill(first, ticket(), replace(buy_fill(), quantity=D("4")))
    with pytest.raises(ValueError, match="exceeds original"):
        record_simulated_fill(first, ticket(), SimulatedFill("buy-2", "order-buy", D("7"), D("100"), D("7"), NOW))


def test_cannot_virtual_short_sell_or_wrong_fill_intent():
    with pytest.raises(ValueError, match="exceeds allocated"):
        record_simulated_fill(VirtualLedger(), ticket(Side.SELL, "5"),
                              SimulatedFill("s0", "order-sell", D("5"), D("100"), D("1"), NOW))
    with pytest.raises(ValueError, match="do not match"):
        record_simulated_fill(VirtualLedger(), ticket(),
                              SimulatedFill("unexpected", "wrong", D("1"), D("100"), D("1"), NOW))


def test_simulated_e3_trade_and_virtual_book_agree():
    cfg = TradingConfig("a", (MonetaryRules("KRW", D("1")),),
                        ((INST.key, InstrumentRules(D("1"), D("1"))),))
    engine = TradingRuntime(cfg, (Money(D("1000000"), "KRW"),))
    sigs = (
        StrategySignal("s1", "orb", "1", INST, SignalDirection.LONG, D("0.01"),
                       NOW, NOW + timedelta(minutes=1), "bar1", D("95")),
        StrategySignal("s2", "ema", "1", INST, SignalDirection.LONG, D("0.01"),
                       NOW, NOW + timedelta(minutes=1), "bar1", D("95")),
    )
    plan = allocate_targets(sigs, as_of=NOW).plans[0]
    intents = propose_simulated_intents((plan,), state=engine.state, config=cfg,
                                       marks=(MarketMark(INST, D("100"), NOW, "fixture"),), as_of=NOW)
    assert len(intents) == 1
    intent = intents[0]
    assert engine.submit(intent).decision.decision.value == "APPROVED"
    engine.accept_simulated(intent.intent_id, NOW + timedelta(seconds=1))
    engine.fill_simulated(intent.intent_id, price=D("100"), quantity=intent.quantity,
                          execution_id="simfill", at=NOW + timedelta(seconds=2))
    actual_fill = engine.state.fills[0]
    virtual = record_simulated_fill(VirtualLedger(), ticket_for_plan(plan, intent), actual_fill)
    audit_virtual_against_account(virtual, engine.state)
    assert virtual.instrument_quantity(INST) == intent.quantity
    with pytest.raises(ValueError, match="mismatch"):
        audit_virtual_against_account(VirtualLedger(), engine.state)


def test_ticket_guards():
    with pytest.raises(ValueError, match="BUY ticket"):
        AttributionTicket("bad", INST, Side.BUY, D("10"))
    with pytest.raises(ValueError, match="SELL attribution"):
        AttributionTicket("bad", INST, Side.SELL, D("10"), (("one", D("1")),))


def test_full_synthetic_buy_sell_realized_pnl_matches_e3():
    cfg = TradingConfig("a", (MonetaryRules("KRW", D("1")),),
                        ((INST.key, InstrumentRules(D("1"), D("1"))),))
    eng = TradingRuntime(cfg, (Money(D("1000000"), "KRW"),))
    sigs = (
        StrategySignal("orb-in", "orb", "1", INST, SignalDirection.LONG, D("0.01"),
                       NOW, NOW + timedelta(minutes=1), "bar1", D("95")),
        StrategySignal("ema-in", "ema", "1", INST, SignalDirection.LONG, D("0.01"),
                       NOW, NOW + timedelta(minutes=1), "bar1", D("95")),
    )
    buy_plan = allocate_targets(sigs, as_of=NOW).plans[0]
    buy_intent = propose_simulated_intents((buy_plan,), state=eng.state, config=cfg,
                                           marks=(MarketMark(INST, D("100"), NOW, "fixture"),),
                                           as_of=NOW)[0]
    eng.submit(buy_intent)
    eng.accept_simulated(buy_intent.intent_id, NOW + timedelta(seconds=1))
    eng.fill_simulated(buy_intent.intent_id, price=D("100"), quantity=buy_intent.quantity,
                       execution_id="buy-ex", at=NOW + timedelta(seconds=2))
    virtual = record_simulated_fill(VirtualLedger(), ticket_for_plan(buy_plan, buy_intent),
                                     eng.state.fills[0])
    sell_at = NOW + timedelta(seconds=3)
    exit_signal = StrategySignal("exit", "risk-exit", "1", INST, SignalDirection.EXIT,
                                 D(0), sell_at, sell_at + timedelta(minutes=1), "bar-exit")
    sell_plan = allocate_targets((exit_signal,), as_of=sell_at).plans[0]
    sell_intent = OrderIntent("sell-e4", "a", "e4-allocator", INST,
                              Side.SELL, D("100"), D("120"), sell_at)
    assert eng.submit(sell_intent).decision.decision.value == "APPROVED"
    eng.accept_simulated(sell_intent.intent_id, sell_at + timedelta(seconds=1))
    eng.fill_simulated(sell_intent.intent_id, price=D("120"), quantity=D("100"),
                       execution_id="sell-ex", at=sell_at + timedelta(seconds=2))
    virtual = record_simulated_fill(virtual, ticket_for_plan(sell_plan, sell_intent),
                                     eng.state.fills[1])
    audit_virtual_against_account(virtual, eng.state)
    assert sum((p.realized_pnl for p in virtual.positions), D(0)) == eng.state.position(INST).realized_pnl
    assert virtual.instrument_quantity(INST) == D("100")


def test_positive_target_rebalance_sell_uses_existing_virtual_holdings():
    cfg = TradingConfig("a", (MonetaryRules("KRW", D("1")),),
                        ((INST.key, InstrumentRules(D("1"), D("1"))),))
    eng = TradingRuntime(cfg, (Money(D("1000000"), "KRW"),))
    first = StrategySignal("entry", "orb", "1", INST, SignalDirection.LONG,
                           D("0.01"), NOW, NOW+timedelta(minutes=1), "entry-bar", D("95"))
    plan = allocate_targets((first,), as_of=NOW).plans[0]
    buy = propose_simulated_intents((plan,), state=eng.state, config=cfg,
                                    marks=(MarketMark(INST, D("100"), NOW, "fixture"),),
                                    as_of=NOW)[0]
    assert eng.submit(buy).decision.decision.value == "APPROVED"
    eng.accept_simulated(buy.intent_id, NOW+timedelta(seconds=1))
    eng.fill_simulated(buy.intent_id, price=D("100"), quantity=buy.quantity,
                       execution_id="rebalance-buy", at=NOW+timedelta(seconds=2))
    virtual = record_simulated_fill(VirtualLedger(), ticket_for_plan(plan, buy), eng.state.fills[-1])
    later = NOW+timedelta(seconds=3)
    again = StrategySignal("rebalance", "orb", "1", INST, SignalDirection.LONG,
                           D("0.01"), later, later+timedelta(minutes=1), "up-bar", D("190"))
    target = allocate_targets((again,), as_of=later).plans[0]
    sell = propose_simulated_intents((target,), state=eng.state, config=cfg,
                                     marks=(MarketMark(INST, D("200"), later, "fixture"),),
                                     as_of=later)[0]
    assert sell.side is Side.SELL and target.target_fraction == D("0.01")
    ticket = ticket_for_plan(target, sell)
    assert not ticket.strategy_weights
    assert eng.submit(sell).decision.decision.value == "APPROVED"
    eng.accept_simulated(sell.intent_id, later+timedelta(seconds=1))
    eng.fill_simulated(sell.intent_id, price=D("200"), quantity=sell.quantity,
                       execution_id="rebalance-sell", at=later+timedelta(seconds=2))
    virtual = record_simulated_fill(virtual, ticket, eng.state.fills[-1])
    audit_virtual_against_account(virtual, eng.state)
    assert virtual.instrument_quantity(INST) == buy.quantity-sell.quantity
    assert virtual.position("orb", INST).realized_pnl == eng.state.position(INST).realized_pnl
