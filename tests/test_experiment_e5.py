from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path

import pytest

from invest_engine.cli import main
from invest_engine.core.replay import canonical_bytes
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.research.experiment import run_experiment

START = datetime(2026, 11, 16, 0, 0, tzinfo=timezone.utc)
INST = InstrumentId(Market.KR, "KRX", "SYN-E5", "SYN", "KRW")


def make_spec(tmp_path: Path) -> Path:
    events = []
    for n in range(3):
        start = START + timedelta(minutes=n)
        end = start + timedelta(minutes=1)
        bar = Bar(start, end, D("100"), D("103"), D("97"), D("100"), D("1000"),
                  interval=timedelta(minutes=1))
        events.append(EventEnvelope(f"e{n}", "market.bar", "synthetic", INST,
                                    end, end, end, n, bar))
    dataset = tmp_path / "bars.jsonl"
    dataset.write_bytes(b"".join(canonical_bytes(ev)+b"\n" for ev in events))
    spec = {
        "schema_version": "e5-research-v1", "run_id": "test-no-trade", "mode": "BACKTEST",
        "code_sha": "synthetic-test-commit",
        "dataset": {"events_jsonl": "bars.jsonl", "source": "synthetic-test",
                    "license": "synthetic", "sha256": hashlib.sha256(dataset.read_bytes()).hexdigest()},
        "sessions": [{"market": "KR", "venue": "KRX", "start": START.isoformat(),
                      "end": (START+timedelta(hours=1)).isoformat()}],
        "strategy": {"id": "no-trade", "version": "1.0.0", "parameters": {"interval": "PT1M"}},
        "account": {"account_id": "test", "cash": [{"currency": "KRW", "amount": "100000"}],
                    "cash_rules": [{"currency": "KRW", "cash_step": "1"}],
                    "instruments": [{"market": "KR", "venue": "KRX", "identifier": "SYN-E5",
                                     "symbol": "SYN", "currency": "KRW", "asset_class": "EQUITY",
                                     "tick": "1", "lot": "1"}],
                    "fee_rate": "0.001", "sell_tax_rate": "0"},
        "risk": {"per_trade_planned_loss": "0.1", "max_symbol_cost_fraction": "0.2",
                 "max_total_cost_fraction": "0.5", "max_open_positions": 3},
        "fill_model": {"version": "penetration-limit-v1", "participation": "0.05",
                       "spread_bps": "5", "impact_bps": "5"},
        "output_dir": "report-out",
    }
    config = tmp_path / "run.json"
    config.write_text(json.dumps(spec), encoding="utf-8")
    return config


def test_end_to_end_run_request_and_cli(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    path = make_spec(tmp_path)
    assert main(["backtest", "--config", str(path)]) == 0
    stdout = json.loads(capsys.readouterr().out)
    assert stdout["run_id"] == "test-no-trade"
    report = json.loads((tmp_path / "report-out" / "report.json").read_text())
    assert report["event_count"] == 3
    assert report["entry_fill_count"] == 0
    assert report["by_currency_end"] == [["KRW", "100000"]]
    assert (tmp_path / "report-out" / "manifest.json").is_file()
    assert len((tmp_path / "report-out" / "equity.jsonl").read_text().splitlines()) == 3
    a = run_experiment(path)
    b = run_experiment(path)
    assert a.manifest_sha256 == b.manifest_sha256 == stdout["manifest_sha256"]


def test_refuse_wrong_checksum_and_live_mode(tmp_path: Path):
    path = make_spec(tmp_path)
    record = json.loads(path.read_text())
    record["dataset"]["sha256"] = "f"*64
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="hash"):
        run_experiment(path)
    record["mode"] = "LIVE"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="only offline"):
        run_experiment(path)


def test_refuse_unknown_field_and_noncanonical_market_event(tmp_path: Path):
    path = make_spec(tmp_path)
    record = json.loads(path.read_text())
    record["broker_credentials"] = "not-a-real-token"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="unexpected"):
        run_experiment(path)
    del record["broker_credentials"]
    file = tmp_path / "bars.jsonl"
    file.write_bytes(file.read_bytes().replace(b'"event_id":', b'"event_id" :'))
    record["dataset"]["sha256"] = hashlib.sha256(file.read_bytes()).hexdigest()
    path.write_text(json.dumps(record))
    with pytest.raises(Exception, match="InvalidEvent|noncanonical|encoding"):
        run_experiment(path)


def test_unapproved_model_and_float_amount_rejected(tmp_path: Path):
    path = make_spec(tmp_path)
    record = json.loads(path.read_text())
    record["strategy"]["id"] = "external-llm"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="approved"):
        run_experiment(path)
    record["strategy"]["id"] = "no-trade"
    record["account"]["cash"][0]["amount"] = 100000.0
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="decimal"):
        run_experiment(path)
