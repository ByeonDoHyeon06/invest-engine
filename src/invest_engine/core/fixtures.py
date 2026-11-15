"""Synthetic-only events. No third-party market data or account information."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from invest_engine.domain.events import EventEnvelope, TradeTick
from invest_engine.domain.primitives import InstrumentId


def synthetic_ticks(
    instrument: InstrumentId,
    *,
    count: int = 500,
    start: datetime = datetime(2025, 1, 2, 0, 0, tzinfo=timezone.utc),
) -> tuple[EventEnvelope[TradeTick], ...]:
    """Fixed integer-derived prices. Test data must never resemble broker credentials."""
    if count < 0:
        raise ValueError("count must be non-negative")
    return tuple(
        EventEnvelope(
            event_id=f"synthetic-{instrument.key}-{i:06d}",
            event_type="market.trade",
            source="synthetic:e0:v1",
            instrument_id=instrument,
            event_time=start + timedelta(seconds=i),
            available_at=start + timedelta(seconds=i, milliseconds=50),
            received_at=start + timedelta(seconds=i, milliseconds=100),
            ingest_ordinal=i,
            payload=TradeTick(
                price=Decimal(100) + Decimal(i % 17) / Decimal(100),
                quantity=Decimal(i % 11 + 1),
                trade_id=f"t{i}",
            ),
        )
        for i in range(count)
    )
