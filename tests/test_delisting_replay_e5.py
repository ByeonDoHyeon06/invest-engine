"""E5.10 terminal delisting: issuer evidence without optimistic liquidation."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest

from invest_engine.core.codec import decode_event
from invest_engine.domain.errors import InvalidEvent
from invest_engine.research.backtest import HistoricalBacktest
from invest_engine.research.delisting_replay import DelistingSchedule, load_delistings
from invest_engine.research.experiment import run_experiment
from invest_engine.strategies.baselines import NoTradeStrategy
from invest_engine.strategies.contracts import DataRequirement
from invest_engine.trading.actions import DelistingObserved
from test_backtest_e5 import INST, STEP, T, feed
from test_pit_e5 import _prepare, _persist


def delist(*, when=None, known=None, action_id="delist:1") -> DelistingObserved:
    at = when if when is not None else T + 3 * STEP
    return DelistingObserved(action_id, INST, at,
                             known if known is not None else T - timedelta(days=1),
                             "issuer-synthetic")


def runner(*, trade: bool = False, actions: tuple[DelistingObserved, ...] = ()) -> HistoricalBacktest:
    import test_backtest_e5
    from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
    from invest_engine.domain.primitives import Money
    from invest_engine.trading.models import TradingConfig
    from invest_engine.trading.money import InstrumentRules, MonetaryRules
    from invest_engine.trading.policy import RiskLimits

    cfg = TradingConfig("sim", (MonetaryRules("KRW", D("1")),),
                        ((INST.key, InstrumentRules(D("1"), D("1"))),), fee_rate=D("0.001"))
    strategy = (test_backtest_e5.SignalOnFirstBar() if trade else
                NoTradeStrategy(DataRequirement("market.bar", STEP)))
    return HistoricalBacktest(
        calendar=StaticSessionCalendar((TradingSession(INST.market, INST.venue, T,
                                                      T + timedelta(hours=1)),)),
        strategies=(strategy,), config=cfg, opening_cash=(Money(D("100000"), "KRW"),),
        risk=RiskLimits(per_trade_planned_loss=D("0.5"),
                        max_symbol_cost_fraction=D("0.2"),
                        max_total_cost_fraction=D("0.5")),
        delisting_schedule=DelistingSchedule(actions),
    )


def test_unheld_delisting_marks_no_trade_without_inventing_proceeds():
    events = feed()[:3]
    action = delist()
    report = runner(actions=(action,)).run(events)
    assert report.entry_fill_count == 0 and report.exit_fill_count == 0
    assert dict(report.by_currency_end) == {"KRW": D("100000")}
    assert "DELISTING_BLOCKED:delist:1" in report.decisions[-1].reason_codes
    assert report.run_sha256 == runner(actions=(action,)).run(events).run_sha256
    assert report.run_sha256 != runner().run(events).run_sha256


def test_delisted_holdings_require_explicit_terminal_settlement():
    with pytest.raises(InvalidEvent, match="DELISTED_HOLDINGS_REQUIRE_VERIFIED_TERMINAL_SETTLEMENT"):
        runner(actions=(delist(),), trade=True).run(feed()[:3])


def test_delisting_with_unresolved_open_order_fails_closed():
    prices = (("100", "100", "100", "100", "1000"),
              ("100", "100", "100", "100", "1000"))
    with pytest.raises(InvalidEvent, match="DELISTING_WITH_UNRESOLVED_ORDERS"):
        runner(actions=(delist(when=T+2*STEP),), trade=True).run(feed(prices=prices))


def test_preflight_requires_terminal_witness_and_forbids_future_market_data():
    with pytest.raises(ValueError, match="LAST_CONFIRMED_BAR"):
        runner(actions=(delist(when=T+timedelta(seconds=30)),)).run(feed()[:3])
    with pytest.raises(ValueError, match="MARKET_EVENTS_AFTER_DELISTING"):
        runner(actions=(delist(),)).run(feed()[:4])
    with pytest.raises(ValueError, match="NOT_AVAILABLE"):
        DelistingSchedule((delist(known=T+timedelta(minutes=4)),))
    with pytest.raises(ValueError, match="DUPLICATE"):
        DelistingSchedule((delist(), replace(delist(), action_id="delist:2")))


def _cli_delisting(tmp_path: Path) -> Path:
    path, records = _prepare(tmp_path)
    events = tuple(decode_event(line) for line in (tmp_path/"bars.jsonl").read_bytes().splitlines())
    last = events[-1]
    effective = last.payload.end
    known = effective - timedelta(days=1)
    records.append({
        "kind":"corporate_action", "action_id":"delist:cli",
        "instrument_key":last.instrument_id.key, "action_type":"DELIST",
        "effective_at":effective.isoformat(), "published_at":known.isoformat(),
        "received_at":known.isoformat(), "source":"issuer-synthetic",
    })
    _persist(tmp_path, path, records)
    payload = {
        "kind":"delisting", "action_id":"delist:cli",
        "instrument_key":last.instrument_id.key,
        "effective_at":effective.isoformat(), "available_at":known.isoformat(),
        "source":"issuer-synthetic",
    }
    delists = tmp_path/"delistings.jsonl"
    delists.write_text(json.dumps(payload, sort_keys=True)+"\n", encoding="utf-8")
    spec = json.loads(path.read_text(encoding="utf-8"))
    spec["delisting_replay"] = {
        "records_jsonl":"delistings.jsonl",
        "sha256":hashlib.sha256(delists.read_bytes()).hexdigest(),
        "source":"issuer-synthetic", "license":"fixture-only",
    }
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def test_cli_pit_delisting_verified_structure_and_manifest_hash(tmp_path: Path):
    path = _cli_delisting(tmp_path)
    first = run_experiment(path)
    second = run_experiment(path)
    assert first.manifest_sha256 == second.manifest_sha256
    assert first.report.entry_fill_count == 0
    assert "DELISTING_BLOCKED:delist:cli" in first.report.decisions[-1].reason_codes
    result = json.loads((tmp_path/"report-out"/"manifest.json").read_text())
    assert result["delisting_schedule_sha256"]
    assert result["research_data_release_verified"] is False


def test_cli_unmodeled_delisting_still_rejected(tmp_path: Path):
    path = _cli_delisting(tmp_path)
    spec = json.loads(path.read_text())
    del spec["delisting_replay"]
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="UNMODELED_CORPORATE_ACTION"):
        run_experiment(path)


def test_cli_requires_pit_and_immutable_delisting_file(tmp_path: Path):
    path = _cli_delisting(tmp_path)
    spec = json.loads(path.read_text())
    spec.pop("pit_evidence")
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="DELISTING_REPLAY_REQUIRES_PIT_EVIDENCE"):
        run_experiment(path)
    path = _cli_delisting(tmp_path)
    (tmp_path/"delistings.jsonl").write_text("{}\n")
    with pytest.raises(ValueError, match="DELISTING_FILE_HASH_MISMATCH"):
        run_experiment(path)


def test_cli_mismatched_issuer_action_and_malformed_schedule(tmp_path: Path):
    path = _cli_delisting(tmp_path)
    records = [json.loads(line) for line in (tmp_path/"pit.jsonl").read_text().splitlines()]
    records[-1]["action_type"] = "MERGER"
    _persist(tmp_path, path, records)
    with pytest.raises(ValueError, match="UNMODELED_CORPORATE_ACTION"):
        run_experiment(path)
    # Purely syntactic schema rejection is independent of PIT truth.
    valid = json.loads((tmp_path/"delistings.jsonl").read_text())
    valid["unknown"] = "reject"
    file = tmp_path/"delistings.jsonl"
    file.write_text(json.dumps(valid)+"\n")
    with pytest.raises(ValueError, match="invalid delisting schedule schema"):
        load_delistings(file, hashlib.sha256(file.read_bytes()).hexdigest(),
                        {INST.key:INST})
