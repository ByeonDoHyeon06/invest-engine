"""E5.9 synthetic cash dividend replay: PIT, funds, timing and compatibility."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import Money
from invest_engine.research.backtest import HistoricalBacktest
from invest_engine.research.dividend_replay import (
    DividendPayment, DividendSchedule, load_dividends,
)
from invest_engine.research.experiment import run_experiment
from invest_engine.trading.actions import DividendEntitled
from invest_engine.trading.models import TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.policy import RiskLimits
from test_backtest_e5 import INST, STEP, T, SignalOnFirstBar
from test_experiment_e5 import START
from test_split_replay_e5 import prepare_cli_split, split
from invest_engine.research.corporate_replay import SplitSchedule

EX = T + timedelta(days=1)
PAY = EX + timedelta(days=1)


def dividend(*, known=None, amount="2", action_id="cash:1") -> DividendEntitled:
    return DividendEntitled(action_id, INST, D(amount), D("0"), EX,
                            known if known is not None else EX - timedelta(days=1),
                            "issuer-fixture")


def payment(*, time=PAY, known=None, action_id="cash:1") -> DividendPayment:
    return DividendPayment(action_id, INST, time,
                           known if known is not None else EX, "issuer-fixture")


def events(*, include_payment=True):
    points = (
        (T, "100", "100", "100", "100"),
        (T+STEP, "100", "105", "95", "100"),
        (T+2*STEP, "100", "102", "99", "100"),
        (EX, "98", "100", "97", "98"),
    ) + (((PAY, "98", "100", "97", "98"),) if include_payment else ())
    result = []
    for ordinal, (start, op, hi, lo, close) in enumerate(points):
        end = start + STEP
        bar = Bar(start, end, D(op), D(hi), D(lo), D(close),
                  D("100000"), interval=STEP)
        result.append(EventEnvelope(f"dividend:{ordinal}", "market.bar", "synthetic",
                                    INST, end, end, end, ordinal, bar))
    return tuple(result)


def runner(*, schedule=None, trades=True, splits=()):
    from invest_engine.strategies.baselines import NoTradeStrategy
    from invest_engine.strategies.contracts import DataRequirement
    config = TradingConfig("sim", (MonetaryRules("KRW", D("1")),),
                           ((INST.key, InstrumentRules(D("1"), D("1"))),),
                           fee_rate=D("0.001"))
    strategy = (SignalOnFirstBar() if trades
                else NoTradeStrategy(DataRequirement("market.bar", STEP)))
    return HistoricalBacktest(
        calendar=StaticSessionCalendar((
            TradingSession(INST.market, INST.venue, T, T + 3*STEP),
            TradingSession(INST.market, INST.venue, EX, EX + STEP),
            TradingSession(INST.market, INST.venue, PAY, PAY + STEP),
        )),
        strategies=(strategy,), config=config,
        opening_cash=(Money(D("100000"), "KRW"),),
        risk=RiskLimits(per_trade_planned_loss=D("0.5"),
                        max_symbol_cost_fraction=D("0.2"),
                        max_total_cost_fraction=D("0.5")),
        dividend_schedule=schedule,
        split_schedule=SplitSchedule(tuple(splits)),
    )


def test_dividend_ex_price_drop_is_offset_by_receivable_then_paid_cash():
    schedule = DividendSchedule((dividend(),), (payment(),))
    report = runner(schedule=schedule).run(events())
    assert report.entry_fill_count == 1
    assert report.exit_fill_count == 0
    assert report.equity[-3].by_currency == (("KRW", D("99990")),)
    assert report.equity[-2].by_currency == (("KRW", D("99990")),)
    assert report.equity[-1].by_currency == (("KRW", D("99990")),)
    assert "DIVIDEND_ENTITLED:cash:1" in report.decisions[-2].reason_codes
    assert "DIVIDEND_PAID:cash:1" in report.decisions[-1].reason_codes
    assert report.run_sha256 == runner(schedule=schedule).run(events()).run_sha256
    assert report.run_sha256 != runner().run(events()).run_sha256


def test_dividend_after_test_horizon_stays_receivable_not_spendable():
    schedule = DividendSchedule((dividend(),), (payment(),))
    report = runner(schedule=schedule).run(events(include_payment=False))
    assert report.equity[-1].by_currency == (("KRW", D("99990")),)
    assert all("DIVIDEND_PAID" not in code
               for decision in report.decisions for code in decision.reason_codes)


def test_dividend_without_holdings_creates_no_cash():
    schedule = DividendSchedule((dividend(),), (payment(),))
    report = runner(schedule=schedule, trades=False).run(events())
    assert dict(report.by_currency_end) == {"KRW": D("100000")}
    assert "DIVIDEND_NO_HOLDINGS:cash:1" in report.decisions[-1].reason_codes


def test_schedule_rejects_bad_order_future_terms_and_dividend_collisions():
    with pytest.raises(ValueError, match="one distinct payment"):
        DividendSchedule((dividend(),), ())
    with pytest.raises(ValueError, match="DIVIDEND_TERMS_NOT_AVAILABLE"):
        DividendSchedule((dividend(known=EX + STEP),), (payment(),))
    with pytest.raises(ValueError, match="NOT_KNOWN"):
        payment(known=PAY + STEP)
    with pytest.raises(ValueError, match="payment must follow"):
        DividendSchedule((dividend(),), (payment(time=EX),))
    with pytest.raises(ValueError, match="SIMULTANEOUS_SPLIT_AND_DIVIDEND"):
        runner(schedule=DividendSchedule((dividend(),), (payment(),)),
               splits=(replace(split(), effective_at=EX),)).run(events())


def test_preflight_rejects_unwitnessed_ex_and_payment_bars():
    good = DividendSchedule((dividend(),), (payment(),))
    altered = replace(dividend(), effective_at=EX + timedelta(seconds=30))
    with pytest.raises(ValueError, match="ENTITLEMENT_REQUIRES_OBSERVED_BAR"):
        runner(schedule=DividendSchedule((altered,), (payment(),))).run(events())
    bad_payment = payment(time=EX + timedelta(seconds=30))
    with pytest.raises(ValueError, match="PAYMENT_REQUIRES_OBSERVED_BAR"):
        runner(schedule=DividendSchedule((dividend(),), (bad_payment,))).run(events())
    good.preflight(events())


def prepare_cli_dividend(tmp_path: Path) -> Path:
    path = prepare_cli_split(tmp_path)
    config = json.loads(path.read_text())
    del config["split_replay"]
    pit = tmp_path / "pit.jsonl"
    records = [json.loads(line) for line in pit.read_text().splitlines()]
    for record in records:
        if record["kind"] == "corporate_action":
            record["action_id"] = "dividend:fixture"
            record["action_type"] = "CASH_DIVIDEND"
    pit.write_text("".join(json.dumps(row, sort_keys=True)+"\n" for row in records))
    config["pit_evidence"]["sha256"] = hashlib.sha256(pit.read_bytes()).hexdigest()
    ex_at = START + timedelta(days=1)
    paid_at = ex_at + timedelta(days=1)
    schedule = [
        {"kind": "entitlement", "action_id": "dividend:fixture",
         "instrument_key": "KR:KRX:SYN-E5", "gross_per_share": "1.50",
         "withholding_fraction": "0.10", "effective_at": ex_at.isoformat(),
         "available_at": (START-timedelta(days=2)).isoformat(),
         "source": "issuer-fixture"},
        {"kind": "payment", "action_id": "dividend:fixture",
         "instrument_key": "KR:KRX:SYN-E5", "paid_at": paid_at.isoformat(),
         "available_at": ex_at.isoformat(), "source": "issuer-fixture"},
    ]
    data = tmp_path / "dividends.jsonl"
    data.write_text("".join(json.dumps(row, sort_keys=True)+"\n" for row in schedule))
    config["dividend_replay"] = {
        "records_jsonl": "dividends.jsonl",
        "sha256": hashlib.sha256(data.read_bytes()).hexdigest(),
        "source": "fixture", "license": "synthetic-only",
        "price_basis": "RAW_UNADJUSTED",
    }
    path.write_text(json.dumps(config))
    return path


def test_cli_pit_dividend_provenance_and_output_hash(tmp_path: Path):
    path = prepare_cli_dividend(tmp_path)
    a = run_experiment(path)
    b = run_experiment(path)
    assert a.manifest_sha256 == b.manifest_sha256
    manifest = json.loads((tmp_path/"report-out"/"manifest.json").read_text())
    assert manifest["dividend_replay_count"] == 1
    assert manifest["dividend_replay_data_verified"] is False
    assert "DIVIDEND_ENTITLED:dividend:fixture" in a.report.decisions[-1].reason_codes
    assert manifest["pit_data_release_verified"] is False


def test_cli_rejects_missing_pit_adjusted_price_or_tampered_data(tmp_path: Path):
    path = prepare_cli_dividend(tmp_path)
    config = json.loads(path.read_text())
    del config["pit_evidence"]
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="DIVIDEND_REPLAY_REQUIRES_PIT"):
        run_experiment(path)
    config = json.loads(path.read_text())
    config["pit_evidence"] = {"records_jsonl":"pit.jsonl",
                              "sha256":hashlib.sha256((tmp_path/"pit.jsonl").read_bytes()).hexdigest(),
                              "source":"fixture","license":"synthetic-test"}
    config["dividend_replay"]["price_basis"] = "SPLIT_ADJUSTED"
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="RAW_UNADJUSTED"):
        run_experiment(path)
    config["dividend_replay"]["price_basis"] = "RAW_UNADJUSTED"
    config["dividend_replay"]["sha256"] = "0"*64
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="hash mismatch"):
        run_experiment(path)


def test_pit_rejects_delist_even_when_dividend_modeled(tmp_path: Path):
    path = prepare_cli_dividend(tmp_path)
    config = json.loads(path.read_text())
    evidence_path = tmp_path/"pit.jsonl"
    records = [json.loads(l) for l in evidence_path.read_text().splitlines()]
    action = next(x for x in records if x["kind"] == "corporate_action")
    action["action_type"] = "DELIST"
    evidence_path.write_text("".join(json.dumps(row, sort_keys=True)+"\n" for row in records))
    config["pit_evidence"]["sha256"] = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="UNMODELED_CORPORATE_ACTION"):
        run_experiment(path)


def test_loader_strictly_checks_decimal_and_pinned_sha(tmp_path: Path):
    path = prepare_cli_dividend(tmp_path)
    config = json.loads(path.read_text())
    file = tmp_path/"dividends.jsonl"
    from test_experiment_e5 import INST as EX_INST
    schedule = load_dividends(file, config["dividend_replay"]["sha256"],
                              {EX_INST.key: EX_INST})
    assert len(schedule.entitlements) == len(schedule.payments) == 1
    rows = [json.loads(line) for line in file.read_text().splitlines()]
    rows[0]["gross_per_share"] = 1.5
    file.write_text("".join(json.dumps(row, sort_keys=True)+"\n" for row in rows))
    with pytest.raises(ValueError, match="decimal strings"):
        load_dividends(file, hashlib.sha256(file.read_bytes()).hexdigest(),
                       {EX_INST.key: EX_INST})
