"""E5.8 split-only replay: causal gating, cost basis, PIT proof, false-positive guards."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest

from invest_engine.core.codec import decode_event
from invest_engine.core.replay import canonical_bytes
from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import Money
from invest_engine.research.backtest import HistoricalBacktest
from invest_engine.research.corporate_replay import SplitSchedule
from invest_engine.research.experiment import run_experiment
from invest_engine.research.pit import load_pit_evidence, validate_pit_events
from invest_engine.research.protection import ProtectionPolicy
from invest_engine.strategies.contracts import DataRequirement
from invest_engine.strategies.baselines import NoTradeStrategy
from invest_engine.trading.actions import SplitApplied
from invest_engine.trading.models import TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.policy import RiskLimits
from test_backtest_e5 import INST, STEP, T, SignalOnFirstBar
from test_experiment_e5 import START, make_spec


NEXT = T + timedelta(days=1)


def market_events() -> tuple[EventEnvelope, ...]:
    # BUY first day, execute next minute, hold over a 2:1 overnight split.
    records = (
        (T, "100", "100", "100", "100"),
        (T + STEP, "100", "105", "95", "100"),
        (T + 2*STEP, "100", "102", "99", "100"),
        (NEXT, "50", "52", "48", "50"),
    )
    events = []
    for n, (start, op, hi, lo, close) in enumerate(records):
        end = start + STEP
        bar = Bar(start, end, D(op), D(hi), D(lo), D(close), D("100000"), interval=STEP)
        events.append(EventEnvelope(f"split-bar:{n}", "market.bar", "synthetic", INST,
                                    end, end, end, n, bar))
    return tuple(events)


def split(*, at=NEXT, known=None, ratio=2) -> SplitApplied:
    return SplitApplied("split:one", INST, ratio, 1, at,
                        known if known is not None else at - timedelta(days=1), "issuer-fixture")


def runner(*, splits=(), strategy=None, protection=None):
    config = TradingConfig("sim", (MonetaryRules("KRW", D("1")),),
                           ((INST.key, InstrumentRules(D("1"), D("1"))),),
                           fee_rate=D("0.001"))
    risk = RiskLimits(per_trade_planned_loss=D("0.5"),
                      max_symbol_cost_fraction=D("0.2"), max_total_cost_fraction=D("0.5"))
    return HistoricalBacktest(
        calendar=StaticSessionCalendar((
            TradingSession(INST.market, INST.venue, T, T+timedelta(minutes=3)),
            TradingSession(INST.market, INST.venue, NEXT, NEXT+timedelta(minutes=1)),
        )),
        strategies=(strategy if strategy else SignalOnFirstBar(),),
        config=config, opening_cash=(Money(D("100000"), "KRW"),),
        risk=risk, split_schedule=SplitSchedule(tuple(splits)),
        protection_policy=protection,
    )


def test_split_replay_cost_and_virtual_attribution_stay_equal():
    report = runner(splits=(split(),)).run(market_events())
    assert report.entry_fill_count == 1
    assert report.exit_fill_count == 0
    assert report.equity[-2].complete and report.equity[-1].complete
    # Synthetic raw prices halve while inventory doubles; no phantom split loss.
    assert report.equity[-2].by_currency == report.equity[-1].by_currency
    assert "SPLIT_APPLIED:split:one" in report.decisions[-1].reason_codes
    assert report.run_sha256 == runner(splits=(split(),)).run(market_events()).run_sha256
    assert report.run_sha256 != runner(splits=()).run(market_events()).run_sha256


def test_split_action_replay_requires_session_open_and_known_terms():
    with pytest.raises(ValueError, match="SPLIT_MUST_START"):
        runner(splits=(split(at=NEXT+timedelta(seconds=30)),)).run(market_events())
    with pytest.raises(ValueError, match="SPLIT_TERMS_UNAVAILABLE"):
        runner(splits=(split(known=NEXT+timedelta(minutes=1)),)).run(market_events())
    with pytest.raises(InvalidEvent, match="SPLIT_REQUIRES_SESSION_OPEN"):
        runner(splits=(split(at=T+STEP, known=T-timedelta(days=1)),)).run(market_events())
    with pytest.raises(ValueError, match="PROTECTIVE_LOTS"):
        runner(splits=(split(),), protection=ProtectionPolicy(enabled=True))


def test_schedule_ids_and_unverified_virtual_split_rejected():
    with pytest.raises(ValueError, match="duplicated"):
        SplitSchedule((split(), split()))
    with pytest.raises(ValueError, match="ordered"):
        SplitSchedule((split(at=NEXT), replace(split(at=T), action_id="split:earlier")))


def prepare_cli_split(tmp_path: Path) -> Path:
    NEXT_CLI = START + timedelta(days=1)
    path = make_spec(tmp_path)
    raw_config = json.loads(path.read_text(encoding="utf-8"))
    entries = tuple(
        decode_event(line) for line in (tmp_path / "bars.jsonl").read_bytes().splitlines()
    )
    # Move the last observation into the next day's first minute, preserving a contiguous stream.
    last = entries[-1]
    corrected_bar = Bar(NEXT_CLI, NEXT_CLI+STEP, D("50"), D("52"), D("48"), D("50"),
                        D("1000"), interval=STEP)
    moved = EventEnvelope(last.event_id, "market.bar", "synthetic", last.instrument_id,
                          NEXT_CLI + STEP, NEXT_CLI + STEP, NEXT_CLI + STEP,
                          last.ingest_ordinal, corrected_bar)
    entries = (*entries[:-1], moved)
    dataset = tmp_path/"bars.jsonl"
    dataset.write_bytes(b"".join(canonical_bytes(e)+b"\n" for e in entries))
    raw_config["dataset"]["sha256"] = hashlib.sha256(dataset.read_bytes()).hexdigest()
    raw_config["sessions"] = [
        {"market":"KR","venue":"KRX","start":START.isoformat(),
         "end":(START+timedelta(minutes=2)).isoformat()},
        {"market":"KR","venue":"KRX","start":NEXT_CLI.isoformat(),
         "end":(NEXT_CLI+STEP).isoformat()},
    ]
    past = START-timedelta(days=2)
    records: list[dict[str, object]] = [
        {"kind":"membership", "instrument_key":last.instrument_id.key,
         "effective_from":past.isoformat(),
         "effective_until":(NEXT_CLI+timedelta(days=1)).isoformat(),
         "published_at":past.isoformat(), "received_at":past.isoformat(),
         "source":"synthetic-universe", "included":True},
        {"kind":"action_coverage","instrument_key":last.instrument_id.key,
         "start":past.isoformat(),"end":(NEXT_CLI+timedelta(days=1)).isoformat(),
         "published_at":past.isoformat(),"received_at":past.isoformat(),
         "source":"synthetic-catalog"},
    ]
    for e in entries:
        records.append({"kind":"vintage","event_id":e.event_id,
                        "payload_sha256":hashlib.sha256(canonical_bytes(e)).hexdigest(),
                        "revision":"original","published_at":e.available_at.isoformat(),
                        "received_at":e.received_at.isoformat(),"source":"synthetic-bar-feed"})
    records.append({"kind":"corporate_action","action_id":"split:one",
                    "instrument_key":last.instrument_id.key,"action_type":"SPLIT",
                    "effective_at":NEXT_CLI.isoformat(),"published_at":past.isoformat(),
                    "received_at":past.isoformat(),"source":"issuer-fixture"})
    pit_path = tmp_path/"pit.jsonl"
    pit_path.write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in records))
    raw_config["pit_evidence"] = {"records_jsonl":"pit.jsonl",
                                  "sha256":hashlib.sha256(pit_path.read_bytes()).hexdigest(),
                                  "source":"fixture","license":"synthetic-test"}
    split_record = {"kind":"split","action_id":"split:one","instrument_key":last.instrument_id.key,
                    "numerator":2,"denominator":1,"effective_at":NEXT_CLI.isoformat(),
                    "available_at":past.isoformat(),"source":"issuer-fixture"}
    spath=tmp_path/"splits.jsonl"
    spath.write_text(json.dumps(split_record,sort_keys=True)+"\n")
    raw_config["split_replay"] = {"records_jsonl":"splits.jsonl",
                                  "sha256":hashlib.sha256(spath.read_bytes()).hexdigest(),
                                  "source":"fixture","license":"synthetic-test",
                                  "price_basis":"RAW_UNADJUSTED"}
    path.write_text(json.dumps(raw_config))
    return path


def test_cli_split_pit_gate_reproducible(tmp_path: Path):
    path=prepare_cli_split(tmp_path)
    first=run_experiment(path)
    second=run_experiment(path)
    assert first.manifest_sha256 == second.manifest_sha256
    out=json.loads((tmp_path/"report-out"/"manifest.json").read_text())
    assert out["split_replay_count"] == 1
    assert out["split_replay_data_verified"] is False
    assert "SPLIT_APPLIED:split:one" in first.report.decisions[-1].reason_codes
    assert first.report.net_pnl == (("KRW", D("0")),)


def test_cli_rejects_unmodeled_or_tampered_splits(tmp_path: Path):
    path = prepare_cli_split(tmp_path)
    config = json.loads(path.read_text())
    del config["split_replay"]
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="UNMODELED_CORPORATE_ACTION"):
        run_experiment(path)
    config["split_replay"] = {"records_jsonl":"splits.jsonl",
                              "sha256":"0"*64,"source":"fixture",
                              "license":"synthetic-test","price_basis":"RAW_UNADJUSTED"}
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="hash mismatch"):
        run_experiment(path)


def test_cli_split_guards_and_unsupported_actions(tmp_path: Path):
    path = prepare_cli_split(tmp_path)
    config=json.loads(path.read_text())
    del config["pit_evidence"]
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="REQUIRES_PIT_EVIDENCE"):
        run_experiment(path)
    path=prepare_cli_split(tmp_path)
    config=json.loads(path.read_text())
    config["split_replay"]["price_basis"]="ADJUSTED"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="RAW_UNADJUSTED"):
        run_experiment(path)
    path=prepare_cli_split(tmp_path)
    records=[json.loads(line) for line in (tmp_path/"pit.jsonl").read_text().splitlines()]
    records[-1]["action_type"] = "CASH_DIVIDEND"
    pit_path=tmp_path/"pit.jsonl"
    pit_path.write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in records))
    config=json.loads(path.read_text())
    config["pit_evidence"]["sha256"]=hashlib.sha256(pit_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="UNMODELED_CORPORATE_ACTION"):
        run_experiment(path)
