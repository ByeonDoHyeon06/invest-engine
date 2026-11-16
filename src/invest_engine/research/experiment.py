"""Strict offline-only E5 RunRequest adapter for canonical historical JSONL events.

No provider authentication, network client, or broker interface is available.
The run manifest is a research artifact, NOT a certificate of profitability.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from invest_engine.core.codec import decode_event
from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.primitives import AssetClass, InstrumentId, Market, Money
from invest_engine.research.backtest import BacktestSettings, HistoricalBacktest
from invest_engine.research.fills import BarFillPolicy
from invest_engine.research.report import BacktestReport, canonical_json, sha256
from invest_engine.strategies.baselines import NoTradeStrategy
from invest_engine.strategies.contracts import DataRequirement, Strategy
from invest_engine.strategies.orb import ORBLongStrategy, ORBParameters
from invest_engine.trading.models import TradingConfig
from invest_engine.trading.money import InstrumentRules, MonetaryRules
from invest_engine.trading.policy import RiskLimits


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    report: BacktestReport
    run_id: str
    output_dir: Path
    manifest_sha256: str


def _object(value: object, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"unexpected or missing config fields: {keys ^ set(value) if isinstance(value, dict) else keys}")
    return cast(dict[str, Any], value)


def _decimal(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("decimal input must be a string")
    number = Decimal(value)
    if not number.is_finite():
        raise ValueError("decimal input must be finite")
    return number


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not (value.endswith("Z") or value.endswith("+00:00")):
        raise ValueError("datetime must be an explicit UTC RFC3339 string")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _interval(value: object) -> timedelta:
    if not isinstance(value, str):
        raise ValueError("interval must be an ISO 8601 minute duration")
    match = re.fullmatch(r"PT([1-9][0-9]*)M", value)
    if match is None:
        raise ValueError("only positive whole-minute intervals supported by this CLI")
    return timedelta(minutes=int(match.group(1)))


def run_experiment(config_file: Path | str) -> ExperimentResult:
    path = Path(config_file)
    root = path.parent.resolve()
    raw = _object(json.loads(path.read_text(encoding="utf-8")), {
        "schema_version", "run_id", "mode", "dataset", "sessions", "strategy",
        "account", "risk", "fill_model", "code_sha", "output_dir",
    })
    if raw["schema_version"] != "e5-research-v1" or raw["mode"] != "BACKTEST":
        raise ValueError("only offline BACKTEST e5-research-v1 is permitted")
    if not isinstance(raw["run_id"], str) or not raw["run_id"].strip():
        raise ValueError("nonempty run id required")
    if not isinstance(raw["code_sha"], str) or not raw["code_sha"].strip():
        raise ValueError("code revision required")
    dataset = _object(raw["dataset"], {"events_jsonl", "source", "license", "sha256"})
    if not all(isinstance(dataset[k], str) and dataset[k].strip() for k in dataset):
        raise ValueError("historical data origin/license/checksum required")
    source_file = (root / dataset["events_jsonl"]).resolve()
    if not source_file.is_file():
        raise ValueError("dataset file does not exist")
    # Hash exact source bytes before parsing. Canonical market codec rejects tampered event JSON.
    import hashlib
    file_hash = hashlib.sha256(source_file.read_bytes()).hexdigest()
    if file_hash != dataset["sha256"]:
        raise ValueError("dataset file hash differs from pinned manifest")
    lines = [line for line in source_file.read_bytes().splitlines() if line]
    if not lines or any(len(line) > 5_000_000 for line in lines):
        raise ValueError("missing or excessively large market-event records")
    events = tuple(decode_event(line) for line in lines)
    sessions: list[TradingSession] = []
    if not isinstance(raw["sessions"], list) or not raw["sessions"]:
        raise ValueError("authoritative historical sessions required")
    for row in raw["sessions"]:
        s = _object(row, {"market", "venue", "start", "end"})
        sessions.append(TradingSession(Market(s["market"]), s["venue"],
                                       _utc(s["start"]), _utc(s["end"])))
    calendar = StaticSessionCalendar(tuple(sessions))
    st = _object(raw["strategy"], {"id", "version", "parameters"})
    params = _object(st["parameters"], {"interval"}) if st["id"] == "no-trade" else None
    strategy: Strategy
    if st["id"] == "no-trade" and st["version"] == "1.0.0":
        assert params is not None
        strategy = NoTradeStrategy(DataRequirement("market.bar", _interval(params["interval"])))
    elif st["id"] == "orb-long" and st["version"] == "1.0.0":
        p = _object(st["parameters"], {"interval", "opening_kr", "opening_us", "prior_sessions",
                                        "volume_multiplier", "target_fraction", "atr_period"})
        strategy = ORBLongStrategy(ORBParameters(
            timeframe=_interval(p["interval"]), opening_kr=_interval(p["opening_kr"]),
            opening_us=_interval(p["opening_us"]), prior_sessions=int(p["prior_sessions"]),
            volume_multiplier=_decimal(p["volume_multiplier"]),
            target_fraction=_decimal(p["target_fraction"]), atr_period=int(p["atr_period"]),
        ))
    else:
        raise ValueError("strategy is not an approved, versioned research plugin")
    account = _object(raw["account"], {"account_id", "cash", "cash_rules", "instruments", "fee_rate", "sell_tax_rate"})
    cash = tuple(Money(_decimal(x["amount"]), x["currency"]) for x in account["cash"])
    cash_rules = tuple(MonetaryRules(x["currency"], _decimal(x["cash_step"]))
                       for x in account["cash_rules"])
    rules: list[tuple[str, InstrumentRules]] = []
    for row in account["instruments"]:
        i = _object(row, {"market", "venue", "identifier", "symbol", "currency", "asset_class", "tick", "lot"})
        inst = InstrumentId(Market(i["market"]), i["venue"], i["identifier"], i["symbol"],
                            i["currency"], AssetClass(i["asset_class"]))
        rules.append((inst.key, InstrumentRules(_decimal(i["tick"]), _decimal(i["lot"]))))
    trading = TradingConfig(account["account_id"], cash_rules, tuple(rules),
                            fee_rate=_decimal(account["fee_rate"]),
                            sell_tax_rate=_decimal(account["sell_tax_rate"]))
    risk = _object(raw["risk"], {"per_trade_planned_loss", "max_symbol_cost_fraction",
                                 "max_total_cost_fraction", "max_open_positions"})
    limits = RiskLimits(per_trade_planned_loss=_decimal(risk["per_trade_planned_loss"]),
                        max_symbol_cost_fraction=_decimal(risk["max_symbol_cost_fraction"]),
                        max_total_cost_fraction=_decimal(risk["max_total_cost_fraction"]),
                        max_open_positions=int(risk["max_open_positions"]))
    fill = _object(raw["fill_model"], {"version", "participation", "spread_bps", "impact_bps"})
    policy = BarFillPolicy(_decimal(fill["participation"]), _decimal(fill["spread_bps"]),
                           _decimal(fill["impact_bps"]), version=fill["version"])
    settings = BacktestSettings(code_sha=raw["code_sha"], dataset_source=dataset["source"],
                                data_license=dataset["license"])
    runner = HistoricalBacktest(calendar=calendar, strategies=(strategy,), config=trading,
                                opening_cash=cash, risk=limits, fill_policy=policy,
                                settings=settings)
    report = runner.run(events)
    output_dir = (root / raw["output_dir"]).resolve()
    if output_dir in (root, source_file):
        raise ValueError("report output must not overwrite experiment config/dataset")
    report.export(output_dir)
    manifest = {
        "schema_version": "e5-research-v1", "run_id": raw["run_id"],
        "code_sha": raw["code_sha"], "dataset_file_sha256": file_hash,
        "dataset_event_sha256": report.dataset_sha256,
        "dataset_source": dataset["source"], "data_license": dataset["license"],
        "strategy_id": st["id"], "strategy_version": st["version"],
        "fill_model_version": policy.version, "config_sha256": report.config_sha256,
        "run_sha256": report.run_sha256,
        "warnings": list(report.notes),
    }
    manifest_sha = sha256(manifest)
    (output_dir / "manifest.json").write_bytes(canonical_json(manifest))
    return ExperimentResult(report, raw["run_id"], output_dir, manifest_sha)
