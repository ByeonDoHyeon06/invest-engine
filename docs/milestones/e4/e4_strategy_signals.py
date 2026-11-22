"""A safe, reproducible no-order strategy example using synthetic bars."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.strategies.baselines import NoTradeStrategy
from invest_engine.strategies.contracts import DataRequirement
from invest_engine.strategies.runtime import StrategyRunner


def main() -> None:
    start = datetime(2026, 11, 16, tzinfo=timezone.utc)
    inst = InstrumentId(Market.KR, "KRX", "KR-SYN-E4", "SYN", "KRW")
    session = TradingSession(Market.KR, "KRX", start, start + timedelta(hours=1))
    runner = StrategyRunner(NoTradeStrategy(DataRequirement(
        "market.bar", timedelta(minutes=5), warmup=2
    )), StaticSessionCalendar((session,)))
    for idx in range(3):
        bar_start = start + timedelta(minutes=5 * idx)
        end = bar_start + timedelta(minutes=5)
        event = EventEnvelope(
            f"synthetic-e4-{idx}", "market.bar", "test-fixture", inst,
            end, end, end, idx,
            Bar(bar_start, end, Decimal("100"), Decimal("101"), Decimal("99"),
                Decimal("100"), Decimal("5"), interval=timedelta(minutes=5)),
        )
        outcome = runner.accept(event)
        print(f"event={idx} signals={len(outcome.signals)} reasons={outcome.reason_codes}")


if __name__ == "__main__":
    main()
