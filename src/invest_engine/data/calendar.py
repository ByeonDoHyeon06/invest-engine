"""Explicit trading sessions and DST-safe local exchange-time conversion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.primitives import InstrumentId, Market, utc_datetime


@dataclass(frozen=True, slots=True)
class TradingSession:
    market: Market
    venue: str
    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.market, Market) or not isinstance(self.venue, str) or not self.venue:
            raise InvalidEvent("session requires market and venue")
        object.__setattr__(self, "start", utc_datetime(self.start, field="session.start"))
        object.__setattr__(self, "end", utc_datetime(self.end, field="session.end"))
        if self.end <= self.start:
            raise InvalidEvent("session end must follow start")


class SessionCalendar(Protocol):
    def session_for(self, instrument: InstrumentId, at: datetime) -> TradingSession | None: ...


@dataclass(frozen=True, slots=True)
class StaticSessionCalendar:
    """Caller supplies authoritative market sessions; no invented holiday calendar."""

    sessions: tuple[TradingSession, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.sessions, tuple):
            raise InvalidEvent("calendar sessions must be a tuple")
        ordered = sorted(self.sessions, key=lambda session: (session.market.value, session.venue, session.start))
        previous: dict[tuple[Market, str], TradingSession] = {}
        for session in ordered:
            key = (session.market, session.venue)
            if key in previous and previous[key].end > session.start:
                raise InvalidEvent("overlapping sessions for market/venue")
            previous[key] = session
        object.__setattr__(self, "sessions", tuple(ordered))

    def session_for(self, instrument: InstrumentId, at: datetime) -> TradingSession | None:
        instant = utc_datetime(at, field="session.lookup")
        for session in self.sessions:
            if (
                session.market == instrument.market
                and session.venue == instrument.venue
                and session.start <= instant < session.end
            ):
                return session
        return None


def _strict_local(day: date, at: time, zone: ZoneInfo) -> datetime:
    if at.tzinfo is not None:
        raise InvalidEvent("exchange wall clock must be naive")
    wall = datetime.combine(day, at)
    local0 = wall.replace(tzinfo=zone, fold=0)
    local1 = wall.replace(tzinfo=zone, fold=1)
    valid0 = local0.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == wall
    valid1 = local1.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None) == wall
    if not valid0 and not valid1:
        raise InvalidEvent("nonexistent local time (DST gap)")
    if valid0 and valid1 and local0.utcoffset() != local1.utcoffset():
        raise InvalidEvent("ambiguous local time (DST fold)")
    return (local0 if valid0 else local1).astimezone(timezone.utc)


def session_from_local(
    market: Market,
    venue: str,
    day: date,
    open_time: time,
    close_time: time,
    timezone_name: str,
    *,
    closes_next_day: bool = False,
) -> TradingSession:
    """Create one session using an explicit IANA time zone and published times."""
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidEvent("unknown exchange time zone") from exc
    start = _strict_local(day, open_time, zone)
    end = _strict_local(day + timedelta(days=int(closes_next_day)), close_time, zone)
    return TradingSession(market, venue, start, end)
