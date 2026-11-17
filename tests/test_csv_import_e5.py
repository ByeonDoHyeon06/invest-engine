"""Synthetic CSV-format import safety and no-trade offline replay smoke tests."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest

from invest_engine.core.codec import decode_event
from invest_engine.domain.errors import InvalidEvent
from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.events import Bar
from invest_engine.domain.primitives import InstrumentId, Market, Money
from invest_engine.research.backtest import HistoricalBacktest
from invest_engine.research.csv_import import import_ohlcv_csv, write_csv_import_manifest
from invest_engine.strategies.baselines import NoTradeStrategy
from invest_engine.strategies.contracts import DataRequirement
from invest_engine.trading.models import TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules

AAPL = InstrumentId(Market.US, "XNAS", "US0378331005", "AAPL", "USD")
STEP = timedelta(minutes=1)
SAMPLE = ("datetime,open,high,low,close,volume\n"
          "2026-03-26T13:30:00+00:00,102.35,102.35,100.14,101.12,106\n"
          "2026-03-26T13:31:00+00:00,101.12,101.14,100.65,100.72,154\n"
          "2026-03-26T13:32:00+00:00,100.72,101.22,100.65,101.06,190\n"
          "2026-03-26T13:33:00+00:00,101.06,101.31,100.9,100.95,129\n"
          "2026-03-26T13:34:00+00:00,100.95,101.42,100.93,101.39,217\n")


def read(tmp_path: Path, content: str = SAMPLE, unit: str = "TICK_COUNT"):
    source = tmp_path / "source.csv"
    target = tmp_path / "events.jsonl"
    source.write_text(content, encoding="utf-8")
    return import_ohlcv_csv(source, target, instrument=AAPL, source="test-public-preview",
                            interval=STEP, volume_unit=unit), target


def test_csv_roundtrip_and_no_trade_replay(tmp_path: Path):
    meta, target = read(tmp_path)
    assert meta.event_count == 5
    assert not meta.execution_eligible
    import hashlib
    assert hashlib.sha256(target.read_bytes()).hexdigest() == meta.output_sha256
    write_csv_import_manifest(tmp_path / "meta.json", meta, "synthetic")
    assert '"availability_timestamps_are_assumptions":true' in (tmp_path / "meta.json").read_text()
    events = tuple(decode_event(line) for line in target.read_bytes().splitlines())
    assert len(events) == 5
    first = events[0]
    assert isinstance(first.payload, Bar)
    assert first.payload.close == D("101.12")
    assert first.available_at > first.payload.end
    calendar = StaticSessionCalendar((TradingSession(Market.US, "XNAS",
        first.payload.start, first.payload.start + timedelta(hours=6, minutes=30)),))
    config = TradingConfig("sample", (MonetaryRules("USD", D("0.01")),),
                           ((AAPL.key, InstrumentRules(D("0.01"), D("1"))),))
    report = HistoricalBacktest(calendar=calendar,
        strategies=(NoTradeStrategy(DataRequirement("market.bar", STEP)),),
        config=config, opening_cash=(Money(D("10000"), "USD"),)).run(events)
    assert report.event_count == 5
    assert report.entry_fill_count == report.exit_fill_count == 0
    assert dict(report.net_pnl) == {"USD": D("0")}


@pytest.mark.parametrize("bad", [
    "date,open,high,low,close,volume\n",  # wrong schema
    SAMPLE.replace("+00:00", "", 1),  # ambiguous clock
    SAMPLE.replace("100.72,101.22", "100.72,NaN"),
    SAMPLE.replace("101.12,101.14", "-101.12,101.14"),
    SAMPLE.replace("13:31:00", "13:30:00"),
])
def test_invalid_rows_rejected(tmp_path: Path, bad: str):
    with pytest.raises((ValueError, InvalidEvent)):
        read(tmp_path, bad)


def test_converter_does_not_override_raw_csv_and_volume_attestation(tmp_path: Path):
    meta, _ = read(tmp_path, unit="SHARES")
    assert meta.execution_eligible
    source = tmp_path / "source.csv"
    with pytest.raises(ValueError, match="overwrite"):
        import_ohlcv_csv(source, source, instrument=AAPL, source="src",
                         interval=STEP, volume_unit="SHARES")
    with pytest.raises(ValueError, match="volume_unit"):
        read(tmp_path, unit="UNKNOWN")


def test_volume_unit_blocks_orb_cli_without_shares(tmp_path: Path):
    import json
    from test_experiment_e5 import make_spec
    from invest_engine.research.experiment import run_experiment

    cfg = make_spec(tmp_path)
    raw = json.loads(cfg.read_text())
    raw["dataset"]["volume_unit"] = "TICK_COUNT"
    raw["strategy"]["id"] = "orb-long"
    cfg.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="not traded shares"):
        run_experiment(cfg)
    raw["strategy"]["id"] = "no-trade"
    cfg.write_text(json.dumps(raw))
    result = run_experiment(cfg)
    manifest = json.loads((tmp_path / "report-out" / "manifest.json").read_text())
    assert manifest["dataset_volume_unit"] == "TICK_COUNT"
    assert "VOLUME_IS_TICK_COUNT_NOT_TRADED_SHARES" in manifest["warnings"]
    assert result.report.entry_fill_count == 0
