"""Exchange-session-anchored resolution aggregation: golden cases and failure policy."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, session_from_local
from invest_engine.data.resample import resample_time_bars
from invest_engine.domain.errors import InvalidEvent, UnsupportedData
from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload, TradeTick
from invest_engine.domain.primitives import InstrumentId, Market

KR_DAY = date(2026, 11, 16)


def calendar(kr_instrument: InstrumentId) -> StaticSessionCalendar:
    return StaticSessionCalendar((session_from_local(
        Market.KR, kr_instrument.venue, KR_DAY, time(9), time(15, 30), "Asia/Seoul"
    ),))


def tick(
    instrument: InstrumentId, number: int, *, minute: int, second: int = 0,
    price: str = "100", qty: str = "1", lag: timedelta = timedelta(0),
) -> EventEnvelope[MarketPayload]:
    local = datetime.combine(KR_DAY, time(9, minute, second), tzinfo=ZoneInfo("Asia/Seoul"))
    utc = local.astimezone(timezone.utc)
    return EventEnvelope(
        event_id=f"tick-{number}", event_type="market.trade", source="synthetic",
        instrument_id=instrument, event_time=utc, available_at=utc + lag,
        received_at=utc + lag, ingest_ordinal=number,
        payload=TradeTick(Decimal(price), Decimal(qty)),
    )


def input_bar(
    instrument: InstrumentId, number: int, *, begin: time,
    interval: timedelta = timedelta(minutes=1),
    open_price: str = "100", high_price: str = "105",
    low_price: str = "95", close_price: str = "102", volume: str = "10",
) -> EventEnvelope[MarketPayload]:
    start = datetime.combine(KR_DAY, begin, tzinfo=ZoneInfo("Asia/Seoul")).astimezone(timezone.utc)
    end = start + interval
    return EventEnvelope(
        event_id=f"sourcebar-{number}", event_type="market.bar", source="synthetic",
        instrument_id=instrument, event_time=end, available_at=end,
        received_at=end, ingest_ordinal=number,
        payload=Bar(start=start, end=end, open=Decimal(open_price),
                    high=Decimal(high_price), low=Decimal(low_price),
                    close=Decimal(close_price), volume=Decimal(volume), interval=interval),
    )


def test_tick_to_one_minute_ohlcv(kr_instrument: InstrumentId) -> None:
    events = [tick(kr_instrument, 1, minute=0, price="100", qty="2"),
              tick(kr_instrument, 2, minute=0, second=30, price="105", qty="3"),
              tick(kr_instrument, 3, minute=0, second=59, price="95", qty="4"),
              tick(kr_instrument, 4, minute=1, price="98", qty="5")]
    bars = resample_time_bars(reversed(events), resolution=timedelta(minutes=1),
                              calendar=calendar(kr_instrument))
    assert len(bars) == 2
    first, second = (e.payload for e in bars)
    assert (first.open, first.high, first.low, first.close, first.volume) == (
        Decimal(100), Decimal(105), Decimal(95), Decimal(95), Decimal(9))
    assert second.volume == Decimal(5)
    assert (bars[0].event_time - bars[0].payload.start) == timedelta(minutes=1)
    assert bars[0].available_at == bars[0].payload.end


def test_tick_gap_does_not_fill_missing_bars(kr_instrument: InstrumentId) -> None:
    bars = resample_time_bars([tick(kr_instrument, 1, minute=0),
                               tick(kr_instrument, 2, minute=4)],
                              resolution=timedelta(minutes=1),
                              calendar=calendar(kr_instrument))
    assert len(bars) == 2
    assert bars[1].payload.start - bars[0].payload.start == timedelta(minutes=4)


def test_session_anchoring_and_late_availability(kr_instrument: InstrumentId) -> None:
    events = [tick(kr_instrument, 1, minute=1, price="100"),
              tick(kr_instrument, 2, minute=25, price="102", lag=timedelta(minutes=35))]
    bars = resample_time_bars(events, resolution=timedelta(minutes=30),
                              calendar=calendar(kr_instrument))
    assert len(bars) == 1
    assert bars[0].payload.start == datetime(2026, 11, 16, tzinfo=timezone.utc)
    assert bars[0].payload.end == datetime(2026, 11, 16, 0, 30, tzinfo=timezone.utc)
    assert bars[0].available_at == events[1].available_at
    assert bars[0].received_at == events[1].received_at


def test_resampling_determinism_independent_of_input_iteration_order(kr_instrument: InstrumentId) -> None:
    events = [tick(kr_instrument, i, minute=i % 3, second=i * 2, price=str(100 + i))
              for i in range(8)]
    a = resample_time_bars(events, resolution=timedelta(minutes=5),
                           calendar=calendar(kr_instrument))
    b = resample_time_bars(list(reversed(events)), resolution=timedelta(minutes=5),
                           calendar=calendar(kr_instrument))
    assert a == b
    assert len({x.event_id for x in a}) == len(a)


def test_one_minute_to_thirty_minutes_without_fabricating_ticks(kr_instrument: InstrumentId) -> None:
    # A complete 30-minute source sequence. Missing even one minute fails.
    bars = [input_bar(kr_instrument, i, begin=time(9, i),
                      close_price=str(100 + i), high_price=str(105 + i))
            for i in range(30)]
    out = resample_time_bars(bars, resolution=timedelta(minutes=30),
                             calendar=calendar(kr_instrument))
    assert len(out) == 1
    payload = out[0].payload
    assert (payload.open, payload.close, payload.high, payload.low, payload.volume) == (
        Decimal(100), Decimal(129), Decimal(134), Decimal(95), Decimal(300))
    with pytest.raises(InvalidEvent, match="incomplete"):
        resample_time_bars(bars[1:], resolution=timedelta(minutes=30),
                           calendar=calendar(kr_instrument))


def test_thirty_minute_to_one_minute_is_rejected(kr_instrument: InstrumentId) -> None:
    source = input_bar(kr_instrument, 1, begin=time(9), interval=timedelta(minutes=30))
    with pytest.raises(UnsupportedData, match="lower-resolution"):
        resample_time_bars([source], resolution=timedelta(minutes=1),
                           calendar=calendar(kr_instrument))


def test_source_bar_may_not_cross_target_boundary(kr_instrument: InstrumentId) -> None:
    source = input_bar(kr_instrument, 1, begin=time(9, 25), interval=timedelta(minutes=10))
    with pytest.raises(UnsupportedData, match="crosses"):
        resample_time_bars([source], resolution=timedelta(minutes=30),
                           calendar=calendar(kr_instrument))


def test_invalid_events_are_never_aggregated(kr_instrument: InstrumentId) -> None:
    event = tick(kr_instrument, 1, minute=0)
    with pytest.raises(InvalidEvent, match="duplicate"):
        resample_time_bars([event, event], resolution=timedelta(minutes=1),
                           calendar=calendar(kr_instrument))
    with pytest.raises(InvalidEvent, match="quality"):
        resample_time_bars([replace(event, quality_flags=("STALE",))],
                           resolution=timedelta(minutes=1), calendar=calendar(kr_instrument))
    with pytest.raises(UnsupportedData, match="mix"):
        resample_time_bars([event, input_bar(kr_instrument, 2, begin=time(9))],
                           resolution=timedelta(minutes=1), calendar=calendar(kr_instrument))
    with pytest.raises(InvalidEvent, match="outside"):
        resample_time_bars([tick(kr_instrument, 3, minute=0)],
                           resolution=timedelta(minutes=1),
                           calendar=StaticSessionCalendar(()))


def test_early_close_last_bucket_is_truncated(kr_instrument: InstrumentId) -> None:
    s = session_from_local(Market.KR, kr_instrument.venue, KR_DAY,
                           time(9), time(11, 45), "Asia/Seoul")
    events = [tick(kr_instrument, 1, minute=0)]
    events.append(replace(events[0], event_id="last", ingest_ordinal=2,
                          event_time=s.end - timedelta(seconds=1),
                          available_at=s.end - timedelta(seconds=1),
                          received_at=s.end - timedelta(seconds=1)))
    bars = resample_time_bars(events, resolution=timedelta(hours=1),
                              calendar=StaticSessionCalendar((s,)))
    assert bars[-1].payload.end == s.end
    assert bars[-1].payload.end - bars[-1].payload.start == timedelta(minutes=45)
    assert bars[-1].payload.interval == timedelta(hours=1)


def test_us_dst_changes_utc_open_but_keeps_wall_clock(us_instrument: InstrumentId) -> None:
    friday = session_from_local(Market.US, us_instrument.venue, date(2026, 3, 6),
                                time(9, 30), time(16), "America/New_York")
    monday = session_from_local(Market.US, us_instrument.venue, date(2026, 3, 9),
                                time(9, 30), time(16), "America/New_York")
    assert friday.start.hour == 14  # EST (UTC-5)
    assert monday.start.hour == 13  # EDT (UTC-4)
    assert friday.end - friday.start == monday.end - monday.start


def test_dst_invalid_local_hour_rejected(us_instrument: InstrumentId) -> None:
    with pytest.raises(InvalidEvent, match="nonexistent"):
        session_from_local(Market.US, us_instrument.venue, date(2026, 3, 8),
                           time(2, 30), time(16), "America/New_York")
    with pytest.raises(InvalidEvent, match="ambiguous"):
        session_from_local(Market.US, us_instrument.venue, date(2026, 11, 1),
                           time(1, 30), time(16), "America/New_York")


def test_calendar_rejects_overlap(kr_instrument: InstrumentId) -> None:
    one = session_from_local(Market.KR, kr_instrument.venue, KR_DAY,
                             time(9), time(15, 30), "Asia/Seoul")
    with pytest.raises(InvalidEvent, match="overlapping"):
        StaticSessionCalendar((one, one))


def test_reject_bad_interval(kr_instrument: InstrumentId) -> None:
    with pytest.raises(InvalidEvent, match="resolution"):
        resample_time_bars([tick(kr_instrument, 1, minute=0)],
                           resolution=timedelta(0), calendar=calendar(kr_instrument))
