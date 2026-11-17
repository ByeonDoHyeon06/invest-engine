"""Offline-only E0 replay verifier command line interface."""

from __future__ import annotations

import argparse
import json
from datetime import timedelta
from pathlib import Path

from invest_engine.research.csv_import import import_ohlcv_csv, write_csv_import_manifest
from invest_engine.core.fixtures import synthetic_ticks
from invest_engine.core.replay import replay_events
from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.research.experiment import run_experiment
from invest_engine.research.stress import export_stress, run_cost_stress


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="invest-engine", description="Offline-only market replay/backtest tools; no broker access"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    replay = subparsers.add_parser("replay-synthetic", help="Replay synthetic trades deterministically")
    replay.add_argument("--count", type=int, default=500)
    replay.add_argument("--market", choices=["KR", "US"], default="KR")
    backtest = subparsers.add_parser("backtest", help="Offline historical market events; no broker access")
    backtest.add_argument("--config", required=True)
    stress = subparsers.add_parser("stress", help="Offline cost/volume assumptions sweep")
    stress.add_argument("--config", required=True)
    stress.add_argument("--output", required=True)
    ingest = subparsers.add_parser("import-csv", help="Offline historical OHLCV import; never trades")
    ingest.add_argument("--input", required=True)
    ingest.add_argument("--output", required=True)
    ingest.add_argument("--market", choices=["KR", "US"], required=True)
    ingest.add_argument("--venue", required=True)
    ingest.add_argument("--identifier", required=True)
    ingest.add_argument("--symbol", required=True)
    ingest.add_argument("--currency", required=True)
    ingest.add_argument("--source", required=True)
    ingest.add_argument("--interval-seconds", type=int, required=True)
    ingest.add_argument("--volume-unit", choices=["SHARES", "TICK_COUNT"], required=True)
    args = parser.parse_args(argv)

    if args.command == "import-csv":
        market = Market(args.market)
        instrument = InstrumentId(market, args.venue, args.identifier,
                                  args.symbol, args.currency)
        out = Path(args.output)
        csv_result = import_ohlcv_csv(
            Path(args.input), out, instrument=instrument, source=args.source,
            interval=timedelta(seconds=args.interval_seconds),
            volume_unit=args.volume_unit,
        )
        write_csv_import_manifest(out.with_suffix(".import.json"), csv_result, args.source)
        print(json.dumps({"records": csv_result.event_count,
                          "events_sha256": csv_result.output_sha256,
                          "volume_unit": csv_result.volume_unit,
                          "execution_eligible": csv_result.execution_eligible}, sort_keys=True))
        return 0

    if args.command == "stress":
        report = run_cost_stress(args.config)
        export_stress(report, args.output, config_file=args.config)
        print(json.dumps({"result_sha256": report.result_sha256,
                          "scenario_count": len(report.outcomes),
                          "output": str(args.output)}, sort_keys=True))
        return 0

    if args.command == "backtest":
        result = run_experiment(args.config)
        print(json.dumps({"run_id": result.run_id, "run_sha256": result.report.run_sha256,
                          "manifest_sha256": result.manifest_sha256,
                          "output_dir": str(result.output_dir)}, sort_keys=True))
        return 0
    if args.command == "replay-synthetic":
        market = Market(args.market)
        instrument = InstrumentId(
            market=market,
            venue="KRX" if market == Market.KR else "XNAS",
            identifier=f"SYNTHETIC-{market.value}",
            symbol="SYNTHETIC",
            currency="KRW" if market == Market.KR else "USD",
        )
        summary = replay_events(synthetic_ticks(instrument, count=args.count))
        print(
            json.dumps(
                {"count": summary.event_count, "state_hash": summary.state_hash,
                 "events_by_type": summary.events_by_type},
                sort_keys=True,
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
