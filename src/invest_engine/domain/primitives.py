"""Instrument and monetary primitives without broker-specific assumptions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum


class Market(str, Enum):
    KR = "KR"
    US = "US"


class AssetClass(str, Enum):
    EQUITY = "EQUITY"
    ETF = "ETF"


def utc_datetime(value: datetime, *, field: str = "timestamp") -> datetime:
    """Reject naive datetimes and store aware instants in UTC."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(timezone.utc)


def _decimal(value: Decimal, *, field: str, positive: bool = False) -> Decimal:
    # Float parsing silently introduces a binary precision error; explicitly disallow it.
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{field} must be a finite Decimal (not float)")
    if positive and value <= 0:
        raise ValueError(f"{field} must be positive")
    return value


def _currency(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value):
        raise ValueError("currency must be an uppercase 3-letter ISO 4217 code")
    return value


@dataclass(frozen=True, slots=True)
class InstrumentId:
    market: Market
    venue: str
    identifier: str  # stable provider-independent ID once instrument master is available
    symbol: str  # point-in-time symbol, not a globally unique ID
    currency: str
    asset_class: AssetClass = AssetClass.EQUITY

    def __post_init__(self) -> None:
        if not isinstance(self.market, Market) or not isinstance(self.asset_class, AssetClass):
            raise ValueError("market/asset_class must be declared enums")
        for field in ("venue", "identifier", "symbol"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field} must be a nonempty string")
            if value != value.strip():
                raise ValueError(f"{field} must not contain leading/trailing whitespace")
        _currency(self.currency)

    @property
    def key(self) -> str:
        return f"{self.market.value}:{self.venue}:{self.identifier}"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        _decimal(self.amount, field="money.amount")
        _currency(self.currency)

    def _check_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError("cannot combine amounts with different currencies")

    def __add__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._check_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: Money) -> Money:
        if not isinstance(other, Money):
            return NotImplemented
        self._check_currency(other)
        return Money(self.amount - other.amount, self.currency)


@dataclass(frozen=True, slots=True)
class Price:
    value: Decimal
    currency: str

    def __post_init__(self) -> None:
        _decimal(self.value, field="price", positive=True)
        _currency(self.currency)


@dataclass(frozen=True, slots=True)
class Quantity:
    value: Decimal

    def __post_init__(self) -> None:
        _decimal(self.value, field="quantity", positive=True)
