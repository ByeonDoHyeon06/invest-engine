"""Registered temporal expansion and exact warmup boundary checks."""
from datetime import date, timedelta
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from alpaca_raw_minute_pilot import build_grid  # noqa: E402
from alpaca_reduced_turnover import registered_window  # noqa: E402


def test_registered_panel_rejects_unplanned_months_and_holdout():
    for month in (1, 4, 7, 10):
        assert registered_window(2023, month) == (2023, month)
    assert registered_window(2022, 10) == (2022, 10)
    for year, month in ((2023, 2), (2022, 1), (2026, 1), (2024, 7), (True, 1)):
        with pytest.raises(ValueError, match="UNREGISTERED"):
            registered_window(year, month)


def test_january_cross_year_and_exact_legacy_windows():
    pytest.importorskip("exchange_calendars")
    _, sessions, first, last = build_grid("AAPL", 1, 2023)
    assert first == date(2022, 12, 2)
    assert last == date(2023, 1, 31)
    assert len(sessions[:20]) == 20
    assert all(s.start.date() < date(2023, 1, 1) for s in sessions[:20])
    assert sessions[20].start.date() == date(2023, 1, 3)
    for month, expected in ((10, 15990), (11, 15810)):
        _, original, _, _ = build_grid("AAPL", month)
        assert original[20].start.month == month
        assert sum((s.end-s.start)//timedelta(minutes=1) for s in original) == expected


def test_july_early_close_preserved():
    pytest.importorskip("exchange_calendars")
    _, sessions, _, _ = build_grid("AAPL", 7, 2023)
    assert sessions[20].start.date() == date(2023, 7, 3)
    assert sessions[20].end-sessions[20].start == timedelta(minutes=210)
    assert not any(s.start.date() == date(2023, 7, 4) for s in sessions)
