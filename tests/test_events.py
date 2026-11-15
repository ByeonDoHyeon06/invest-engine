from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from invest_engine.domain.errors import InvalidEvent, UnsupportedData
from invest_engine.domain.events import (
    Bar,
    BarKind,
    BookLevel,
    EventEnvelope,
    MarketStatus,
    OrderBookSnapshot,
    QuoteTick,
    SessionState,
    TradeTick,
)
from invest_engine.domain.primitives import InstrumentId


def test_event_contract_requires_instrument_and_matching_type(
    kr_instrument: InstrumentId,
) -> None:
    at = datetime(2026, 11, 15, tzinfo=timezone.utc)
    event = EventEnvelope(
        event_id="1",
        event_type="market.trade",
        source="synthetic",
        instrument_id=kr_instrument,
        event_time=at,
        available_at=at + timedelta(milliseconds=1),
        received_at=at + timedelta(milliseconds=2),
        ingest_ordinal=0,
        payload=TradeTick(Decimal("100"), Decimal("2")),
    )
    assert event.schema_version == 1
    with pytest.raises(FrozenInstanceError):
        event.event_id = "x"  # type: ignore[misc]
    with pytest.raises(InvalidEvent, match="event_type"):
        replace(event, event_type="market.quote")
    with pytest.raises(UnsupportedData, match="schema"):
        replace(event, schema_version=99)
    with pytest.raises(InvalidEvent, match="instrument"):
        replace(event, instrument_id=None)
    with pytest.raises(InvalidEvent, match="received_at"):
        replace(event, received_at=at)
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(event, available_at=datetime(2026, 11, 15))


def test_status_global_event_can_omit_instrument() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    event = EventEnvelope(
        event_id="status",
        event_type="market.status",
        source="synthetic",
        instrument_id=None,
        event_time=now,
        available_at=now,
        received_at=now,
        ingest_ordinal=0,
        payload=MarketStatus(SessionState.HALTED, "exchange outage"),
    )
    assert event.instrument_id is None


def test_quotes_orderbook_and_bar_reject_invalid_market_data() -> None:
    with pytest.raises(InvalidEvent, match="crossed"):
        QuoteTick(Decimal(101), Decimal(1), Decimal(100), Decimal(1))
    with pytest.raises(InvalidEvent, match="non-negative"):
        QuoteTick(Decimal(99), Decimal(-1), Decimal(100), Decimal(2))
    with pytest.raises(InvalidEvent, match="descending"):
        OrderBookSnapshot(
            (BookLevel(Decimal(99), Decimal(1)), BookLevel(Decimal(100), Decimal(2))),
            (BookLevel(Decimal(101), Decimal(1)),),
        )
    with pytest.raises(InvalidEvent, match="high"):
        _bar(high=Decimal(9))
    with pytest.raises(InvalidEvent, match="interval"):
        _bar(interval=None)
    with pytest.raises(InvalidEvent, match="non-time"):
        _bar(kind=BarKind.VOLUME, interval=timedelta(minutes=1))


def _bar(
    *, high: Decimal = Decimal(110), interval: timedelta | None = timedelta(minutes=1),
    kind: BarKind = BarKind.TIME,
) -> Bar:
    now = datetime(2026, 11, 15, tzinfo=timezone.utc)
    return Bar(
        start=now, end=now + timedelta(minutes=1), open=Decimal(100),
        high=high, low=Decimal(90), close=Decimal(101), volume=Decimal(22),
        kind=kind, interval=interval,
    )


def test_bar_timestamps_normalize_to_utc() -> None:
    ny = ZoneInfo("America/New_York")
    date = datetime(2026, 3, 9, 9, 30, tzinfo=ny)
    bar = Bar(
        start=date, end=date + timedelta(minutes=30), open=Decimal(100),
        high=Decimal(101), low=Decimal(99), close=Decimal(100),
        volume=Decimal(50), interval=timedelta(minutes=30),
    )
    assert bar.start.tzinfo == timezone.utc
    assert bar.start.hour == 13  # New York DST after 2026-03-08
    assert bar.end - bar.start == timedelta(minutes=30)
