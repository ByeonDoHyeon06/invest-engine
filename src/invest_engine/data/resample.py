"""Offline, session-anchored, resolution-agnostic Time Bar aggregation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable, Literal

from invest_engine.data.calendar import SessionCalendar, TradingSession
from invest_engine.domain.errors import InvalidEvent, UnsupportedData
from invest_engine.domain.events import Bar, BarKind, EventEnvelope, MarketPayload, TradeTick
from invest_engine.domain.primitives import InstrumentId


@dataclass(frozen=True, slots=True)
class _BucketKey:
    instrument: InstrumentId
    session: TradingSession
    start: datetime
    end: datetime
    source: str


def _price(payload: MarketPayload, field: Literal["open", "high", "low", "close"]) -> Decimal:
    if isinstance(payload, TradeTick):
        return payload.price
    if isinstance(payload, Bar):
        return {"open": payload.open, "high": payload.high,
                "low": payload.low, "close": payload.close}[field]
    raise UnsupportedData("unsupported aggregation price payload")


def _bucket(session: TradingSession, instant: datetime, duration: timedelta) -> tuple[datetime, datetime]:
    position = (instant - session.start) // duration
    start = session.start + duration * position
    return start, min(start + duration, session.end)


def resample_time_bars(
    events: Iterable[EventEnvelope[MarketPayload]],
    *,
    resolution: timedelta,
    calendar: SessionCalendar,
) -> tuple[EventEnvelope[Bar], ...]:
    """Create time bars without manufacturing missing intervals or lower resolution.

    Only finalized TradeTick OR finalized time Bar inputs are accepted per instrument.
    All aggregate results are finalized after the source observations are available.
    End-of-session truncated bars carry the configured nominal interval.
    """
    if not isinstance(resolution, timedelta) or resolution <= timedelta(0):
        raise InvalidEvent("resolution must be a positive timedelta")
    values = tuple(events)
    if len({e.event_id for e in values}) != len(values):
        raise InvalidEvent("duplicate input event IDs")
    types: dict[str, type[object]] = {}
    sources: dict[str, str] = {}
    groups: dict[_BucketKey, list[EventEnvelope[MarketPayload]]] = {}
    for event in values:
        instrument = event.instrument_id
        if instrument is None:
            raise UnsupportedData("aggregation requires a market instrument")
        if event.quality_flags:
            raise InvalidEvent("cannot aggregate quality-flagged observations")
        payload = event.payload
        if not isinstance(payload, (TradeTick, Bar)):
            raise UnsupportedData("only trade ticks and time bars can form time bars")
        if instrument.key in types and types[instrument.key] is not type(payload):
            raise UnsupportedData("cannot mix trade and pre-aggregated bars for one instrument")
        if instrument.key in sources and sources[instrument.key] != event.source:
            raise UnsupportedData("cannot combine multiple provider feeds without deduplication")
        types[instrument.key] = type(payload)
        sources[instrument.key] = event.source
        at = payload.start if isinstance(payload, Bar) else event.event_time
        session = calendar.session_for(instrument, at)
        if session is None:
            raise InvalidEvent("observation outside explicitly supplied market sessions")
        start, end = _bucket(session, at, resolution)
        if isinstance(payload, Bar):
            if payload.kind is not BarKind.TIME or payload.interval is None:
                raise UnsupportedData("only time-based source bars can be resampled")
            if not payload.finalized:
                raise InvalidEvent("unfinalized bars cannot be aggregated")
            if payload.interval > resolution:
                raise UnsupportedData("cannot recreate lower-resolution bars")
            if payload.end > end or payload.start < start:
                raise UnsupportedData("source bar crosses target bucket boundary")
            if payload.end > session.end or payload.end != event.event_time:
                raise InvalidEvent("bar end/event timestamp must match its market session")
        key = _BucketKey(instrument, session, start, end, event.source)
        groups.setdefault(key, []).append(event)

    ordered_groups = sorted(groups.items(), key=lambda item: (
        item[0].end, item[0].instrument.key, item[0].start, item[0].source
    ))
    result: list[EventEnvelope[Bar]] = []
    for key, observations in ordered_groups:
        observations.sort(key=lambda e: (
            e.payload.start if isinstance(e.payload, Bar) else e.event_time,
            e.ingest_ordinal,
        ))
        if isinstance(observations[0].payload, Bar):
            expected = key.start
            for event in observations:
                bar = event.payload
                if not isinstance(bar, Bar):
                    raise InvalidEvent("heterogeneous source group")
                if bar.start != expected:
                    raise InvalidEvent("incomplete or overlapping source bar sequence")
                expected = bar.end
            if expected != key.end:
                raise InvalidEvent("incomplete source bars; no silent gap filling")
        volume = Decimal(0)
        for event in observations:
            payload = event.payload
            if isinstance(payload, TradeTick):
                volume += payload.quantity
            elif isinstance(payload, Bar):
                # Preserve each source bar's intrabar extrema separately below.
                volume += payload.volume
        open_price = _price(observations[0].payload, "open")
        close_price = _price(observations[-1].payload, "close")
        high_price = max(_price(event.payload, "high") for event in observations)
        low_price = min(_price(event.payload, "low") for event in observations)
        bar = Bar(
            start=key.start, end=key.end, open=open_price, high=high_price,
            low=low_price, close=close_price, volume=volume,
            interval=resolution, kind=BarKind.TIME, finalized=True,
        )
        stamp = "|".join([
            key.instrument.key, key.source, key.start.isoformat(), key.end.isoformat(),
            str(resolution.total_seconds()), *(event.event_id for event in observations),
        ])
        event_id = "resampled:" + hashlib.sha256(stamp.encode("utf-8")).hexdigest()
        available = max(key.end, *(event.available_at for event in observations))
        received = max(available, *(event.received_at for event in observations))
        result.append(EventEnvelope(
            event_id=event_id, event_type="market.bar", source=f"resampler:{key.source}",
            instrument_id=key.instrument, event_time=key.end, available_at=available,
            received_at=received, ingest_ordinal=len(result), payload=bar,
        ))
    return tuple(result)
