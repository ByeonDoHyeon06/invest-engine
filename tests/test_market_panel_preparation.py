"""Offline checks for the data preparation utility; no quotes fabricated."""
from datetime import date
from decimal import InvalidOperation
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from prepare_market_panel import coverage, load_plan, normalize, parse_public, write_private


def test_frozen_universe_and_reserved_test():
    plan, h = load_plan()
    assert len(h) == 64
    assert sum(x["market"] == "US" for x in plan["instruments"]) == 40
    assert sum(x["market"] == "KR" for x in plan["instruments"]) == 40
    assert sum(x["public_probe"] for x in plan["instruments"]) == 16
    assert plan["periods"]["validation"][-1] < plan["periods"]["reserved_test"][0]


def test_no_missing_session_interpolation():
    rows = [normalize("2025-01-02", 10, 12, 9, 11, 100)]
    result = coverage(rows, {"2025-01-02", "2025-01-03"})
    assert result["status"] == "BLOCKED_COVERAGE"
    assert result["missing_dates"] == ["2025-01-03"]


def test_duplicate_extra_zero_and_bad_ohlc():
    a = normalize("2025-01-02", "10", "12", "9", "11", "0")
    result = coverage([a, a], {"2025-01-03"}, invalid=1)
    assert result["duplicates"] == result["extra_sessions"] == 1
    assert result["zero_volume_rows"] == 2
    assert result["status"] == "BLOCKED_COVERAGE"
    with pytest.raises(ValueError, match="INVALID_OHLC"):
        normalize("2025-01-02", 10, 8, 7, 11, 2)
    with pytest.raises((ValueError, InvalidOperation)):
        normalize("2025-01-02", "NaN", 12, 9, 11, 2)


def test_public_parser_does_not_include_future_rows():
    raw = b"date,open,high,low,close,volume\n2025-01-02,10,12,9,11,200\n2026-01-02,10,12,9,11,200\n"
    rows, invalid = parse_public(raw, 2025)
    assert len(rows) == 1 and invalid == 1


def test_private_version_never_silently_changes(tmp_path):
    rows = [normalize(date(2025, 1, 2).isoformat(), 10, 12, 9, 11, 100)]
    h = write_private(tmp_path, "US", "TEST", 2025, rows)
    assert h == write_private(tmp_path, "US", "TEST", 2025, rows)
    with pytest.raises(ValueError, match="NEW_VERSION"):
        write_private(tmp_path, "US", "TEST", 2025, [])
