from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from invest_engine.core.fixtures import synthetic_ticks
from invest_engine.core.replay import replay_events
from invest_engine.domain.primitives import InstrumentId, Money


@pytest.mark.parametrize("count", [1, 2, 10, 100, 250, 1000])
def test_variable_batch_size_is_deterministic(count: int, kr_instrument: InstrumentId) -> None:
    batch = synthetic_ticks(kr_instrument, count=count)
    assert replay_events(batch) == replay_events(reversed(batch))


@pytest.mark.parametrize("digits", [0, 1, 2, 3, 5, 9])
def test_decimal_money_add_subtract_roundtrip(digits: int) -> None:
    left = Money(Decimal(10) ** -digits, "USD")
    right = Money(Decimal(7) ** digits, "USD")
    assert left + right - right == left


def test_timestamp_parsing_does_not_use_wall_clock(kr_instrument: InstrumentId) -> None:
    start = datetime(2026, 11, 15, tzinfo=timezone.utc)
    values = synthetic_ticks(kr_instrument, count=100, start=start)
    assert replay_events(values).last_available_at == start + timedelta(seconds=99, milliseconds=50)
