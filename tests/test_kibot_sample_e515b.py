"""Independent provider adapter: no made-up bars, no adjustment or rounding."""
from datetime import date, time, timedelta
from decimal import Decimal as D
from zoneinfo import ZoneInfo

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, session_from_local
from invest_engine.domain.events import Bar
from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.research.evaluation import EvaluationWindow
from invest_engine.research.kibot_sample import inspect_kibot_unadjusted

INST = InstrumentId(Market.US, "XNYS", "fixture", "FIX", "USD")


def fixture():
    start = date(2026, 10, 12)
    days = tuple(start+timedelta(days=i) for i in range(21))
    sessions = tuple(session_from_local(Market.US, "XNYS", day, time(9, 30),
                                       time(9, 32), "America/New_York") for day in days)
    rows = [f"{d:%m/%d/%Y},09:{m},100.001,101,99,100.0001,123"
            for d in days for m in (30, 31)]
    return rows, StaticSessionCalendar(sessions), EvaluationWindow(sessions[20].start,
                                                                    sessions[-1].end)


def inspect(rows, calendar, window):
    return inspect_kibot_unadjusted(("\n".join(rows)+"\n").encode(), INST,
                                   calendar, window, source="synthetic-kibot-fixture")


def test_complete_sample_uses_bar_start_and_preserves_original_decimal_price():
    rows, calendar, window = fixture()
    result = inspect(rows, calendar, window)
    assert result.expected_minutes == result.observed_minutes == 42
    assert result.missing_minutes == result.extra_minutes == 0
    assert result.complete_sessions == result.expected_sessions == 21
    assert result.file_sha256 == inspect(rows, calendar, window).file_sha256
    first = result.events[0]
    assert isinstance(first.payload, Bar)
    assert first.payload.open == D("100.001") and first.payload.close == D("100.0001")
    assert first.payload.volume == D("123")
    assert first.available_at == first.payload.end
    assert first.payload.start == calendar.sessions[0].start
    assert first.payload.start.hour == 13
    last = result.events[-1]
    assert isinstance(last.payload, Bar)
    assert last.payload.start.hour == 14  # DST ends Nov 1, 2026
    assert last.payload.start.astimezone(ZoneInfo("America/New_York")).hour == 9


def test_missing_minute_and_missing_entire_session_are_explicit_not_filled():
    rows, calendar, window = fixture()
    dropped = rows[2:41]
    result = inspect(dropped, calendar, window)
    assert result.missing_minutes == 3 and result.observed_minutes == 39
    assert result.missing_by_session == (("2026-10-12", 2), ("2026-11-01", 1))
    assert result.complete_sessions == 19
    assert result.events == ()


def test_extra_minute_is_not_silently_filtered():
    rows, calendar, window = fixture()
    rows.insert(2, rows[1].replace("09:31", "09:32"))
    result = inspect(rows, calendar, window)
    assert result.extra_minutes == 1 and result.missing_minutes == 0
    assert result.events == ()


@pytest.mark.parametrize("bad", [
    lambda r: r[0].replace(",123", ",0"),
    lambda r: r[0].replace(",123", ",3.5"),
    lambda r: r[0].replace(",123", ",NaN"),
    lambda r: r[0].replace(",101,", ",98,"),
    lambda r: r[0].replace("09:30", "01:30").replace("10/12", "11/01"),
])
def test_invalid_records_fail_closed(bad):
    rows, calendar, window = fixture()
    rows[0] = bad(rows)
    with pytest.raises(ValueError, match="KIBOT_INVALID_BAR_RECORD"):
        inspect(rows, calendar, window)


def test_duplicate_and_out_of_order_are_rejected():
    rows, calendar, window = fixture()
    with pytest.raises(ValueError, match="KIBOT_INVALID_BAR_RECORD"):
        inspect([rows[0], *rows], calendar, window)
    with pytest.raises(ValueError, match="KIBOT_INVALID_BAR_RECORD"):
        inspect([rows[1], rows[0], *rows[2:]], calendar, window)


def test_empty_file_reports_no_observed_minutes():
    _, calendar, window = fixture()
    result = inspect_kibot_unadjusted(b"", INST, calendar, window, source="fixture")
    assert result.missing_minutes == 42 and result.complete_sessions == 0
    assert result.events == ()
