"""Strict single-instrument one-minute research windows; no provider authentication."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from invest_engine.data.calendar import SessionCalendar, StaticSessionCalendar
from invest_engine.domain.events import Bar, BarKind, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import utc_datetime

MINUTE = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class EvaluationWindow:
    start: datetime
    end: datetime
    warmup_sessions: int = 20
    market_coverage: str = "CONSOLIDATED"

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", utc_datetime(self.start))
        object.__setattr__(self, "end", utc_datetime(self.end))
        if self.start >= self.end:
            raise ValueError("EVALUATION_WINDOW_ORDER")
        if type(self.warmup_sessions) is not int or self.warmup_sessions < 20:
            raise ValueError("EVALUATION_REQUIRES_20_WARMUP_SESSIONS")
        if self.market_coverage not in ("CONSOLIDATED", "SINGLE_VENUE"):
            raise ValueError("EVALUATION_MARKET_COVERAGE_REQUIRED")


@dataclass(frozen=True, slots=True)
class WindowCoverage:
    warmup_bars: int
    evaluation_bars: int
    warmup_sessions: int
    evaluation_sessions: int


def validate_window(
    events: tuple[EventEnvelope[MarketPayload], ...],
    calendar: SessionCalendar,
    window: EvaluationWindow,
) -> WindowCoverage:
    if not events or not isinstance(calendar, StaticSessionCalendar):
        raise ValueError("EVALUATION_REQUIRES_EXPLICIT_CALENDAR_AND_BARS")
    instrument = events[0].instrument_id
    if instrument is None or any(e.instrument_id != instrument for e in events):
        raise ValueError("EVALUATION_REQUIRES_SINGLE_INSTRUMENT")
    sessions = calendar.sessions
    if any(s.market != instrument.market or s.venue != instrument.venue for s in sessions):
        raise ValueError("EVALUATION_CALENDAR_INSTRUMENT_MISMATCH")
    before = [s for s in sessions if s.end <= window.start]
    inside = [s for s in sessions if s.start >= window.start and s.end <= window.end]
    if (len(before) != window.warmup_sessions or not inside
            or len(before) + len(inside) != len(sessions)):
        raise ValueError("EVALUATION_SESSION_COUNT_OR_BOUNDARY")
    if inside[0].start != window.start or inside[-1].end != window.end:
        raise ValueError("EVALUATION_MUST_MATCH_SESSION_BOUNDARIES")
    expected_count = sum((s.end - s.start) // MINUTE for s in sessions)
    if any((s.end - s.start) % MINUTE for s in sessions) or expected_count != len(events):
        raise ValueError("EVALUATION_MISSING_OR_EXTRA_MINUTE")
    warmup_bars = 0
    index = 0
    for session in sessions:
        cursor = session.start
        while cursor < session.end:
            event = events[index]
            bar = event.payload
            if (not isinstance(bar, Bar) or bar.kind is not BarKind.TIME
                    or not bar.finalized or bar.interval != MINUTE
                    or bar.start != cursor or bar.end != cursor + MINUTE
                    or event.event_time != bar.end or event.available_at < bar.end
                    or event.received_at >= bar.end + MINUTE or event.quality_flags):
                raise ValueError("EVALUATION_INVALID_OR_MISSING_MINUTE")
            if bar.volume != bar.volume.to_integral_value():
                raise ValueError("EVALUATION_REQUIRES_INTEGRAL_SHARE_VOLUME")
            if session.end <= window.start:
                if event.received_at >= window.start:
                    raise ValueError("EVALUATION_WARMUP_NOT_KNOWN_BEFORE_START")
                warmup_bars += 1
            cursor += MINUTE
            index += 1
    return WindowCoverage(warmup_bars, len(events) - warmup_bars, len(before), len(inside))
