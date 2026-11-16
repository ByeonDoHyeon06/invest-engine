"""E3.3 market valuation/continuous-risk regression and hostile input fixtures."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.primitives import InstrumentId, Market, Money
from invest_engine.trading.codec import decode_trade_event, encode_trade_event
from invest_engine.trading.journal import SQLiteTradingJournal
from invest_engine.trading.ledger import RiskObserved
from invest_engine.trading.models import DecisionStatus, OrderIntent, Side, TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.monitoring import (
    ExternalAccountReference, FxMark, MarketMark, MonitorInput,
    ReferencePosition, SessionBaseline,
)
from invest_engine.trading.policy import RiskLimits
from invest_engine.trading.runtime import TradingRuntime

UTC = timezone.utc
T = datetime(2026, 11, 16, 1, 0, tzinfo=UTC)
KR = InstrumentId(Market.KR, "KRX", "KR7005930003", "005930", "KRW")
US = InstrumentId(Market.US, "NASDAQ", "US0378331005", "AAPL", "USD")


def create(*, usd: bool = False, reference: bool = False, journal=None) -> TradingRuntime:
    balances = (Money(D("1000000"), "KRW"),)
    cash_rules = (MonetaryRules("KRW", D("1")),)
    if usd:
        balances += (Money(D("1000.00"), "USD"),)
        cash_rules += (MonetaryRules("USD", D("0.01")),)
    config = TradingConfig(
        "sim", cash_rules,
        ((KR.key, InstrumentRules(D("1"), D("1"))),
         (US.key, InstrumentRules(D("0.01"), D("1")))),
    )
    return TradingRuntime(
        config, balances, RiskLimits(require_monitoring=True,
                                    require_account_reference=reference),
        journal=journal, checkpoint_interval=2,
    )


def snapshot(
    at: datetime, *, price: D = D("7000"), usd: bool = False,
    fx: bool = True, reference: ExternalAccountReference | None = None,
    mark_age: timedelta = timedelta(0),
    session: str = "KR-2026-11-16",
    baseline_kr: D = D("1000000"),
) -> MonitorInput:
    markets = (MarketMark(KR, price, at - mark_age, "synthetic"),)
    currency_baselines = (SessionBaseline("KRW", session, baseline_kr, T),)
    rate = ()
    if usd:
        currency_baselines += (SessionBaseline("USD", session, D("1000"), T),)
        if fx:
            rate = (FxMark("USD", "KRW", D("1350"), at, "synthetic-fx"),)
    return MonitorInput(at, session, "KRW", markets, rate, currency_baselines, reference)


def buy(name: str, at: datetime, quantity: str = "10") -> OrderIntent:
    return OrderIntent(name, "sim", "fixture", KR, Side.BUY,
                       D(quantity), D("7000"), at, D("6800"))


def seed(run: TradingRuntime) -> datetime:
    # Synthetic bought shares before the monitoring requirement is activated
    # by an observation. An initial monitor is still mandatory for submission.
    run.observe_market_and_account(snapshot(T))
    assert run.submit(buy("first", T + timedelta(seconds=1))).decision.decision is DecisionStatus.APPROVED
    run.accept_simulated("first", T + timedelta(seconds=2))
    run.fill_simulated("first", quantity=D("10"), price=D("7000"),
                       execution_id="f1", at=T + timedelta(seconds=3))
    return T + timedelta(seconds=3)


def test_monitor_required_for_entry_and_marked_approval():
    run = create()
    assert run.submit(buy("before", T)).decision.reason_codes == ("MARK_MONITORING_REQUIRED",)
    result = run.observe_market_and_account(snapshot(T + timedelta(seconds=1)))
    assert result.healthy
    assert result.converted_equity == D("1000000")
    assert run.submit(buy("now", T + timedelta(seconds=2))).decision.decision is DecisionStatus.APPROVED
    assert run.state.account("KRW").reserved == D("70070")
    # Every ledger change invalidates the previous mark/portfolio assessment.
    assert run.submit(buy("again", T + timedelta(seconds=3))).decision.reason_codes == ("MARK_RECHECK_AFTER_STATE_CHANGE",)


def test_unobserved_new_symbol_is_blocked_and_revaluation_allowed():
    run = create()
    clean = MonitorInput(T, "KR-2026-11-16", "KRW", baselines=(
        SessionBaseline("KRW", "KR-2026-11-16", D("1000000"), T),
    ))
    assert run.observe_market_and_account(clean).healthy
    assert run.submit(buy("no-quote", T)).decision.reason_codes == ("ENTRY_MARK_MISSING",)
    assert run.observe_market_and_account(snapshot(T + timedelta(seconds=1))).healthy
    assert run.submit(buy("yes-quote", T + timedelta(seconds=2))).decision.decision is DecisionStatus.APPROVED


def test_mark_staleness_and_future_rejected_with_reason():
    run = create()
    t = T + timedelta(minutes=5)
    stale = run.observe_market_and_account(snapshot(t, mark_age=timedelta(minutes=5)))
    assert stale.healthy  # No held shares yet; entry quote still must be fresh
    # No position has yet been bought, but proposed entry must check its own mark.
    assert run.submit(buy("entry", t)).decision.reason_codes == ("ENTRY_MARK_STALE",)
    future = run.observe_market_and_account(snapshot(t + timedelta(seconds=1),
                                                   mark_age=timedelta(seconds=-1)))
    assert future.healthy  # no held shares; proposed entry still detects future quote
    assert run.submit(buy("future", t + timedelta(seconds=1))).decision.reason_codes == ("ENTRY_MARK_STALE",)


def test_missing_currency_fx_blocks_aggregate_instead_of_partial_total():
    run = create(usd=True)
    t = T + timedelta(seconds=1)
    incomplete = run.observe_market_and_account(snapshot(t, usd=True, fx=False))
    assert incomplete.converted_equity is None
    assert "FX_MARK_MISSING" in incomplete.reasons
    fixed = run.observe_market_and_account(snapshot(t + timedelta(seconds=1), usd=True))
    assert fixed.healthy
    assert fixed.converted_equity == D("2350000")
    assert run.submit(buy("fx-ok", t + timedelta(seconds=2))).decision.decision is DecisionStatus.APPROVED


def test_mark_to_market_daily_loss_is_latched_for_session_and_not_reversed():
    run = create()
    seed(run)
    t = T + timedelta(seconds=4)
    loss = run.observe_market_and_account(snapshot(t, price=D("5000")))
    assert "DAILY_LOSS_LIMIT" in loss.reasons
    assert loss.valuations[0].unrealized_pnl == D("-20070")
    assert loss.valuations[0].equity == D("979930")
    assert loss.valuations[0].daily_return == D("-0.02007")
    assert run.submit(buy("blocked", t + timedelta(seconds=1))).decision.reason_codes == ("DAILY_LOSS_LATCHED",)
    recovery = run.observe_market_and_account(snapshot(t + timedelta(seconds=2)))
    assert recovery.healthy
    assert run.submit(buy("still-blocked", t + timedelta(seconds=3))).decision.reason_codes == ("DAILY_LOSS_LATCHED",)
    # New session is a new monitored risk context (exchange calendar remains E7).
    next_day = T + timedelta(days=1)
    new_session = "KR-2026-11-17"
    clean = run.observe_market_and_account(snapshot(next_day, session=new_session,
                                                       baseline_kr=D("999930")))
    assert clean.healthy
    assert run.submit(buy("next-session", next_day + timedelta(seconds=1), "1")).decision.decision is DecisionStatus.APPROVED


def test_missing_position_mark_fails_closed_not_valued_at_cost():
    run = create()
    seed(run)
    t = T + timedelta(seconds=4)
    without = MonitorInput(t, "KR-2026-11-16", "KRW", baselines=(
        SessionBaseline("KRW", "KR-2026-11-16", D("1000000"), T),
    ))
    evaluation = run.observe_market_and_account(without)
    assert "MARK_MISSING" in evaluation.reasons
    assert not evaluation.healthy
    assert evaluation.converted_equity is None
    assert evaluation.valuations[0].equity is None
    assert "DAILY_LOSS_LIMIT" not in evaluation.reasons
    assert not run.state.daily_loss_sessions
    assert run.submit(buy("blocked", t + timedelta(seconds=1))).decision.decision is DecisionStatus.REJECTED


def test_cash_reference_mismatch_latches_and_requires_healthy_review():
    run = create(reference=True)
    t = T + timedelta(seconds=1)
    bad = ExternalAccountReference("sim", t, (Money(D("999000"), "KRW"),), ())
    assessed = run.observe_market_and_account(snapshot(t, reference=bad))
    assert "CASH_RECONCILIATION_MISMATCH" in assessed.reasons
    assert run.state.reconciliation_hold
    assert run.submit(buy("blocked", t + timedelta(seconds=1))).decision.reason_codes == ("ACCOUNT_RECONCILIATION_REVIEW_REQUIRED",)
    with pytest.raises(InvalidEvent, match="healthy"):
        run.review_reconciliation_hold(reviewed_by="operator", at=t + timedelta(seconds=2))
    # The failed attempt halts this runtime under E3 fail-closed rules; use a
    # second runtime to demonstrate manual release path without invalid event.


def test_reconciliation_happy_review_after_mismatch_and_restart(tmp_path):
    db = tmp_path / "mon.sqlite"
    t = T + timedelta(seconds=1)
    with SQLiteTradingJournal(db) as j:
        run = create(reference=True, journal=j)
        bad = ExternalAccountReference("sim", t, (Money(D("999000"), "KRW"),), ())
        run.observe_market_and_account(snapshot(t, reference=bad))
        digest = run.state.digest
    with SQLiteTradingJournal(db) as j:
        run = create(reference=True, journal=j)
        assert run.state.digest == digest
        assert run.state.reconciliation_hold
        ref = ExternalAccountReference("sim", t + timedelta(seconds=1),
                                       (Money(D("1000000"), "KRW"),), ())
        assert run.observe_market_and_account(snapshot(t + timedelta(seconds=1), reference=ref)).healthy
        assert run.submit(buy("before-review", t + timedelta(seconds=2))).decision.reason_codes == ("ACCOUNT_RECONCILIATION_REVIEW_REQUIRED",)
        # New risk observation after rejected order, then manual clear.
        t2 = t + timedelta(seconds=3)
        ref2 = ExternalAccountReference("sim", t2, (Money(D("1000000"), "KRW"),), ())
        run.observe_market_and_account(snapshot(t2, reference=ref2))
        run.review_reconciliation_hold(reviewed_by="operator", at=t2 + timedelta(seconds=1))
        assert not run.state.reconciliation_hold
        # A review is an event, so a fresh mark is mandatory before BUY.
        t3 = t2 + timedelta(seconds=2)
        ref3 = ExternalAccountReference("sim", t3, (Money(D("1000000"), "KRW"),), ())
        run.observe_market_and_account(snapshot(t3, reference=ref3))
        assert run.submit(buy("approved", t3 + timedelta(seconds=1))).decision.decision is DecisionStatus.APPROVED
    with SQLiteTradingJournal(db) as j:
        restored = create(reference=True, journal=j)
        assert not restored.state.reconciliation_hold
        assert restored.state.order("approved") is not None


def test_position_and_external_orders_comparison():
    run = create(reference=True)
    ref = ExternalAccountReference("sim", T, (Money(D("1000000"), "KRW"),),
                                   (ReferencePosition(KR.key, D("1")),), ("ghost",))
    result = run.observe_market_and_account(snapshot(T, reference=ref))
    assert "POSITION_RECONCILIATION_MISMATCH" in result.reasons
    assert "ORDER_RECONCILIATION_MISMATCH" in result.reasons


def test_monitor_event_codec_roundtrip_and_deterministic_state():
    a, b = create(usd=True), create(usd=True)
    record = snapshot(T, usd=True)
    assert a.observe_market_and_account(record) == b.observe_market_and_account(record)
    assert a.state.digest == b.state.digest
    event = a.state.seen_events
    assert "risk-observation:0" in event
    original = RiskObserved(record)
    assert original.observation == record
    from invest_engine.trading.ledger import TradingEvent
    wire = TradingEvent("test", 0, T, original)
    assert decode_trade_event(encode_trade_event(wire)) == wire


def test_guard_requires_valid_baseline_and_future_fx_not_allowed():
    run = create(usd=True)
    late = FxMark("USD", "KRW", D("1350"), T + timedelta(seconds=2), "feed")
    obs = snapshot(T, usd=True)
    risk = MonitorInput(obs.checked_at, obs.session_id, obs.base_currency, obs.marks,
                        (late,), obs.baselines)
    out = run.observe_market_and_account(risk)
    assert "FX_MARK_STALE_OR_FUTURE" in out.reasons
    assert out.converted_equity is None


def test_invalid_monitor_inputs_rejected():
    with pytest.raises(ValueError, match="duplicate"):
        MonitorInput(T, "KR-2026-11-16", "KRW", marks=(
            MarketMark(KR, D("7000"), T, "synthetic"),
            MarketMark(KR, D("7001"), T, "synthetic"),
        ))
    with pytest.raises(ValueError, match="FX base"):
        FxMark("KRW", "KRW", D("1"), T, "synthetic")


def test_marked_position_is_used_for_symbol_exposure_not_original_cost():
    run = create()
    seed(run)
    t = T + timedelta(seconds=4)
    check = run.observe_market_and_account(snapshot(t, price=D("7500")))
    assert check.healthy
    # Original book cost 70,070 + 28,000 = 98,070 < 10% initial equity,
    # while current marked exposure 75,000 + 28,000 > 10% marked equity.
    declined = run.submit(buy("extra", t + timedelta(seconds=1), "4"))
    assert declined.decision.reason_codes == ("SYMBOL_COST_LIMIT",)


def test_no_day_baseline_or_stale_fx_fails_without_daily_loss_latch():
    run = create(usd=True)
    t = T + timedelta(minutes=4)
    obs = snapshot(t, usd=True)
    wrong_session = SessionBaseline("KRW", "KR-OLD", D("1000000"), T)
    stale_fx = FxMark("USD", "KRW", D("1350"), T, "fx")
    check = MonitorInput(t, obs.session_id, "KRW", obs.marks, (stale_fx,),
                         (wrong_session, obs.baselines[1]))
    out = run.observe_market_and_account(check)
    assert "SESSION_BASELINE_MISSING" in out.reasons
    assert "FX_MARK_STALE_OR_FUTURE" in out.reasons
    assert not run.state.daily_loss_sessions


def test_monitor_result_is_replayed_from_original_inputs_not_trusted_output(tmp_path):
    db = tmp_path / "replay-risk.sqlite"
    with SQLiteTradingJournal(db) as j:
        run = create(journal=j)
        assert run.observe_market_and_account(snapshot(T)).healthy
        before = run.state.digest
    with SQLiteTradingJournal(db) as j:
        run = create(journal=j)
        assert run.state.digest == before
        assert run.state.monitoring is not None
        assert run.state.monitoring.healthy
    with SQLiteTradingJournal(db) as j:
        # New policies must not silently reuse the same journal: the policy is
        # bound to the identity hashed into the SQLite trading_metadata table.
        strict = RiskLimits(require_monitoring=True, max_daily_loss_fraction=D("0.005"))
        config = TradingConfig("sim", (MonetaryRules("KRW", D("1")),), (
            (KR.key, InstrumentRules(D("1"), D("1"))),
            (US.key, InstrumentRules(D("0.01"), D("1"))),
        ))
        with pytest.raises(InvalidEvent, match="differs"):
            TradingRuntime(config, (Money(D("1000000"), "KRW"),), strict, journal=j)


def test_synthetic_external_account_reference_cannot_precede_last_fill():
    run = create(reference=True)
    # Need a healthy monitored snapshot to create the fill first.
    ref = ExternalAccountReference("sim", T, (Money(D("1000000"), "KRW"),), ())
    run.observe_market_and_account(snapshot(T, reference=ref))
    run.submit(buy("first", T + timedelta(seconds=1)))
    run.accept_simulated("first", T + timedelta(seconds=2))
    run.fill_simulated("first", price=D("7000"), quantity=D("10"),
                       execution_id="first-fill", at=T + timedelta(seconds=3))
    stale = ExternalAccountReference("sim", T + timedelta(seconds=1),
                                     (Money(D("1000000"), "KRW"),), ())
    out = run.observe_market_and_account(snapshot(T + timedelta(seconds=4), reference=stale))
    assert out.reasons == ("REFERENCE_STALE_OR_FUTURE",)


def test_monitor_codec_rejects_invalid_decimal_by_canonical_boundary():
    from invest_engine.trading.ledger import TradingEvent
    payload = encode_trade_event(TradingEvent("risktest", 0, T, RiskObserved(snapshot(T))))
    corrupted = payload.replace(b'"7000"', b'"NaN"')
    with pytest.raises(InvalidEvent):
        decode_trade_event(corrupted)


def test_position_reducing_sell_is_possible_when_mark_feed_is_down():
    run = create()
    seed(run)
    t = T + timedelta(seconds=4)
    no_price = MonitorInput(t, "KR-2026-11-16", "KRW", baselines=(
        SessionBaseline("KRW", "KR-2026-11-16", D("1000000"), T),
    ))
    assert not run.observe_market_and_account(no_price).healthy
    exit_intent = OrderIntent("risk-reduction", "sim", "operator", KR, Side.SELL,
                              D("10"), D("6900"), t + timedelta(seconds=1))
    assert run.submit(exit_intent).decision.decision is DecisionStatus.APPROVED
    assert run.state.position(KR).reserved_sell == D("10")  # type: ignore[union-attr]
