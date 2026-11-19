"""E5.14: executable hold coverage, causal protected session liquidation."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import Market, Money
from invest_engine.research.backtest import HistoricalBacktest
from invest_engine.research.evaluation import EvaluationWindow
from invest_engine.research.protection import ProtectionPolicy
from invest_engine.strategies.baselines import BuyHoldBaseline
from invest_engine.trading.models import TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.policy import RiskLimits
from test_experiment_e5 import INST, START

MINUTE = timedelta(minutes=1)


def feed(*, evaluation_days=1, session_minutes=4):
    sessions = tuple(
        TradingSession(Market.KR, "KRX", START + timedelta(days=i),
                       START + timedelta(days=i, minutes=session_minutes))
        for i in range(20 + evaluation_days)
    )
    events = []
    for session in sessions:
        for minute in range(session_minutes):
            start = session.start + minute * MINUTE
            end = start + MINUTE
            bar = Bar(start, end, D("100"), D("104"), D("96"), D("100"),
                      D("4000"), interval=MINUTE)
            n = len(events)
            events.append(EventEnvelope(f"e{n}", "market.bar", "synthetic", INST,
                                        end, end, end, n, bar))
    return events, StaticSessionCalendar(sessions), EvaluationWindow(
        sessions[20].start, sessions[-1].end)


def change_bar(events, index, **changes):
    event = events[index]
    events[index] = replace(event, payload=replace(event.payload, **changes))


def engine(calendar, window, strategy, **kwargs):
    config = TradingConfig("sim", (MonetaryRules("KRW", D("1")),),
                           ((INST.key, InstrumentRules(D("1"), D("1"))),))
    return HistoricalBacktest(
        calendar=calendar, strategies=(strategy,), config=config,
        opening_cash=(Money(D("100000"), "KRW"),),
        risk=RiskLimits(per_trade_planned_loss=D("0.5"),
                        max_symbol_cost_fraction=D("0.2"), max_total_cost_fraction=D("0.5")),
        evaluation_window=window, **kwargs,
    )


def hold(*, retry=False):
    return BuyHoldBaseline(MINUTE, D("0.05"), D("0.1"), retry_each_session=retry)


def protected(calendar, window, **kwargs):
    return engine(calendar, window, hold(),
                  protection_policy=ProtectionPolicy(enabled=True, adverse_bps=D("10")),
                  session_flat=True, **kwargs)


def test_hold_retries_after_unfilled_day_then_never_rebalances():
    events, calendar, window = feed(evaluation_days=3)
    # Day one: the limit at 100 cannot be penetrated in any later bar.
    for index in range(81, 84):
        change_bar(events, index, open=D("102"), low=D("101"), close=D("102"))
    # Day three: a fresh target at a different mark would otherwise trim holdings.
    for index in range(88, 92):
        change_bar(events, index, open=D("200"), high=D("204"), low=D("196"),
                   close=D("200"))
    legacy = engine(calendar, window, hold()).run(tuple(events))
    report = engine(calendar, window, hold(retry=True),
                    first_entry_only=True).run(tuple(events))
    assert not legacy.fills
    assert report.entry_fill_count == 1 and report.exit_fill_count == 0
    assert report.fills[0].market_event_id == "e85"
    assert "FIRST_ENTRY_ALREADY_FILLED" in report.decisions[88].reason_codes
    assert not report.decisions[88].intent_ids
    assert report.run_sha256 == engine(calendar, window, hold(retry=True),
                                      first_entry_only=True).run(tuple(events)).run_sha256


def test_hold_retry_policy_is_explicit():
    _, calendar, window = feed()
    with pytest.raises(ValueError, match="RETRY_HOLD_REQUIRES_FIRST_ENTRY_ONLY"):
        engine(calendar, window, hold(retry=True))


def test_final_bar_liquidates_preexisting_inventory_at_adverse_open():
    events, calendar, window = feed()
    change_bar(events, -1, open=D("103"), high=D("110"), low=D("91"), close=D("99"))
    report = protected(calendar, window).run(tuple(events))
    assert [(f.side, f.market_event_id) for f in report.fills] == [
        ("BUY", "e81"), ("SELL", "e83")]
    close = report.fills[-1]
    assert close.reason_code == "SESSION_CLOSE_LIQUIDATION"
    assert close.price == D("102")  # 103 less 10 bp, then floor to KRW tick.
    assert close.quantity == report.fills[0].quantity
    assert report.run_sha256 == protected(calendar, window).run(tuple(events)).run_sha256
    assert all(not d.intent_ids for d in report.decisions[:80])


def test_stop_is_active_before_scheduled_liquidation():
    events, calendar, window = feed()
    change_bar(events, 82, open=D("85"), low=D("80"), high=D("92"), close=D("90"))
    report = protected(calendar, window).run(tuple(events))
    assert report.entry_fill_count == report.exit_fill_count == 1
    assert report.fills[-1].reason_code == "GAP_BELOW_STOP"
    assert report.fills[-1].market_event_id == "e82"
    assert report.fills[-1].price == D("84")


def test_last_minute_cancels_unfilled_entry_before_crossing():
    events, calendar, window = feed()
    for index in (81, 82):
        change_bar(events, index, open=D("102"), low=D("101"), close=D("102"))
    report = protected(calendar, window).run(tuple(events))
    assert not report.fills
    assert "SESSION_CLOSE_CANCEL_PENDING" in report.decisions[-1].reason_codes


def test_insufficient_liquidity_is_not_faked_flat():
    events, calendar, window = feed()
    change_bar(events, -1, volume=D("20"))
    with pytest.raises(InvalidEvent, match="SESSION_FLAT_INSUFFICIENT_LIQUIDITY"):
        protected(calendar, window).run(tuple(events))


def test_late_entry_observation_cannot_liquidate_retroactively():
    events, calendar, window = feed(session_minutes=3)
    # Second bar is the entry fill. Its observation arrives after the last bar starts.
    event = events[-2]
    events[-2] = replace(event, received_at=event.received_at + timedelta(seconds=5))
    with pytest.raises(InvalidEvent, match="SESSION_CLOSE_LATE_ENTRY_OBSERVATION"):
        protected(calendar, window).run(tuple(events))


def test_two_minute_session_does_not_create_last_bar_entry():
    events, calendar, window = feed(session_minutes=2)
    report = protected(calendar, window).run(tuple(events))
    assert not report.fills
    assert "SESSION_CLOSE_NO_NEW_ORDERS" in report.decisions[-2].reason_codes


def test_partial_buy_and_stop_conflict_fails_closed():
    events, calendar, window = feed()
    change_bar(events, 81, volume=D("20"))  # partial fill; BUY remainder stays open
    change_bar(events, 82, open=D("85"), low=D("80"), high=D("92"), close=D("90"))
    with pytest.raises(InvalidEvent, match="SESSION_FLAT_PROTECTION_BUY_CONFLICT"):
        protected(calendar, window).run(tuple(events))


def test_orb_session_flat_end_to_end():
    from invest_engine.strategies.orb import ORBLongStrategy

    events, calendar, window = feed(evaluation_days=2, session_minutes=9)
    # Breakouts on both evaluation days, with prior-session volume evidence.
    # Raise volume at the current breakout minute only.
    for day in (20, 21):
        change_bar(events, day*9+5, high=D("108"), close=D("106"), volume=D("8000"))
        change_bar(events, day*9+6, open=D("106"), high=D("108"), low=D("103"),
                   close=D("106"))
        change_bar(events, day*9+7, open=D("106"), high=D("108"), low=D("103"),
                   close=D("106"))
        change_bar(events, day*9+8, open=D("106"), high=D("108"), low=D("103"),
                   close=D("106"))
    # Second breakout has 19 normal previous session volumes and the first
    # breakout, so the historical median remains 4000 shares.
    report = engine(calendar, window, ORBLongStrategy(),
                    protection_policy=ProtectionPolicy(enabled=True, adverse_bps=D("10")),
                    session_flat=True).run(tuple(events))
    assert report.entry_fill_count == 2 and report.exit_fill_count == 2
    assert [f.reason_code for f in report.fills] == [
        "LIMIT_FILLED", "SESSION_CLOSE_LIQUIDATION",
        "LIMIT_FILLED", "SESSION_CLOSE_LIQUIDATION"]
    assert [f.market_event_id for f in report.fills] == ["e186", "e188", "e195", "e197"]
