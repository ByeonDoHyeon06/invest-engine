"""E5.11 held delisting: explicit cash witness, no invented exit price."""
from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from decimal import Decimal as D

import pytest

from invest_engine.domain.errors import InvalidEvent
from invest_engine.research.delisting_replay import DelistingSchedule, load_delistings
from invest_engine.trading.actions import DelistingCashResolved, DelistingObserved
from invest_engine.trading.codec import decode_trade_event, encode_trade_event
from invest_engine.trading.journal import SQLiteTradingJournal
from invest_engine.trading.ledger import audit_trading_state
from test_actions_e5 import KR, T as BASE, bought, engine
from test_backtest_e5 import INST, STEP, T, feed
from test_delisting_replay_e5 import delist, runner


def resolution(*, qty: str = "100", cash: str = "6000",
               known=None, paid=None, proof: str = "a" * 64) -> DelistingCashResolved:
    now = T + 3 * STEP
    return DelistingCashResolved("delist:1", INST, D(qty), D(cash),
                                paid if paid is not None else now,
                                known if known is not None else now, "declared-cash-witness", proof)


def test_held_position_can_close_only_with_explicit_cash_receipt():
    events = feed()[:3]
    action = delist()
    schedule = DelistingSchedule((action,), (resolution(),))
    report = runner(trade=True, actions=()).run(events)
    assert report.entry_fill_count == 2
    # New opt-in evidence does not become a simulated SELL fill.
    target = _run_with_schedule(schedule)
    assert target.entry_fill_count == 2 and target.exit_fill_count == 0
    assert target.terminal_settlements[0].quantity == D("100")
    assert target.terminal_settlements[0].net_cash == D("6000")
    assert target.terminal_settlements[0].realized_pnl < 0
    assert dict(target.by_currency_end)["KRW"] == D("95990")
    assert "DELISTING_PAID:delist:1" in target.decisions[-1].reason_codes
    assert target.run_sha256 == _run_with_schedule(schedule).run_sha256
    assert target.run_sha256 != report.run_sha256


def _run_with_schedule(schedule: DelistingSchedule):
    import test_backtest_e5
    from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
    from invest_engine.domain.primitives import Money
    from invest_engine.research.backtest import HistoricalBacktest
    from invest_engine.trading.models import TradingConfig
    from invest_engine.trading.money import InstrumentRules, MonetaryRules
    from invest_engine.trading.policy import RiskLimits

    cfg = TradingConfig("sim", (MonetaryRules("KRW", D("1")),),
                        ((INST.key, InstrumentRules(D("1"), D("1"))),), fee_rate=D("0.001"))
    return HistoricalBacktest(
        calendar=StaticSessionCalendar((TradingSession(INST.market, INST.venue, T,
                                                      T + timedelta(hours=1)),)),
        strategies=(test_backtest_e5.SignalOnFirstBar(),), config=cfg,
        opening_cash=(Money(D("100000"), "KRW"),),
        risk=RiskLimits(per_trade_planned_loss=D("0.5"),
                        max_symbol_cost_fraction=D("0.2"),
                        max_total_cost_fraction=D("0.5")),
        delisting_schedule=schedule,
    ).run(feed()[:3])


def test_wrong_quantity_and_zero_holdings_refuse_cash():
    for qty in ("99", "101"):
        with pytest.raises(InvalidEvent, match="QUANTITY_MISMATCH"):
            _run_with_schedule(DelistingSchedule((delist(),), (resolution(qty=qty),)))
    # A no-trade strategy must not receive a settlement windfall.
    with pytest.raises(InvalidEvent, match="REQUIRES_HELD_SHARES"):
        _unheld_resolution()


def _unheld_resolution():
    from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
    from invest_engine.domain.primitives import Money
    from invest_engine.research.backtest import HistoricalBacktest
    from invest_engine.strategies.baselines import NoTradeStrategy
    from invest_engine.strategies.contracts import DataRequirement
    from invest_engine.trading.models import TradingConfig
    from invest_engine.trading.money import InstrumentRules, MonetaryRules

    cfg = TradingConfig("sim", (MonetaryRules("KRW", D("1")),),
                        ((INST.key, InstrumentRules(D("1"), D("1"))),))
    return HistoricalBacktest(
        calendar=StaticSessionCalendar((TradingSession(INST.market, INST.venue, T,
                                                      T+timedelta(hours=1)),)),
        strategies=(NoTradeStrategy(DataRequirement("market.bar", STEP)),),
        config=cfg, opening_cash=(Money(D("100000"), "KRW"),),
        delisting_schedule=DelistingSchedule((delist(),), (resolution(),)),
    ).run(feed()[:3])


def test_late_receipt_and_missing_issuer_link_rejected():
    with pytest.raises(ValueError, match="CASH_EVENT_REPLAY"):
        DelistingSchedule((delist(),),
                         (resolution(paid=T+4*STEP),))
    with pytest.raises(ValueError, match="ACTION_MISMATCH"):
        DelistingSchedule((), (resolution(),))
    with pytest.raises(ValueError, match="SHA-256"):
        resolution(proof="short")


def test_terminal_cash_is_event_sourced_and_restorable(tmp_path):
    path = tmp_path / "terminal.sqlite"
    at = BASE + timedelta(seconds=4)
    with SQLiteTradingJournal(path) as journal:
        eng = engine(journal=journal)
        bought(eng)
        eng.flag_delisting(DelistingObserved("delist-k", KR, at, at, "fixture"), at)
        payout = DelistingCashResolved("delist-k", KR, D("10"), D("42000"),
                                      at, at, "fixture", "f"*64)
        assert eng.resolve_delisted_cash(payout, at)
        assert not eng.resolve_delisted_cash(payout, at)
        assert eng.state.position(KR).quantity == 0
        assert eng.state.position(KR).realized_pnl == D("42000") - D("70070")
        assert eng.state.account("KRW").settled == D("971930")
        audit_trading_state(eng.state)
        snapshots = journal._read()
        assert decode_trade_event(encode_trade_event(snapshots[-1])) == snapshots[-1]
        checkpoint = eng.state.digest
    with SQLiteTradingJournal(path) as journal:
        eng = engine(journal=journal)
        assert eng.state.digest == checkpoint
        assert len(eng.state.delisting_resolutions) == 1
        assert eng.state.position(KR).quantity == 0
        # Duplicate with contradictory receipt must be treated as corruption.
        with pytest.raises(InvalidEvent, match="conflicting terminal"):
            eng.resolve_delisted_cash(DelistingCashResolved(
                "delist-k", KR, D("10"), D("60000"), at, at, "fixture", "f"*64), at)


def test_resolution_requires_exact_currency_step_and_no_future_receipt():
    at = BASE + timedelta(seconds=4)
    eng = engine()
    bought(eng)
    eng.flag_delisting(DelistingObserved("delist-k", KR, at, at, "fixture"), at)
    with pytest.raises(InvalidEvent, match="PRECISION_INVALID"):
        eng.resolve_delisted_cash(DelistingCashResolved(
            "delist-k", KR, D("10"), D("42000.01"), at, at, "fixture", "e"*64), at)
    eng2 = engine()
    bought(eng2)
    eng2.flag_delisting(DelistingObserved("delist-k", KR, at, at, "fixture"), at)
    with pytest.raises(InvalidEvent, match="NOT_YET_RECEIVED"):
        eng2.resolve_delisted_cash(DelistingCashResolved(
            "delist-k", KR, D("10"), D("42000"), at+timedelta(hours=1),
            at, "fixture", "e"*64), at)


def test_resolution_loader_is_hash_pinned_and_tagged(tmp_path):
    last = T+3*STEP
    rows = [
        {"kind":"delisting", "action_id":"delist:1", "instrument_key":INST.key,
         "effective_at":last.isoformat(), "available_at":(T-timedelta(days=1)).isoformat(),
         "source":"fixture"},
        {"kind":"cash_resolution", "action_id":"delist:1", "instrument_key":INST.key,
         "quantity":"100", "net_cash":"0", "paid_at":last.isoformat(),
         "available_at":last.isoformat(), "source":"fixture", "evidence_sha256":"d"*64},
    ]
    path=tmp_path/"delistings.jsonl"
    path.write_text("".join(json.dumps(row,sort_keys=True)+"\n" for row in rows))
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    loaded=load_delistings(path,digest,{INST.key:INST})
    assert loaded.resolutions[0].net_cash == 0  # zero recovery must be explicit
    assert loaded.delistings[0].action_id == "delist:1"
    path.write_bytes(path.read_bytes()+b"\n")
    with pytest.raises(ValueError,match="HASH_MISMATCH"):
        load_delistings(path,digest,{INST.key:INST})


def test_virtual_multiple_strategies_cash_recovery_is_conserved():
    from invest_engine.strategies.attribution import (
        VirtualLedger, VirtualPosition, resolve_virtual_delisting,
    )
    positions = (
        VirtualPosition("alpha", INST, D("40"), D("100")),
        VirtualPosition("beta", INST, D("60"), D("105")),
    )
    ledger = VirtualLedger(positions=positions)
    transformed = resolve_virtual_delisting(ledger, resolution(cash="6000"))
    assert all(v.quantity == 0 for v in transformed.positions)
    assert sum((p.realized_pnl for p in transformed.positions), D(0)) == D("6000") - D("10300")
    assert [p.realized_pnl for p in transformed.positions] == [D("-1600"), D("-2700")]
    with pytest.raises(ValueError, match="virtual attribution"):
        resolve_virtual_delisting(ledger, resolution(qty="99"))


def test_resolution_cannot_reuse_unrelated_dividend_action_id():
    from test_actions_e5 import dividend

    eng = engine()
    bought(eng)
    at = BASE + timedelta(seconds=3)
    other = dividend(at)
    eng.record_dividend(other, at)
    at += timedelta(seconds=1)
    eng.flag_delisting(DelistingObserved("delist-k", KR, at, at, "fixture"), at)
    cash_before = eng.state.account("KRW").settled
    with pytest.raises(InvalidEvent, match="DELISTING_ID_NOT_REGISTERED_FOR_INSTRUMENT"):
        eng.resolve_delisted_cash(DelistingCashResolved(
            other.action_id, KR, D("10"), D("42000"), at, at, "fixture", "f"*64), at)
    assert eng.state.account("KRW").settled == cash_before
    assert eng.state.position(KR).quantity == D("10")
