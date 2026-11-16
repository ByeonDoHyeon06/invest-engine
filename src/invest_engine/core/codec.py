"""Versioned, lossless codec for the E0 market-event domain schema.

Future event variants require explicit decoders and a schema-version policy;
never guess payload types from loosely typed JSON.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from invest_engine.core.replay import canonical_bytes
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
from invest_engine.domain.primitives import AssetClass, InstrumentId, Market


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise InvalidEvent("expected JSON object")
    return cast(dict[str, Any], value)


def _datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _decimal(value: str) -> Decimal:
    return Decimal(value)


def _payload(tag: str, value: dict[str, Any]) -> MarketPayload:
    if tag == "market.trade":
        return TradeTick(_decimal(value["price"]), _decimal(value["quantity"]), value["trade_id"])
    if tag == "market.quote":
        return QuoteTick(
            _decimal(value["bid_price"]), _decimal(value["bid_size"]),
            _decimal(value["ask_price"]), _decimal(value["ask_size"]),
        )
    if tag == "market.order_book_snapshot":
        bids = tuple(
            BookLevel(_decimal(row["price"]), _decimal(row["size"])) for row in value["bids"]
        )
        asks = tuple(
            BookLevel(_decimal(row["price"]), _decimal(row["size"])) for row in value["asks"]
        )
        return OrderBookSnapshot(bids, asks, value["book_sequence"])
    if tag == "market.bar":
        resolution = value["interval"]
        interval = (
            timedelta(microseconds=int(resolution["microseconds"]))
            if resolution is not None else None
        )
        return Bar(
            _datetime(value["start"]), _datetime(value["end"]),
            open=_decimal(value["open"]), high=_decimal(value["high"]),
            low=_decimal(value["low"]), close=_decimal(value["close"]),
            volume=_decimal(value["volume"]),
            kind=BarKind(value["kind"]), interval=interval, finalized=value["finalized"],
        )
    if tag == "market.status":
        return MarketStatus(SessionState(value["state"]), value["reason"])
    raise UnsupportedData(f"unknown event payload: {tag}")


def decode_event(data: bytes) -> EventEnvelope[MarketPayload]:
    """Decode JSON produced by canonical_bytes; reject malformed or altered payloads."""
    try:
        record = _mapping(json.loads(data))
        inst = record["instrument_id"]
        instrument: InstrumentId | None = None
        if inst is not None:
            identifier = _mapping(inst)
            instrument = InstrumentId(
                Market(identifier["market"]), identifier["venue"],
                identifier["identifier"], identifier["symbol"],
                identifier["currency"], AssetClass(identifier["asset_class"]),
            )
        tag = str(record["event_type"])
        result: EventEnvelope[MarketPayload] = EventEnvelope(
            event_id=record["event_id"], event_type=tag, source=record["source"],
            instrument_id=instrument, event_time=_datetime(record["event_time"]),
            available_at=_datetime(record["available_at"]),
            received_at=_datetime(record["received_at"]),
            ingest_ordinal=record["ingest_ordinal"],
            payload=_payload(tag, _mapping(record["payload"])),
            schema_version=record["schema_version"],
            source_sequence=record["source_sequence"],
            correlation_id=record["correlation_id"],
            causation_id=record["causation_id"],
            quality_flags=tuple(record["quality_flags"]),
        )
        if canonical_bytes(result) != data:
            raise InvalidEvent("event encoding is not canonical")
        return result
    except (TypeError, ValueError, KeyError, OverflowError, json.JSONDecodeError) as exc:
        raise InvalidEvent(f"malformed persisted event: {type(exc).__name__}") from exc
