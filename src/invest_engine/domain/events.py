"""Versioned, immutable typed market events. E0 deliberately does not create bars."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Generic, TypeVar

from invest_engine.domain.errors import InvalidEvent, UnsupportedData
from invest_engine.domain.primitives import InstrumentId, _decimal, utc_datetime


class BarKind(str, Enum):
    TIME = "TIME"
    VOLUME = "VOLUME"
    DOLLAR = "DOLLAR"
    TICK_COUNT = "TICK_COUNT"


class SessionState(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class TradeTick:
    price: Decimal
    quantity: Decimal
    trade_id: str | None = None

    def __post_init__(self) -> None:
        _decimal(self.price, field="trade.price", positive=True)
        _decimal(self.quantity, field="trade.quantity", positive=True)
        if self.trade_id is not None and not self.trade_id:
            raise InvalidEvent("trade_id must not be empty")


@dataclass(frozen=True, slots=True)
class QuoteTick:
    bid_price: Decimal
    bid_size: Decimal
    ask_price: Decimal
    ask_size: Decimal

    def __post_init__(self) -> None:
        for f in ("bid_price", "ask_price"):
            _decimal(getattr(self, f), field=f, positive=True)
        for f in ("bid_size", "ask_size"):
            _decimal(getattr(self, f), field=f)
            if getattr(self, f) < 0:
                raise InvalidEvent(f"{f} must be non-negative")
        if self.bid_price > self.ask_price:
            raise InvalidEvent("crossed quote: bid > ask")


@dataclass(frozen=True, slots=True)
class BookLevel:
    price: Decimal
    size: Decimal

    def __post_init__(self) -> None:
        _decimal(self.price, field="book.level.price", positive=True)
        _decimal(self.size, field="book.level.size")
        if self.size < 0:
            raise InvalidEvent("book level size must be non-negative")


@dataclass(frozen=True, slots=True)
class OrderBookSnapshot:
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]
    book_sequence: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.bids, tuple) or not isinstance(self.asks, tuple):
            raise InvalidEvent("book levels must be immutable tuples")
        if not self.bids or not self.asks:
            raise InvalidEvent("snapshot requires nonempty bids and asks")
        if any(not isinstance(v, BookLevel) for v in (*self.bids, *self.asks)):
            raise InvalidEvent("book levels must have BookLevel type")
        if any(a.price <= b.price for a, b in zip(self.bids, self.bids[1:], strict=False)):
            raise InvalidEvent("bids must be strictly descending")
        if any(a.price >= b.price for a, b in zip(self.asks, self.asks[1:], strict=False)):
            raise InvalidEvent("asks must be strictly ascending")
        if self.bids[0].price > self.asks[0].price:
            raise InvalidEvent("crossed order book")
        if self.book_sequence is not None and self.book_sequence < 0:
            raise InvalidEvent("book_sequence cannot be negative")


@dataclass(frozen=True, slots=True)
class Bar:
    start: datetime
    end: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    kind: BarKind = BarKind.TIME
    interval: timedelta | None = None
    finalized: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "start", utc_datetime(self.start, field="bar.start"))
        object.__setattr__(self, "end", utc_datetime(self.end, field="bar.end"))
        if self.end <= self.start:
            raise InvalidEvent("bar end must be after start")
        for f in ("open", "high", "low", "close"):
            _decimal(getattr(self, f), field=f, positive=True)
        _decimal(self.volume, field="volume")
        if self.volume < 0:
            raise InvalidEvent("volume cannot be negative")
        if self.high < max(self.open, self.close, self.low):
            raise InvalidEvent("high below another OHLC value")
        if self.low > min(self.open, self.close, self.high):
            raise InvalidEvent("low above another OHLC value")
        if not isinstance(self.kind, BarKind):
            raise InvalidEvent("invalid bar kind")
        if self.kind is BarKind.TIME and (self.interval is None or self.interval <= timedelta(0)):
            raise InvalidEvent("time bar needs positive interval")
        if self.kind is not BarKind.TIME and self.interval is not None:
            raise InvalidEvent("non-time bars must not declare a time interval")


@dataclass(frozen=True, slots=True)
class MarketStatus:
    state: SessionState
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.state, SessionState):
            raise InvalidEvent("invalid session state")


MarketPayload = TradeTick | QuoteTick | OrderBookSnapshot | Bar | MarketStatus
PayloadT = TypeVar("PayloadT", bound=MarketPayload, covariant=True)
_EVENT_TYPES: dict[type[object], str] = {
    TradeTick: "market.trade",
    QuoteTick: "market.quote",
    OrderBookSnapshot: "market.order_book_snapshot",
    Bar: "market.bar",
    MarketStatus: "market.status",
}


@dataclass(frozen=True, slots=True)
class EventEnvelope(Generic[PayloadT]):
    event_id: str
    event_type: str
    source: str
    instrument_id: InstrumentId | None
    event_time: datetime
    available_at: datetime
    received_at: datetime
    ingest_ordinal: int
    payload: PayloadT
    schema_version: int = 1
    source_sequence: int | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    quality_flags: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.event_id or not self.event_id.strip():
            raise InvalidEvent("event_id must be nonempty")
        if not self.source or not self.source.strip():
            raise InvalidEvent("source must be nonempty")
        if self.schema_version != 1:
            raise UnsupportedData(f"unsupported E0 schema version: {self.schema_version}")
        if self.ingest_ordinal < 0 or (
            self.source_sequence is not None and self.source_sequence < 0
        ):
            raise InvalidEvent("event sequence/ordinal cannot be negative")
        if not isinstance(self.quality_flags, tuple) or any(
            not isinstance(x, str) for x in self.quality_flags
        ):
            raise InvalidEvent("quality_flags must be immutable string tuple")
        expected_type = _EVENT_TYPES.get(type(self.payload))
        if expected_type is None:
            raise UnsupportedData("payload type not supported by E0")
        if self.event_type != expected_type:
            raise InvalidEvent(f"event_type must be {expected_type}")
        if self.instrument_id is None and not isinstance(self.payload, MarketStatus):
            raise InvalidEvent("instrument_id required for price/quote/book/bar events")
        if self.instrument_id is not None and not isinstance(self.instrument_id, InstrumentId):
            raise InvalidEvent("instrument_id has invalid type")
        for field_name in ("event_time", "available_at", "received_at"):
            object.__setattr__(
                self, field_name, utc_datetime(getattr(self, field_name), field=field_name)
            )
        # event_time may be later than available_at for scheduled corporate events (future).
        # Market-only E0 payloads still permit clock skew; do not invent a strict ordering.
        if self.received_at < self.available_at:
            raise InvalidEvent("received_at precedes available_at")
