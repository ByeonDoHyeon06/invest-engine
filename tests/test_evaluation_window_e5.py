"""Strict E5.12 warm-up and evaluation boundary regression tests."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
import hashlib
import json

import pytest

from invest_engine.core.replay import canonical_bytes
from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import Market, Money
from invest_engine.research.backtest import HistoricalBacktest
from invest_engine.research.evaluation import EvaluationWindow, validate_window
from invest_engine.research.experiment import run_experiment
from invest_engine.strategies.baselines import BuyHoldBaseline, NoTradeStrategy
from invest_engine.strategies.contracts import DataRequirement
from invest_engine.trading.models import TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.policy import RiskLimits
from test_experiment_e5 import INST, START, make_spec

MINUTE = timedelta(minutes=1)


def fixture():
    sessions = tuple(TradingSession(Market.KR, "KRX", START+timedelta(days=i),
                                    START+timedelta(days=i, minutes=3)) for i in range(21))
    events = []
    for session in sessions:
        for j in range(3):
            start = session.start + MINUTE*j
            end = start + MINUTE
            bar = Bar(start, end, D("100"), D("104"), D("96"), D("100"), D("4000"),
                      interval=MINUTE)
            n = len(events)
            events.append(EventEnvelope(f"w{n}", "market.bar", "synthetic", INST,
                                        end, end, end, n, bar))
    calendar = StaticSessionCalendar(sessions)
    window = EvaluationWindow(sessions[-1].start, sessions[-1].end)
    return tuple(events), calendar, window


def runner(calendar, window, strategy):
    config = TradingConfig("sim", (MonetaryRules("KRW", D("1")),),
                           ((INST.key, InstrumentRules(D("1"), D("1"))),))
    return HistoricalBacktest(
        calendar=calendar, strategies=(strategy,), config=config,
        opening_cash=(Money(D("100000"), "KRW"),),
        risk=RiskLimits(per_trade_planned_loss=D("0.5"),
                        max_symbol_cost_fraction=D("0.2"), max_total_cost_fraction=D("0.5")),
        evaluation_window=window,
    )


def test_warmup_cannot_trade_or_set_buy_hold_state():
    events, calendar, window = fixture()
    strategy = BuyHoldBaseline(MINUTE, D("0.05"), D("0.1"))
    report = runner(calendar, window, strategy).run(events)
    assert report.event_count == 63
    assert len(report.equity) == 3
    assert all(row.reason_codes == ("WARMUP_ONLY",) and not row.intent_ids
               for row in report.decisions[:60])
    assert report.decisions[60].signal_ids
    assert report.fills and all(f.market_event_id in {"w61", "w62"} for f in report.fills)
    assert report.equity[0].at == events[60].received_at
    assert report.run_sha256 == runner(
        calendar, window, BuyHoldBaseline(MINUTE, D("0.05"), D("0.1"))).run(events).run_sha256


def test_preflight_requires_complete_sessions_and_fixed_boundary():
    events, calendar, window = fixture()
    assert validate_window(events, calendar, window).warmup_bars == 60
    with pytest.raises(ValueError, match="MISSING_OR_EXTRA_MINUTE"):
        validate_window(events[:4] + events[5:], calendar, window)
    with pytest.raises(ValueError, match="INVALID_OR_MISSING_MINUTE"):
        validate_window(events[:4] + (events[3],) + events[5:], calendar, window)
    with pytest.raises(ValueError, match="SESSION"):
        validate_window(events, calendar, replace(window, start=window.start + MINUTE))
    with pytest.raises(ValueError, match="20_WARMUP"):
        EvaluationWindow(window.start, window.end, 19)


def test_preflight_rejects_fractional_share_volume_and_late_bar():
    events, calendar, window = fixture()
    event = events[0]
    with pytest.raises(ValueError, match="INTEGRAL_SHARE_VOLUME"):
        validate_window((replace(event, payload=replace(event.payload, volume=D("1.5"))),)
                        + events[1:], calendar, window)
    with pytest.raises(ValueError, match="INVALID_OR_MISSING_MINUTE"):
        validate_window((replace(event, received_at=event.received_at+MINUTE),)
                        + events[1:], calendar, window)


def test_no_trade_equity_excludes_warmup():
    events, calendar, window = fixture()
    report = runner(calendar, window, NoTradeStrategy(
        DataRequirement("market.bar", MINUTE))).run(events)
    assert len(report.equity) == 3 and not report.fills
    assert dict(report.by_currency_end)["KRW"] == D("100000")


def test_cli_requires_pit_and_volume_declaration(tmp_path):
    path = make_spec(tmp_path)
    spec = json.loads(path.read_text())
    _, _, window = fixture()
    spec["evaluation_window"] = {
        "start": window.start.isoformat(), "end": window.end.isoformat(),
        "warmup_sessions": 20, "price_basis": "RAW_UNADJUSTED",
        "market_coverage": "CONSOLIDATED",
    }
    spec["dataset"]["volume_unit"] = "TICK_COUNT"
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="RAW_SHARE_VOLUME"):
        run_experiment(path)
    spec["dataset"]["volume_unit"] = "SHARES"
    path.write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="PIT_EVIDENCE"):
        run_experiment(path)


def test_cli_fixed_window_pins_coverage_and_uses_real_pipeline(tmp_path):
    path = make_spec(tmp_path)
    spec = json.loads(path.read_text())
    events, calendar, window = fixture()
    data = tmp_path / "bars.jsonl"
    data.write_bytes(b"".join(canonical_bytes(e)+b"\n" for e in events))
    spec["dataset"]["sha256"] = hashlib.sha256(data.read_bytes()).hexdigest()
    spec["dataset"]["volume_unit"] = "SHARES"
    spec["sessions"] = [{"market": s.market.value, "venue": s.venue,
                         "start": s.start.isoformat(), "end": s.end.isoformat()}
                        for s in calendar.sessions]
    early = (START-timedelta(days=1)).isoformat()
    late = (calendar.sessions[-1].end+timedelta(days=1)).isoformat()
    rows = [
        {"kind": "membership", "instrument_key": INST.key,
         "effective_from": early, "effective_until": late,
         "published_at": early, "received_at": early, "source": "fixture", "included": True},
        {"kind": "action_coverage", "instrument_key": INST.key,
         "start": early, "end": late, "published_at": early,
         "received_at": early, "source": "fixture"},
    ]
    rows.extend({"kind": "vintage", "event_id": e.event_id,
                 "payload_sha256": hashlib.sha256(canonical_bytes(e)).hexdigest(),
                 "revision": "v1", "published_at": e.available_at.isoformat(),
                 "received_at": e.received_at.isoformat(), "source": "fixture"}
                for e in events)
    evidence = tmp_path/"pit.jsonl"
    evidence.write_text("".join(json.dumps(row)+"\n" for row in rows))
    spec["pit_evidence"] = {"records_jsonl": "pit.jsonl",
                            "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
                            "source": "fixture", "license": "synthetic"}
    spec["evaluation_window"] = {"start": window.start.isoformat(),
                                 "end": window.end.isoformat(), "warmup_sessions": 20,
                                 "price_basis": "RAW_UNADJUSTED",
                                 "market_coverage": "SINGLE_VENUE"}
    path.write_text(json.dumps(spec))
    report = run_experiment(path)
    manifest = json.loads((report.output_dir/"manifest.json").read_text())
    assert manifest["evaluation_coverage"] == {
        "warmup_bars": 60, "evaluation_bars": 3,
        "warmup_sessions": 20, "evaluation_sessions": 1}
    assert manifest["evaluation_provider_verified"] is False
    assert manifest["evaluation_window"]["market_coverage"] == "SINGLE_VENUE"
    assert len(report.report.equity) == 3 and not report.report.fills
    assert run_experiment(path).manifest_sha256 == report.manifest_sha256
