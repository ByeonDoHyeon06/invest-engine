from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from random import Random

import pytest

from invest_engine.core.clock import ReplayClock
from invest_engine.core.fixtures import synthetic_ticks
from invest_engine.core.replay import canonicalize_batch, replay_events
from invest_engine.domain.errors import InvalidEvent, StaleData, UnsupportedData
from invest_engine.domain.events import TradeTick
from invest_engine.domain.primitives import InstrumentId, Market


def test_500_market_events_have_stable_state_hash(kr_instrument: InstrumentId) -> None:
    events = synthetic_ticks(kr_instrument, count=500)
    first = replay_events(events)
    shuffled = list(events)
    Random(12).shuffle(shuffled)
    second = replay_events(shuffled)
    assert first == second
    assert first.event_count == 500
    assert first.events_by_type == (("market.trade", 500),)
    assert len(first.state_hash) == 64


def test_replay_changes_when_observation_changes(kr_instrument: InstrumentId) -> None:
    events = list(synthetic_ticks(kr_instrument, count=100))
    original = replay_events(events)
    events[52] = replace(events[52], payload=TradeTick(Decimal("999"), Decimal(5)))
    assert replay_events(events).state_hash != original.state_hash
    assert replay_events(events, run_version="new") != original


def test_duplicate_id_and_ordinal_are_not_silently_accepted(
    kr_instrument: InstrumentId,
) -> None:
    events = synthetic_ticks(kr_instrument, count=2)
    with pytest.raises(InvalidEvent, match="duplicate"):
        canonicalize_batch((*events, events[0]))
    with pytest.raises(InvalidEvent, match="duplicate"):
        canonicalize_batch((*events, replace(events[1], ingest_ordinal=0)))


def test_future_observation_cannot_be_accessed(kr_instrument: InstrumentId) -> None:
    events = synthetic_ticks(kr_instrument, count=2)
    with pytest.raises(StaleData, match="not available"):
        replay_events(events, as_of=events[0].available_at)


def test_clock_is_monotonic_and_calendar_injectable() -> None:
    at = datetime(2026, 11, 15, tzinfo=timezone.utc)
    clock = ReplayClock(at)
    with pytest.raises(UnsupportedData, match="calendar"):
        clock.is_market_open(Market.KR)
    clock.advance_to(at + timedelta(seconds=2))
    with pytest.raises(InvalidEvent, match="backwards"):
        clock.advance_to(at)

    class AlwaysClosed:
        def is_open(self, market: Market, at: datetime) -> bool:
            return False

    clock.calendar = AlwaysClosed()
    assert clock.is_market_open(Market.US) is False


def test_empty_events_are_supported() -> None:
    result = replay_events([])
    assert result.event_count == 0
    assert result.last_available_at is None


def test_two_markets_do_not_collide_on_same_ticker() -> None:
    kr = InstrumentId(Market.KR, "KRX", "SYN1", "XYZ", "KRW")
    us = InstrumentId(Market.US, "XNYS", "SYN1", "XYZ", "USD")
    assert synthetic_ticks(kr, count=1)[0].event_id != synthetic_ticks(us, count=1)[0].event_id
