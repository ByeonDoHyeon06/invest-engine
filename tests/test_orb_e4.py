from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId
from invest_engine.strategies.orb import ORBLongStrategy, ORBParameters
from invest_engine.strategies.runtime import StrategyRunner
from invest_engine.strategies.orb_screen import ORBScreen, ScreenedORB

D0 = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
STEP = timedelta(minutes=1)


def make_feed(inst: InstrumentId, *, breakout: bool = True,
              missing: bool = False, current_volume: str = "30",
              breakout_days: tuple[int, ...] = (20,), n_days: int = 21):
    sessions = tuple(TradingSession(inst.market, inst.venue,
                         D0 + timedelta(days=i), D0 + timedelta(days=i, hours=1))
                     for i in range(n_days))
    events = []
    for day, session in enumerate(sessions):
        for minute in range(7):
            if missing and day == 20 and minute == 3:
                continue
            at = session.start + STEP * minute
            was_breakout = day in breakout_days and breakout and minute == 5
            close = D("101") if was_breakout else D("99")
            high = D("102") if was_breakout else D("100")
            volume = D(current_volume) if was_breakout else D("10")
            bar = Bar(at, at+STEP, D("99"), high, D("95"), close, volume, interval=STEP)
            event_time = at + STEP
            idx = len(events)
            events.append(EventEnvelope(f"{day}-{minute}", "market.bar", "synthetic", inst,
                                        event_time, event_time, event_time, idx, bar))
    return StaticSessionCalendar(sessions), events


def run_feed(strategy, cal, events):
    runner = StrategyRunner(strategy, cal)
    return [y for ev in events for y in runner.accept(ev).signals]


def test_orb_breakout_on_day_21_and_once(kr_instrument):
    cal, events = make_feed(kr_instrument)
    strategy = ORBLongStrategy()
    signals = run_feed(strategy, cal, events)
    assert len(signals) == 1
    signal = signals[0]
    assert signal.trigger_event_id == "20-5"
    assert signal.stop_price is not None and signal.stop_price < D("101")
    assert signal.target_fraction == D("0.05")
    assert signal.reason_codes[0] == "OPENING_RANGE_BREAKOUT"
    assert ORBLongStrategy().snapshot() == b"[]"
    restored = ORBLongStrategy()
    restored.restore(strategy.snapshot())
    assert restored.snapshot() == strategy.snapshot()


def test_orb_requires_complete_opening_range(kr_instrument):
    cal, events = make_feed(kr_instrument, missing=True)
    assert run_feed(ORBLongStrategy(), cal, events) == []


def test_orb_requires_sufficient_historical_volume(kr_instrument):
    cal, events = make_feed(kr_instrument)
    events = [e for e in events if not e.event_id.startswith("10-")]
    events = [replace(e, ingest_ordinal=n) for n, e in enumerate(events)]
    assert run_feed(ORBLongStrategy(), cal, events) == []


def test_orb_requires_volume_multiplier(kr_instrument):
    cal, events = make_feed(kr_instrument, current_volume="12")
    assert run_feed(ORBLongStrategy(), cal, events) == []


def test_orb_does_not_invent_recovered_price_or_same_bar_fill(kr_instrument):
    cal, events = make_feed(kr_instrument, breakout=False)
    assert run_feed(ORBLongStrategy(), cal, events) == []


def test_us_custom_opening_range(kr_instrument, us_instrument):
    cal, events = make_feed(us_instrument)
    assert run_feed(ORBLongStrategy(ORBParameters(opening_us=timedelta(minutes=5))), cal, events)
    assert not run_feed(ORBLongStrategy(), cal, events)


def test_invalid_orb_params_and_snapshot():
    with pytest.raises(ValueError):
        ORBParameters(timeframe=timedelta(minutes=2))
    with pytest.raises(ValueError):
        ORBLongStrategy().restore(b"not json")


def test_screen_reduces_weekly_signals_without_changing_original(kr_instrument):
    cal, events = make_feed(kr_instrument, breakout_days=(20, 21), n_days=22)
    baseline = run_feed(ORBLongStrategy(), cal, events)
    assert len(baseline) == 2
    screened = ScreenedORB(ORBParameters(), ORBScreen(once_per_week=True))
    signals = run_feed(screened, cal, events)
    assert len(signals) == 1
    assert signals[0].trigger_event_id == baseline[0].trigger_event_id
    assert signals[0].strategy_id == screened.manifest.strategy_id
    assert signals[0].stop_price == baseline[0].stop_price
    restored = ScreenedORB(ORBParameters(), ORBScreen(once_per_week=True))
    restored.restore(screened.snapshot())
    assert restored.snapshot() == screened.snapshot()
    with pytest.raises(ValueError):
        restored.restore(b'{"inner":[],"weeks":[["bad","2026-W99"]]}')


def test_range_cost_proxy_and_original_constraints(kr_instrument):
    cal, events = make_feed(kr_instrument)
    allowed = ScreenedORB(ORBParameters(), ORBScreen(minimum_range_bps=D("200")))
    assert len(run_feed(allowed, cal, events)) == 1
    denied = ScreenedORB(ORBParameters(), ORBScreen(minimum_range_bps=D("600")))
    assert not run_feed(denied, cal, events)
    cal, events = make_feed(kr_instrument, missing=True)
    assert not run_feed(ScreenedORB(ORBParameters(), ORBScreen(True, D("200"))), cal, events)


def test_invalid_screen_and_snapshot(kr_instrument):
    with pytest.raises(ValueError):
        ORBScreen()
    with pytest.raises(ValueError):
        ORBScreen(minimum_range_bps=D("-1"))
    strategy = ScreenedORB(ORBParameters(), ORBScreen(True))
    with pytest.raises(ValueError):
        strategy.restore(b"[]")
