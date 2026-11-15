from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from invest_engine.domain.primitives import (
    AssetClass,
    InstrumentId,
    Market,
    Money,
    Price,
    Quantity,
    utc_datetime,
)


def test_markets_are_part_of_identity() -> None:
    kr = InstrumentId(Market.KR, "KRX", "ID1", "ABC", "KRW")
    us = InstrumentId(Market.US, "XNAS", "ID1", "ABC", "USD")
    assert kr != us
    assert kr.key != us.key


def test_money_currency_is_explicit() -> None:
    assert Money(Decimal("1.25"), "KRW") + Money(Decimal("2.5"), "KRW") == Money(
        Decimal("3.75"), "KRW"
    )
    assert Money(Decimal("1.25"), "KRW") - Money(Decimal("2.5"), "KRW") == Money(
        Decimal("-1.25"), "KRW"
    )
    with pytest.raises(ValueError, match="different currencies"):
        _ = Money(Decimal("1"), "KRW") + Money(Decimal("1"), "USD")


@pytest.mark.parametrize("value", [1.23, Decimal("NaN"), Decimal("Infinity"), "12.3"])
def test_float_nan_infinity_implicit_values_are_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="finite Decimal"):
        Money(value, "USD")  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("-1")])
def test_invalid_price_quantity(value: Decimal) -> None:
    with pytest.raises(ValueError):
        Price(value, "USD")
    with pytest.raises(ValueError):
        Quantity(value)


def test_instrument_validation_and_immutable() -> None:
    with pytest.raises(ValueError):
        InstrumentId(Market.US, "", "id", "AAPL", "USD")
    with pytest.raises(ValueError):
        InstrumentId(Market.US, "XNAS", "id", " AAPL", "USD")
    with pytest.raises(ValueError):
        InstrumentId(Market.US, "XNAS", "id", "AAPL", "usd")
    instrument = InstrumentId(Market.US, "XNAS", "id", "AAPL", "USD", AssetClass.ETF)
    with pytest.raises(FrozenInstanceError):
        instrument.symbol = "MSFT"  # type: ignore[misc]


def test_utc_datetime_rejects_naive() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        utc_datetime(datetime(2026, 11, 15, 11, 0))
    assert utc_datetime(datetime(2026, 11, 15, 11, tzinfo=timezone.utc)).utcoffset() == timedelta(0)
