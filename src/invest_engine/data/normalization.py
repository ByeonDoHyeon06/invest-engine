"""Strict, provider-neutral raw-to-domain market event normalization."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Mapping

from invest_engine.data.contracts import RawMarketRecord
from invest_engine.domain.errors import InvalidEvent, UnsupportedData
from invest_engine.domain.events import (
    Bar,
    BarKind,
    BookLevel,
    EventEnvelope,
    MarketPayload,
    MarketStatus,
    OrderBookSnapshot,
    QuoteTick,
    SessionState,
    TradeTick,
)
from invest_engine.domain.primitives import utc_datetime


def _number(value: object, name: str) -> Decimal:
    """Never create financial decimals from binary floating point values."""
    if isinstance(value, bool) or not isinstance(value, (int, str, Decimal)):
        raise InvalidEvent(f"{name} must be Decimal, decimal string, or integer")
    if isinstance(value, str) and not value.strip():
        raise InvalidEvent(f"{name} is empty")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise InvalidEvent(f"invalid decimal for {name}") from exc
    if not result.is_finite():
        raise InvalidEvent(f"{name} must be finite")
    return result


def _instant(value: object, field: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidEvent(f"invalid ISO timestamp in {field}") from exc
    if not isinstance(value, datetime):
        raise InvalidEvent(f"{field} must be datetime or ISO timestamp")
    return utc_datetime(value, field=field)


def _int(value: object, name: str, *, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidEvent(f"{name} must be an integer")
    if positive and value <= 0:
        raise InvalidEvent(f"{name} must be positive")
    return value


def _keys(payload: Mapping[str, object], *, required: set[str], optional: set[str] | None = None) -> None:
    found = set(payload)
    missing = required - found
    unexpected = found - required - (optional or set())
    if missing or unexpected:
        raise InvalidEvent(f"invalid payload fields: missing={sorted(missing)}, unexpected={sorted(unexpected)}")


def _levels(value: object, name: str) -> tuple[BookLevel, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise InvalidEvent(f"{name} must be a nonempty sequence")
    levels: list[BookLevel] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            raise InvalidEvent("book levels must contain mappings")
        _keys(raw, required={"price", "size"})
        levels.append(BookLevel(_number(raw["price"], "price"), _number(raw["size"], "size")))
    return tuple(levels)


def _payload(kind: str, raw: Mapping[str, object]) -> MarketPayload:
    if kind == "trade":
        _keys(raw, required={"price", "quantity"}, optional={"trade_id"})
        tid = raw.get("trade_id")
        if tid is not None and not isinstance(tid, str):
            raise InvalidEvent("trade_id must be a string")
        return TradeTick(_number(raw["price"], "price"), _number(raw["quantity"], "quantity"), tid)
    if kind == "quote":
        _keys(raw, required={"bid_price", "bid_size", "ask_price", "ask_size"})
        return QuoteTick(
            bid_price=_number(raw["bid_price"], "bid_price"),
            bid_size=_number(raw["bid_size"], "bid_size"),
            ask_price=_number(raw["ask_price"], "ask_price"),
            ask_size=_number(raw["ask_size"], "ask_size"),
        )
    if kind == "book":
        _keys(raw, required={"bids", "asks"}, optional={"book_sequence"})
        seq = raw.get("book_sequence")
        if seq is not None:
            seq = _int(seq, "book_sequence")
        return OrderBookSnapshot(_levels(raw["bids"], "bids"), _levels(raw["asks"], "asks"), seq)
    if kind == "bar":
        _keys(raw, required={"start", "end", "open", "high", "low", "close", "volume", "interval_seconds"}, optional={"finalized"})
        start, end = _instant(raw["start"], "bar.start"), _instant(raw["end"], "bar.end")
        seconds = _int(raw["interval_seconds"], "interval_seconds", positive=True)
        interval = timedelta(seconds=seconds)
        if end - start != interval:
            raise InvalidEvent("bar start/end do not match interval_seconds")
        finalized = raw.get("finalized", True)
        if not isinstance(finalized, bool):
            raise InvalidEvent("finalized must be boolean")
        return Bar(
            start=start, end=end,
            open=_number(raw["open"], "open"),
            high=_number(raw["high"], "high"),
            low=_number(raw["low"], "low"),
            close=_number(raw["close"], "close"),
            volume=_number(raw["volume"], "volume"),
            kind=BarKind.TIME, interval=interval, finalized=finalized,
        )
    if kind == "status":
        _keys(raw, required={"state"}, optional={"reason"})
        reason = raw.get("reason", "")
        if not isinstance(reason, str):
            raise InvalidEvent("reason must be a string")
        value = raw["state"]
        if not isinstance(value, str):
            raise InvalidEvent("market state must be a string")
        try:
            state = SessionState(value)
        except (ValueError, TypeError) as exc:
            raise InvalidEvent("unknown market state") from exc
        return MarketStatus(state, reason)
    raise UnsupportedData(f"unsupported payload kind: {kind}")


def normalize_record(raw: RawMarketRecord) -> EventEnvelope[MarketPayload]:
    """Normalize a source adapter record without changing its timestamp meaning."""
    payload = _payload(raw.kind, raw.payload)
    return EventEnvelope(
        event_id=raw.event_id,
        event_type={
            "trade": "market.trade", "quote": "market.quote",
            "book": "market.order_book_snapshot", "bar": "market.bar",
            "status": "market.status",
        }[raw.kind],
        source=raw.source,
        instrument_id=raw.instrument_id,
        event_time=raw.event_time,
        available_at=raw.available_at,
        received_at=raw.received_at,
        ingest_ordinal=raw.ingest_ordinal,
        source_sequence=raw.source_sequence,
        payload=payload,
    )
