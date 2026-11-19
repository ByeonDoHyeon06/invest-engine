"""Kibot headerless US minute sample loader and strict coverage diagnostic.

Source documents declare consolidated equity/ETF trade volume. This is an
offline retrospective adapter: timestamps, adjustment variant, provenance and
rights must be supplied by the caller. Never synthesize missing bars.
"""
from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from invest_engine.data.calendar import StaticSessionCalendar
from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import AssetClass, InstrumentId, Market
from invest_engine.research.evaluation import EvaluationWindow, validate_window

ET = ZoneInfo("America/New_York")
MINUTE = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class KibotCoverage:
    file_sha256: str
    expected_minutes: int
    observed_minutes: int
    missing_minutes: int
    extra_minutes: int
    missing_by_session: tuple[tuple[str, int], ...]
    complete_sessions: int
    expected_sessions: int
    events: tuple[EventEnvelope[MarketPayload], ...]


def inspect_kibot_unadjusted(
    raw: bytes, instrument: InstrumentId, calendar: StaticSessionCalendar,
    window: EvaluationWindow, *, source: str,
) -> KibotCoverage:
    """Parse the selected regular-session rows without rounding OHLCV.

    The vendor raw variant is a caller-controlled provenance assertion, not
    proof of adjustment or PIT history. Input is bounded by the I/O shell.
    All rows are checked for strict shape/order and numeric consistency.
    Only the declared date span is considered for coverage; a minute on a
    holiday or outside the expected schedule in that span is an extra.
    """
    if (instrument.market is not Market.US or instrument.currency != "USD"
            or instrument.asset_class not in (AssetClass.EQUITY, AssetClass.ETF)
            or window.market_coverage != "CONSOLIDATED"
            or not source.strip() or not calendar.sessions):
        raise ValueError("KIBOT_INVALID_RESEARCH_CONTRACT")
    sessions = calendar.sessions
    if any(s.market is not instrument.market or s.venue != instrument.venue
           for s in sessions):
        raise ValueError("KIBOT_CALENDAR_INSTRUMENT_MISMATCH")
    expected: dict[datetime, str] = {}
    for session in sessions:
        cursor = session.start
        day = cursor.astimezone(ET).date().isoformat()
        if (cursor.second or cursor.microsecond or
                (session.end - cursor) % MINUTE):
            raise ValueError("KIBOT_INVALID_SESSION_MINUTE_GRID")
        while cursor < session.end:
            expected[cursor] = day
            cursor += MINUTE
    first_day = sessions[0].start.astimezone(ET).date()
    last_day = sessions[-1].end.astimezone(ET).date()
    by_time: dict[datetime, Bar] = {}
    last: datetime | None = None
    for row in csv.reader(io.StringIO(raw.decode("utf-8-sig"))):
        if len(row) != 7:
            raise ValueError("KIBOT_BAD_ROW_WIDTH")
        try:
            wall = datetime.strptime(row[0]+" "+row[1], "%m/%d/%Y %H:%M")
            if wall.strftime("%m/%d/%Y %H:%M") != row[0]+" "+row[1]:
                raise ValueError("KIBOT_BAD_TIMESTAMP_FORMAT")
            local = wall.replace(tzinfo=ET)
            if local.utcoffset() != wall.replace(tzinfo=ET, fold=1).utcoffset():
                raise ValueError("KIBOT_AMBIGUOUS_LOCAL_TIMESTAMP")
            at = local.astimezone(timezone.utc)
            if at.astimezone(ET).replace(tzinfo=None) != wall:
                raise ValueError("KIBOT_NONEXISTENT_LOCAL_TIMESTAMP")
            if last is not None and at <= last:
                raise ValueError("KIBOT_DUPLICATE_OR_UNSORTED_TIMESTAMP")
            last = at
            prices = tuple(Decimal(x) for x in row[2:6])
            volume = Decimal(row[6])
            if not volume.is_finite() or volume <= 0 or volume != volume.to_integral_value():
                raise ValueError("KIBOT_INVALID_SHARE_VOLUME")
            bar = Bar(at, at+MINUTE, prices[0], prices[1], prices[2], prices[3],
                      volume, interval=MINUTE)
        except (ArithmeticError, ValueError) as exc:
            # Never include a raw data row in public logs.
            raise ValueError("KIBOT_INVALID_BAR_RECORD") from exc
        if first_day <= wall.date() <= last_day:
            by_time[at] = bar
    missing: dict[str, int] = {}
    for at, day_key in expected.items():
        if at not in by_time:
            missing[day_key] = missing.get(day_key, 0) + 1
    observed = tuple(at for at in expected if at in by_time)
    extra = len(set(by_time)-set(expected))
    events: tuple[EventEnvelope[MarketPayload], ...] = ()
    if not missing and not extra:
        records: list[EventEnvelope[MarketPayload]] = []
        for index, at in enumerate(observed):
            bar = by_time[at]
            # Assumed historical availability; never claim witnessed receipts.
            records.append(EventEnvelope(f"{instrument.symbol}:{at.isoformat()}",
                "market.bar", source, instrument, bar.end, bar.end, bar.end, index, bar))
        events = tuple(records)
        validate_window(events, calendar, window)
    return KibotCoverage(hashlib.sha256(raw).hexdigest(), len(expected), len(observed),
                         sum(missing.values()), extra, tuple(sorted(missing.items())),
                         len(sessions)-len(missing), len(sessions), events)
