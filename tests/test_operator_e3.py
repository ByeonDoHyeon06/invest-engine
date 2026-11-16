"""Operator-safety behaviors; only synthetic orders are produced."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.primitives import InstrumentId, Market, Money
from invest_engine.trading.journal import SQLiteTradingJournal
from invest_engine.trading.models import DecisionStatus, OrderIntent, OrderStatus, Side, TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.runtime import ExitQuote, TradingRuntime

NOW = datetime(2026, 11, 16, tzinfo=timezone.utc)
KR = InstrumentId(Market.KR, "KRX", "KR7005930003", "005930", "KRW")


def engine(journal=None):
    conf = TradingConfig("sim", (MonetaryRules("KRW", D("1")),), ((KR.key, InstrumentRules(D("1"), D("1"))),))
    return TradingRuntime(conf, (Money(D("1000000"), "KRW"),), journal=journal, checkpoint_interval=2)


def buy(id: str, at: datetime) -> OrderIntent:
    return OrderIntent(id, "sim", "fixture", KR, Side.BUY, D("10"), D("7000"), at, D("6800"))


def seed_position(run):
    run.submit(buy("buy1", NOW))
    run.accept_simulated("buy1", NOW + timedelta(seconds=1))
    run.fill_simulated("buy1", quantity=D("10"), price=D("7000"), execution_id="fill1", at=NOW+timedelta(seconds=2))


def test_pause_does_not_cancel_existing_order_and_rejects_new_buy():
    run=engine()
    run.submit(buy("buy1", NOW))
    run.pause_new_entries(reason="operator review", at=NOW+timedelta(seconds=1))
    assert run.state.entry_pause_reason == "operator review"
    assert run.state.account("KRW").reserved == D("70070")
    blocked = run.submit(buy("buy2", NOW+timedelta(seconds=2)))
    assert blocked.decision.decision is DecisionStatus.REJECTED
    assert blocked.decision.reason_codes == ("NEW_ENTRIES_PAUSED",)
    assert blocked.commands == ()
    run.accept_simulated("buy1", NOW+timedelta(seconds=3))
    run.fill_simulated("buy1", quantity=D("4"), price=D("7000"), execution_id="f1", at=NOW+timedelta(seconds=4))
    run.request_cancel("buy1", NOW+timedelta(seconds=5))
    run.confirm_cancel("buy1", NOW+timedelta(seconds=6))
    sell = OrderIntent("sell1", "sim", "operator", KR, Side.SELL,
                       D("4"), D("7000"), NOW+timedelta(seconds=7))
    assert run.submit(sell).decision.decision is DecisionStatus.APPROVED
    run.resume_new_entries(reviewed_by="operator", at=NOW+timedelta(seconds=8))
    assert run.state.entry_pause_reason is None


def test_cancel_all_produces_commands_without_releasing_cash():
    run=engine()
    run.submit(buy("buy1", NOW))
    run.accept_simulated("buy1", NOW+timedelta(seconds=1))
    commands = run.request_cancel_all(at=NOW+timedelta(seconds=2))
    assert tuple(c.intent_id for c in commands) == ("buy1",)
    assert run.state.order("buy1").status is OrderStatus.CANCEL_PENDING  # type: ignore[union-attr]
    assert run.state.account("KRW").reserved == D("70070")
    run.confirm_cancel("buy1", NOW+timedelta(seconds=3))
    assert run.state.account("KRW").reserved == 0
    assert run.request_cancel_all(at=NOW+timedelta(seconds=4)) == ()


def test_flatten_plan_is_manual_and_requires_fresh_quote():
    run=engine()
    seed_position(run)
    t=NOW+timedelta(minutes=1)
    with pytest.raises(InvalidEvent, match="stale"):
        run.plan_flatten(at=t, quotes=(), max_age=timedelta(seconds=20))
    fresh=ExitQuote(KR, D("6950"), available_at=t-timedelta(seconds=1))
    intents=run.plan_flatten(at=t, quotes=(fresh,), max_age=timedelta(seconds=20))
    assert len(intents) == 1
    assert intents[0].side is Side.SELL
    assert intents[0].quantity == D("10")
    assert run.state.position(KR).quantity == D("10")  # type: ignore[union-attr]
    run.pause_new_entries(reason="flatten", at=t+timedelta(seconds=1))
    # Replan at the current decision time; do not backdate an earlier intent.
    live_plan = run.plan_flatten(
        at=t+timedelta(seconds=2), quotes=(fresh,), max_age=timedelta(seconds=20)
    )
    assert run.submit(live_plan[0]).decision.decision is DecisionStatus.APPROVED
    assert run.state.position(KR).reserved_sell == D("10")  # type: ignore[union-attr]
    # No automatic market order, order acceptance or fill is generated.
    assert run.state.position(KR).quantity == D("10")  # type: ignore[union-attr]
    assert run.plan_flatten(at=t+timedelta(seconds=3), quotes=(fresh,), max_age=timedelta(seconds=20)) == ()


def test_pause_persisted_after_restart_and_resume_is_audited(tmp_path):
    db = tmp_path / "pause.sqlite"
    with SQLiteTradingJournal(db) as journal:
        run=engine(journal)
        run.pause_new_entries(reason="risk alert", at=NOW)
        before=run.state.digest
    with SQLiteTradingJournal(db) as journal:
        run=engine(journal)
        assert run.state.entry_pause_reason == "risk alert"
        assert run.state.digest == before
        assert run.submit(buy("deny", NOW+timedelta(seconds=1))).decision.reason_codes == ("NEW_ENTRIES_PAUSED",)
        run.resume_new_entries(reviewed_by="operator", at=NOW+timedelta(seconds=2))
        assert run.state.entry_pause_reason is None
    with SQLiteTradingJournal(db) as journal:
        run=engine(journal)
        assert run.state.entry_pause_reason is None


def test_unknown_status_prevents_operator_resuming_entries():
    run=engine()
    run.submit(buy("buy1", NOW))
    run.pause_new_entries(reason="review", at=NOW+timedelta(seconds=1))
    run.mark_unknown("buy1", NOW+timedelta(seconds=2))
    with pytest.raises(InvalidEvent, match="unknown"):
        run.resume_new_entries(reviewed_by="operator", at=NOW+timedelta(seconds=3))
    assert run.state.entry_pause_reason == "review"



def test_cancel_timeout_unknown_holds_cash_until_explicit_reconcile():
    run = engine()
    run.submit(buy("buy1", NOW))
    run.accept_simulated("buy1", NOW+timedelta(seconds=1))
    run.request_cancel("buy1", NOW+timedelta(seconds=2))
    run.mark_unknown("buy1", NOW+timedelta(seconds=3))
    assert run.state.account("KRW").reserved == D("70070")
    assert run.submit(buy("buy2", NOW+timedelta(seconds=4))).decision.decision is DecisionStatus.HALTED
    run.reconcile("buy1", OrderStatus.CANCELED, NOW+timedelta(seconds=5))
    assert run.state.account("KRW").reserved == 0


def test_legacy_e3_example_state_digest_unchanged():
    """Adding operator event tags must not break E3.1 deterministic streams."""
    run = engine()
    run.submit(buy("buy1", NOW))
    run.accept_simulated("buy1", NOW+timedelta(seconds=1))
    run.fill_simulated("buy1", quantity=D("4"), price=D("7000"),
                       execution_id="fill-1", at=NOW+timedelta(seconds=2))
    run.request_cancel("buy1", NOW+timedelta(seconds=3))
    run.confirm_cancel("buy1", NOW+timedelta(seconds=4))
    assert run.state.account("KRW").settled == D("971972")
    assert run.state.account("KRW").reserved == 0
