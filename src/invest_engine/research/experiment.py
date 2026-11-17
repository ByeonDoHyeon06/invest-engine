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
from invest_engine.research.audit import (
    audit_hash, file_sha256, inspect_dataset, source_tree_sha256,
)
from invest_engine.research.corporate_replay import SplitSchedule, load_splits
from invest_engine.research.dividend_replay import DividendSchedule, load_dividends
from invest_engine.research.delisting_replay import DelistingSchedule, load_delistings
from invest_engine.research.fills import BarFillPolicy
from invest_engine.research.fx import FxObservation, FxReportingPolicy, FxSeries
from invest_engine.research.protection import ProtectionPolicy
from invest_engine.research.pit import load_pit_evidence, validate_pit_events
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
    raw_input = json.loads(path.read_text(encoding="utf-8"))
    required = {"schema_version", "run_id", "mode", "dataset", "sessions", "strategy",
                "account", "risk", "fill_model", "code_sha", "output_dir"}
    if (not isinstance(raw_input, dict) or not required <= set(raw_input)
        or not set(raw_input) <= required | {"fx_reporting", "pit_evidence", "split_replay",
                                                "dividend_replay", "delisting_replay"}):
        raise ValueError("unexpected or missing config fields")
    raw = cast(dict[str, Any], raw_input)
    if raw["schema_version"] != "e5-research-v1" or raw["mode"] != "BACKTEST":
        raise ValueError("only offline BACKTEST e5-research-v1 is permitted")
    if not isinstance(raw["run_id"], str) or not raw["run_id"].strip():
        raise ValueError("nonempty run id required")
    if not isinstance(raw["code_sha"], str) or not raw["code_sha"].strip():
        raise ValueError("code revision required")
    dataset_input = raw["dataset"]
    if not isinstance(dataset_input, dict):
        raise ValueError("dataset must be an object")
    declared = dataset_input.get("volume_unit")
    if declared is not None and declared not in ("SHARES", "TICK_COUNT"):
        raise ValueError("unsupported dataset volume unit")
    dataset = _object({k: v for k, v in dataset_input.items() if k != "volume_unit"},
                      {"events_jsonl", "source", "license", "sha256"})
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
    schedule = SplitSchedule()
    split_file_hash: str | None = None
    if "split_replay" in raw:
        if "pit_evidence" not in raw:
            raise ValueError("SPLIT_REPLAY_REQUIRES_PIT_EVIDENCE")
        spec_split = _object(raw["split_replay"], {
            "records_jsonl", "sha256", "source", "license", "price_basis",
        })
        if spec_split["price_basis"] != "RAW_UNADJUSTED":
            raise ValueError("SPLIT_REPLAY_REQUIRES_RAW_UNADJUSTED_BARS")
        if not all(isinstance(spec_split[k], str) and spec_split[k].strip()
                   for k in ("records_jsonl", "sha256", "source", "license")):
            raise ValueError("split schedule provenance fields required")
        known_instruments = {e.instrument_id.key: e.instrument_id
                             for e in events if e.instrument_id is not None}
        schedule = load_splits((root / spec_split["records_jsonl"]).resolve(),
                               spec_split["sha256"], known_instruments)
        schedule.preflight(events)
        split_file_hash = spec_split["sha256"]
    dividend_schedule = DividendSchedule()
    dividend_file_hash: str | None = None
    if "dividend_replay" in raw:
        if "pit_evidence" not in raw:
            raise ValueError("DIVIDEND_REPLAY_REQUIRES_PIT_EVIDENCE")
        spec_dividend = _object(raw["dividend_replay"], {
            "records_jsonl", "sha256", "source", "license", "price_basis",
        })
        if spec_dividend["price_basis"] != "RAW_UNADJUSTED":
            raise ValueError("DIVIDEND_REPLAY_REQUIRES_RAW_UNADJUSTED_BARS")
        if not all(isinstance(spec_dividend[k], str) and spec_dividend[k].strip()
                   for k in ("records_jsonl", "sha256", "source", "license")):
            raise ValueError("dividend schedule provenance fields required")
        known = {e.instrument_id.key: e.instrument_id
                 for e in events if e.instrument_id is not None}
        dividend_schedule = load_dividends((root / spec_dividend["records_jsonl"]).resolve(),
                                           spec_dividend["sha256"], known)
        dividend_schedule.preflight(events)
        dividend_file_hash = spec_dividend["sha256"]
    delisting_schedule = DelistingSchedule()
    delisting_file_hash: str | None = None
    if "delisting_replay" in raw:
        if "pit_evidence" not in raw:
            raise ValueError("DELISTING_REPLAY_REQUIRES_PIT_EVIDENCE")
        dl = _object(raw["delisting_replay"], {
            "records_jsonl", "sha256", "source", "license",
        })
        if not all(isinstance(dl[k], str) and dl[k].strip()
                   for k in ("records_jsonl", "sha256", "source", "license")):
            raise ValueError("delisting schedule origin and license required")
        instruments = {e.instrument_id.key: e.instrument_id
                       for e in events if e.instrument_id is not None}
        delisting_schedule = load_delistings(
            (root / dl["records_jsonl"]).resolve(), dl["sha256"], instruments,
        )
        delisting_schedule.preflight(events)
        delisting_file_hash = dl["sha256"]
    pit_result = None
    pit_file_hash: str | None = None
    pit_source: str | None = None
    pit_license: str | None = None
    if "pit_evidence" in raw:
        spec = _object(raw["pit_evidence"], {
            "records_jsonl", "sha256", "source", "license",
        })
        if not all(isinstance(spec[k], str) and spec[k].strip() for k in spec):
            raise ValueError("PIT evidence origin, license, and hash required")
        evidence_file = (root / spec["records_jsonl"]).resolve()
        evidence, pit_file_hash = load_pit_evidence(evidence_file, spec["sha256"])
        # Validate before starting a strategy or writing any result artifacts.
        # These are caller declarations; they do not authenticate the provider.
        pit_result = validate_pit_events(events, evidence, modeled_splits=schedule.splits,
                                         modeled_dividends=dividend_schedule.entitlements,
                                         modeled_delistings=delisting_schedule.delistings)
        pit_source, pit_license = spec["source"], spec["license"]
    st = _object(raw["strategy"], {"id", "version", "parameters"})
    if declared == "TICK_COUNT" and st["id"] != "no-trade":
        raise ValueError("TICK_COUNT volume is not traded shares; only no-trade smoke tests allowed")
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
    fill_required = {"version", "participation", "spread_bps", "impact_bps"}
    fields = raw["fill_model"]
    if not isinstance(fields, dict):
        raise ValueError("fill_model must be an object")
    if set(fields) not in (fill_required, fill_required | {"protective_exit"}):
        raise ValueError("unexpected or missing fill model fields")
    fill = cast(dict[str, Any], fields)
    policy = BarFillPolicy(_decimal(fill["participation"]), _decimal(fill["spread_bps"]),
                           _decimal(fill["impact_bps"]), version=fill["version"])
    protection = ProtectionPolicy()
    # Opt-in extension; the original E5 research-v1 schema remains readable.
    if "protective_exit" in raw["fill_model"]:
        protection_raw = _object(raw["fill_model"]["protective_exit"], {
            "enabled", "reward_multiple", "adverse_bps", "version",
        })
        if not isinstance(protection_raw["enabled"], bool):
            raise ValueError("protection.enabled must be a JSON boolean")
        multiple = protection_raw["reward_multiple"]
        protection = ProtectionPolicy(
            enabled=protection_raw["enabled"],
            reward_multiple=_decimal(multiple) if multiple is not None else None,
            adverse_bps=_decimal(protection_raw["adverse_bps"]),
            version=protection_raw["version"],
        )
    fx_series: FxSeries | None = None
    fx_policy: FxReportingPolicy | None = None
    fx_file_hash: str | None = None
    fx_source: str | None = None
    fx_license: str | None = None
    if "fx_reporting" in raw:
        fx_spec = _object(raw["fx_reporting"], {
            "base_currency", "max_age_seconds", "observations_jsonl",
            "sha256", "source", "license",
        })
        if not isinstance(fx_spec["max_age_seconds"], int) or isinstance(
            fx_spec["max_age_seconds"], bool
        ) or fx_spec["max_age_seconds"] < 0:
            raise ValueError("FX max_age_seconds must be a nonnegative integer")
        if not all(isinstance(fx_spec[k], str) and fx_spec[k].strip() for k in (
            "base_currency", "observations_jsonl", "sha256", "source", "license"
        )):
            raise ValueError("FX observation file and provenance required")
        fx_file = (root / fx_spec["observations_jsonl"]).resolve()
        if not fx_file.is_file():
            raise ValueError("FX observation file does not exist")
        fx_file_hash = hashlib.sha256(fx_file.read_bytes()).hexdigest()
        if fx_file_hash != fx_spec["sha256"]:
            raise ValueError("FX observation file hash differs from pinned manifest")
        fx_lines = [line for line in fx_file.read_bytes().splitlines() if line]
        if not fx_lines or any(len(line) > 1_000_000 for line in fx_lines):
            raise ValueError("missing or oversized FX observations")
        observations: list[FxObservation] = []
        for line in fx_lines:
            entry = _object(json.loads(line), {
                "observation_id", "base", "quote", "rate", "event_time",
                "available_at", "received_at", "source",
            })
            observations.append(FxObservation(
                observation_id=entry["observation_id"], base=entry["base"],
                quote=entry["quote"], rate=_decimal(entry["rate"]),
                event_time=_utc(entry["event_time"]),
                available_at=_utc(entry["available_at"]),
                received_at=_utc(entry["received_at"]), source=entry["source"],
            ))
        fx_series = FxSeries(tuple(observations))
        fx_policy = FxReportingPolicy(fx_spec["base_currency"],
                                      timedelta(seconds=fx_spec["max_age_seconds"]))
        fx_source, fx_license = fx_spec["source"], fx_spec["license"]
    settings = BacktestSettings(code_sha=raw["code_sha"], dataset_source=dataset["source"],
                                data_license=dataset["license"])
    runner = HistoricalBacktest(calendar=calendar, strategies=(strategy,), config=trading,
                                opening_cash=cash, risk=limits, fill_policy=policy,
                                protection_policy=protection, settings=settings,
                                fx_series=fx_series, fx_policy=fx_policy,
                                split_schedule=schedule, dividend_schedule=dividend_schedule,
                                delisting_schedule=delisting_schedule)
    report = runner.run(events)
    output_dir = (root / raw["output_dir"]).resolve()
    if output_dir in (root, source_file):
        raise ValueError("report output must not overwrite experiment config/dataset")
    report.export(output_dir)
    audit = inspect_dataset(events, calendar)
    (output_dir / "audit.json").write_bytes(canonical_json(audit))
    if pit_result is not None:
        (output_dir / "pit_gate.json").write_bytes(canonical_json(pit_result))
    artifact_names: tuple[str, ...] = ("report.json", "decisions.jsonl", "fills.jsonl",
                      "equity.jsonl", "audit.json")
    if fx_policy is not None:
        artifact_names += ("fx_equity.jsonl",)
    if pit_result is not None:
        artifact_names += ("pit_gate.json",)
    artifact_hashes = {name: file_sha256(output_dir / name) for name in artifact_names}
    manifest = {
        "schema_version": "e5-research-v1", "run_id": raw["run_id"],
        "code_sha": raw["code_sha"], "dataset_file_sha256": file_hash,
        "dataset_event_sha256": report.dataset_sha256,
        "dataset_source": dataset["source"], "data_license": dataset["license"],
        "dataset_volume_unit": declared if declared is not None else "UNDECLARED",
        "strategy_id": st["id"], "strategy_version": st["version"],
        "fill_model_version": policy.version,
        "protective_exit_version": protection.version if protection.enabled else None,
        "config_sha256": report.config_sha256,
        "run_sha256": report.run_sha256,
        "code_tree_sha256": source_tree_sha256(),
        "audit_sha256": audit_hash(audit),
        "artifact_sha256": artifact_hashes,
        "research_data_release_verified": False,
        "fx_dataset_file_sha256": fx_file_hash,
        "fx_event_sha256": fx_series.digest if fx_series is not None else None,
        "fx_reporting_currency": fx_policy.base_currency if fx_policy is not None else None,
        "fx_source": fx_source, "fx_license": fx_license,
        "fx_data_release_verified": False,
        "delisting_schedule_sha256": delisting_file_hash,
        "pit_dataset_file_sha256": pit_file_hash,
        "pit_evidence_sha256": pit_result.evidence_sha256 if pit_result else None,
        "pit_gate_checked_events": pit_result.event_count if pit_result else None,
        "pit_source": pit_source, "pit_license": pit_license,
        "pit_data_release_verified": False,
        "split_replay_file_sha256": split_file_hash,
        "split_replay_count": len(schedule.splits),
        "split_replay_data_verified": False,
        "dividend_replay_file_sha256": dividend_file_hash,
        "dividend_replay_count": len(dividend_schedule.entitlements),
        "dividend_replay_data_verified": False,
        "warnings": (list(report.notes) + list(audit.warnings)
                     + list(pit_result.reason_codes if pit_result else ("PIT_EVIDENCE_NOT_SUPPLIED",))
                     + (["VOLUME_IS_TICK_COUNT_NOT_TRADED_SHARES"] if declared == "TICK_COUNT" else [])
                     + (["VOLUME_UNIT_NOT_DECLARED"] if declared is None else [])),
    }
    manifest_sha = sha256(manifest)
    (output_dir / "manifest.json").write_bytes(canonical_json(manifest))
    return ExperimentResult(report, raw["run_id"], output_dir, manifest_sha)
