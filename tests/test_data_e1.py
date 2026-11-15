"""E1.1 typed source ingestion, feed quality, and as-of visibility tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from invest_engine.data.contracts import (
    DataCapability,
    DataRequest,
    HistoricalDataProvider,
    RawMarketRecord,
    require_capability,
)
from invest_engine.data.normalization import normalize_record
from invest_engine.data.quality import Disposition, QualityFlag, QualityGate, QualityPolicy
from invest_engine.data.visibility import ObservationBuffer
from invest_engine.domain.errors import InvalidEvent, UnsupportedData
from invest_engine.domain.events import Bar, MarketStatus, QuoteTick, TradeTick
from invest_engine.domain.primitives import InstrumentId, Market

AT = datetime(2026, 11, 15, 10, tzinfo=timezone.utc)


def trade(instrument: InstrumentId, **override: object) -> RawMarketRecord:
    data: dict[str, object] = {
        "event_id": "trade-1", "source": "synthetic", "kind": "trade",
        "instrument_id": instrument, "event_time": AT,
        "available_at": AT + timedelta(milliseconds=10),
        "received_at": AT + timedelta(milliseconds=20),
        "ingest_ordinal": 1, "source_sequence": 100,
        "payload": {"price": "123.45", "quantity": "2.5", "trade_id": "tx"},
    }
    data.update(override)
    return RawMarketRecord(**data)  # type: ignore[arg-type]


def test_trade_normalization_retains_decimal_timing_identity(us_instrument: InstrumentId) -> None:
    record = trade(us_instrument)
    event = normalize_record(record)
    assert isinstance(event.payload, TradeTick)
    assert event.payload.price == Decimal("123.45")
    assert event.event_type == "market.trade"
    assert event.instrument_id == us_instrument
    assert event.available_at == AT + timedelta(milliseconds=10)
    assert event.source_sequence == 100


@pytest.mark.parametrize("bad", [123.4, True, None, float("nan"), "Infinity", "garbage"])
def test_reject_inexact_or_invalid_numbers(us_instrument: InstrumentId, bad: object) -> None:
    with pytest.raises(InvalidEvent):
        normalize_record(trade(us_instrument, payload={"price": bad, "quantity": "2"}))


def test_strict_keys_and_missing_values(us_instrument: InstrumentId) -> None:
    with pytest.raises(InvalidEvent, match="unexpected"):
        normalize_record(trade(us_instrument, payload={"price": "2", "quantity": 1, "side": "BUY"}))
    with pytest.raises(InvalidEvent, match="missing"):
        normalize_record(trade(us_instrument, payload={"price": "2"}))


def test_quote_book_status_and_bar_are_typed(kr_instrument: InstrumentId) -> None:
    raw = trade(kr_instrument, kind="quote", payload={
        "bid_price": "98", "bid_size": "3", "ask_price": "99", "ask_size": "4"
    })
    quote = normalize_record(raw)
    assert isinstance(quote.payload, QuoteTick)
    book = normalize_record(trade(kr_instrument, kind="book", payload={
        "bids": [{"price": "98", "size": "3"}],
        "asks": [{"price": "99", "size": "1"}], "book_sequence": 7,
    }))
    assert book.payload.book_sequence == 7
    status = normalize_record(trade(kr_instrument, kind="status", instrument_id=None,
                                    payload={"state": "HALTED", "reason": "synthetic"}))
    assert isinstance(status.payload, MarketStatus)
    bar = normalize_record(trade(kr_instrument, kind="bar", payload={
        "start": "2026-11-15T09:59:00Z", "end": "2026-11-15T10:00:00Z",
        "interval_seconds": 60, "open": "3", "high": "5", "low": "2",
        "close": "4", "volume": "10",
    }))
    assert isinstance(bar.payload, Bar)
    assert bar.payload.interval == timedelta(minutes=1)


def test_reject_bar_interval_mismatch_and_naive_time(kr_instrument: InstrumentId) -> None:
    with pytest.raises(InvalidEvent, match="interval"):
        normalize_record(trade(kr_instrument, kind="bar", payload={
            "start": "2026-11-15T09:58:00Z", "end": "2026-11-15T10:00:00Z",
            "interval_seconds": 60, "open": 3, "high": 5, "low": 2, "close": 4, "volume": 10,
        }))
    with pytest.raises(ValueError, match="timezone-aware"):
        trade(kr_instrument, received_at=datetime(2026, 11, 15))


def test_raw_record_input_is_copied(kr_instrument: InstrumentId) -> None:
    payload: dict[str, object] = {"price": "10", "quantity": "1"}
    record = trade(kr_instrument, payload=payload)
    payload["price"] = "1"
    assert normalize_record(record).payload.price == Decimal("10")  # type: ignore[union-attr]


def test_timezone_normalizes_to_utc(kr_instrument: InstrumentId) -> None:
    kst = ZoneInfo("Asia/Seoul")
    record = trade(kr_instrument, event_time=datetime(2026, 11, 15, 19, tzinfo=kst))
    assert record.event_time == AT


def test_capabilities_are_explicit(kr_instrument: InstrumentId) -> None:
    class Provider:
        def capabilities(self) -> frozenset[DataCapability]:
            return frozenset({DataCapability(Market.KR, "bar", frozenset({timedelta(minutes=30)}))})

        def iter_records(self, request: DataRequest) -> list[RawMarketRecord]:
            return []

    provider: HistoricalDataProvider = Provider()
    require_capability(provider, DataRequest(Market.KR, "bar", AT, AT + timedelta(days=1), timedelta(minutes=30)))
    with pytest.raises(UnsupportedData):
        require_capability(provider, DataRequest(Market.KR, "bar", AT, AT + timedelta(days=1), timedelta(minutes=1)))
    with pytest.raises(UnsupportedData):
        require_capability(provider, DataRequest(Market.US, "bar", AT, AT + timedelta(days=1), timedelta(minutes=30)))
    with pytest.raises(InvalidEvent, match="resolution"):
        DataRequest(Market.KR, "trade", AT, AT + timedelta(days=1), timedelta(minutes=1))


def test_quality_duplicate_and_sequence_gap_stay_quarantined(us_instrument: InstrumentId) -> None:
    gate = QualityGate()
    first = normalize_record(trade(us_instrument))
    assert gate.inspect(first).disposition is Disposition.ACCEPT
    dup = gate.inspect(first)
    assert QualityFlag.DUPLICATE in dup.flags
    second = normalize_record(trade(us_instrument, event_id="trade-2", source_sequence=102,
                                    ingest_ordinal=2, event_time=AT + timedelta(seconds=1)))
    bad = gate.inspect(second)
    assert QualityFlag.SEQUENCE_GAP in bad.flags
    assert QualityFlag.STREAM_UNSYNCED in bad.flags
    third = normalize_record(trade(us_instrument, event_id="trade-3", source_sequence=103,
                                   ingest_ordinal=3, event_time=AT + timedelta(seconds=2)))
    assert gate.inspect(third).disposition is Disposition.QUARANTINE
    gate.reset_stream(QualityGate.stream_key(first), last_sequence=103)
    fourth = normalize_record(trade(us_instrument, event_id="trade-4", source_sequence=104,
                                    ingest_ordinal=4, event_time=AT + timedelta(seconds=3)))
    assert gate.inspect(fourth).accepted


def test_quality_late_stale_and_partial_bar(kr_instrument: InstrumentId) -> None:
    gate = QualityGate(QualityPolicy(timedelta(milliseconds=100), timedelta(milliseconds=30)))
    first = normalize_record(trade(kr_instrument, source_sequence=None, received_at=AT + timedelta(milliseconds=20)))
    assert gate.inspect(first).accepted
    old = normalize_record(trade(kr_instrument, event_id="old", source_sequence=None,
                                 event_time=AT - timedelta(seconds=3), ingest_ordinal=2))
    assert QualityFlag.LATE in gate.inspect(old).flags
    stale = normalize_record(trade(kr_instrument, event_id="stale", source_sequence=None,
                                   received_at=AT + timedelta(seconds=2), ingest_ordinal=3))
    assert QualityFlag.STALE in gate.inspect(stale).flags
    partial = normalize_record(trade(kr_instrument, kind="bar", event_id="partial", source_sequence=None,
        payload={"start": "2026-11-15T09:59:00Z", "end": "2026-11-15T10:00:00Z",
                 "interval_seconds": 60, "open": 1, "high": 3, "low": 1, "close": 2,
                 "volume": 10, "finalized": False}))
    assert QualityFlag.UNFINALIZED_BAR in gate.inspect(partial).flags


def test_as_of_buffer_blocks_future_data(us_instrument: InstrumentId) -> None:
    gate = QualityGate()
    observation = normalize_record(trade(us_instrument))
    decision = gate.inspect(observation)
    buffer = ObservationBuffer()
    buffer.append(decision)
    assert buffer.visible_at(AT) == ()
    assert buffer.visible_at(AT + timedelta(milliseconds=15)) == ()
    assert buffer.visible_at(AT + timedelta(milliseconds=20)) == (observation,)
    with pytest.raises(InvalidEvent, match="duplicate"):
        buffer.append(decision)
    with pytest.raises(ValueError, match="timezone-aware"):
        buffer.visible_at(datetime(2026, 11, 15))
    with pytest.raises(InvalidEvent, match="quarantined"):
        buffer.append(gate.inspect(observation))


def test_sequence_rewind_and_policy_validation(us_instrument: InstrumentId) -> None:
    gate = QualityGate()
    first = normalize_record(trade(us_instrument))
    gate.inspect(first)
    rewind = normalize_record(trade(us_instrument, event_id="rewind", source_sequence=99,
                                     ingest_ordinal=2))
    assert QualityFlag.SEQUENCE_REWIND in gate.inspect(rewind).flags
    with pytest.raises(ValueError, match="negative"):
        QualityPolicy(allowed_lateness=timedelta(seconds=-1))
    with pytest.raises(ValueError, match="negative"):
        gate.reset_stream(QualityGate.stream_key(first), last_sequence=-1)
