"""Offline-only E0 replay verifier command line interface."""

from __future__ import annotations

import argparse
import json

from invest_engine.core.fixtures import synthetic_ticks
from invest_engine.core.replay import replay_events
from invest_engine.domain.primitives import InstrumentId, Market


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="invest-engine", description="E0 synthetic replay verifier; no orders or API calls"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    replay = subparsers.add_parser("replay-synthetic", help="Replay synthetic trades deterministically")
    replay.add_argument("--count", type=int, default=500)
    replay.add_argument("--market", choices=["KR", "US"], default="KR")
    args = parser.parse_args(argv)

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
