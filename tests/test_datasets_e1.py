"""E1.3 immutable dataset manifests, source lineage and Parquet integrity tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from invest_engine.data.contracts import RawMarketRecord
from invest_engine.data.datasets import (
    AdjustmentPolicy,
    DataCompleteness,
    DatasetManifest,
    DatasetSpec,
    _event_json,
    _raw_json,
    _read_event_json,
    _read_raw_json,
    read_dataset,
    write_dataset,
)
from invest_engine.data.normalization import normalize_record
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import InstrumentId, Market

AT = datetime(2026, 11, 16, 0, tzinfo=timezone.utc)


def spec(**kwargs: object) -> DatasetSpec:
    data: dict[str, object] = {
        "dataset_id": "synthetic_kr_2026_11_v1", "provider": "synthetic",
        "license_id": "synthetic-test-only", "market": Market.KR,
        "event_kind": "trade", "coverage_start": AT,
        "coverage_end": AT + timedelta(days=1),
        "calendar_version": "krx-test-v1", "revision": 1,
        "adjustment": AdjustmentPolicy.RAW,
        "completeness": DataCompleteness.UNVERIFIED,
    }
    data.update(kwargs)
    return DatasetSpec(**data)  # type: ignore[arg-type]


def records(instrument: InstrumentId) -> tuple[RawMarketRecord, ...]:
    return (
        RawMarketRecord(
            event_id="r-1", source="synthetic", kind="trade",
            instrument_id=instrument, event_time=AT,
            available_at=AT + timedelta(milliseconds=1),
            received_at=AT + timedelta(milliseconds=3),
            ingest_ordinal=0, source_sequence=10,
            payload={"price": "100.1234500", "quantity": "7.5", "trade_id": "t1"},
        ),
        RawMarketRecord(
            event_id="r-2", source="synthetic", kind="trade",
            instrument_id=instrument, event_time=AT + timedelta(seconds=10),
            available_at=AT + timedelta(seconds=10),
            received_at=AT + timedelta(seconds=11),
            ingest_ordinal=1, source_sequence=11,
            payload={"price": "101", "quantity": "2", "trade_id": "t2"},
        ),
    )


def test_schema_and_revision_metadata() -> None:
    assert spec().completeness is DataCompleteness.UNVERIFIED
    with pytest.raises(InvalidEvent, match="unsafe"):
        spec(dataset_id="../escape")
    with pytest.raises(InvalidEvent, match="revision"):
        spec(revision=2)
    with pytest.raises(InvalidEvent, match="itself"):
        spec(revision=2, previous_dataset_id="synthetic_kr_2026_11_v1")
    with pytest.raises(InvalidEvent, match="coverage"):
        spec(coverage_end=AT)
    with pytest.raises(InvalidEvent, match="required"):
        spec(license_id="")
    new = spec(dataset_id="synthetic_kr_2026_11_v2", revision=2,
               previous_dataset_id="synthetic_kr_2026_11_v1",
               completeness=DataCompleteness.GAPS_PRESENT)
    assert new.revision == 2


def test_raw_to_json_is_lossless_for_strict_prices(kr_instrument: InstrumentId) -> None:
    source = records(kr_instrument)[0]
    back = _read_raw_json(_raw_json(source))
    assert back == source
    assert back.payload["price"] == "100.1234500"
    assert back.received_at > back.available_at


def test_normalized_event_serialization(kr_instrument: InstrumentId) -> None:
    for raw in records(kr_instrument):
        event = normalize_record(raw)
        restored = _read_event_json(_event_json(event))
        assert restored == event
        assert restored.payload.price == event.payload.price  # type: ignore[union-attr]


def test_can_store_truncated_market_bar_without_reinventing_timestamps(
    kr_instrument: InstrumentId,
) -> None:
    raw = records(kr_instrument)[0]
    original = normalize_record(raw)
    event: EventEnvelope[MarketPayload] = replace(
        original,
        event_type="market.bar",
        event_time=AT + timedelta(minutes=45),
        available_at=AT + timedelta(minutes=45),
        received_at=AT + timedelta(minutes=45),
        payload=Bar(
            start=AT, end=AT + timedelta(minutes=45), interval=timedelta(hours=1),
            open=Decimal("100"), high=Decimal("110"), low=Decimal("99"),
            close=Decimal("108"), volume=Decimal("15"),
        ),
    )
    assert _read_event_json(_event_json(event)) == event


def test_manifest_checks_invalid_hashes() -> None:
    with pytest.raises(InvalidEvent, match="checksum"):
        DatasetManifest(spec(), 0, 0, "not-a-hash", "0" * 64)
    with pytest.raises(InvalidEvent, match="exceed"):
        DatasetManifest(spec(), 0, 1, "0" * 64, "0" * 64)


def test_immutable_parquet_roundtrip_and_integrity(
    tmp_path: Path, kr_instrument: InstrumentId,
) -> None:
    pytest.importorskip("pyarrow")
    raw = records(kr_instrument)
    accepted = tuple(normalize_record(item) for item in raw)
    m = write_dataset(tmp_path, spec(), raw, accepted)
    manifest, original, normalized = read_dataset(tmp_path, m.spec.dataset_id)
    assert manifest == m
    assert original == raw
    assert normalized == accepted
    assert normalized[0].payload.price == Decimal("100.1234500")  # type: ignore[union-attr]
    assert (tmp_path / m.spec.dataset_id / "raw.parquet").exists()
    with pytest.raises(FileExistsError, match="immutable"):
        write_dataset(tmp_path, spec(), raw, accepted)

    target = tmp_path / m.spec.dataset_id / "normalized.parquet"
    target.write_bytes(target.read_bytes() + b"tampered")
    with pytest.raises(InvalidEvent, match="checksum"):
        read_dataset(tmp_path, m.spec.dataset_id)


def test_manifest_tamper_and_noncanonical_ids(tmp_path: Path, kr_instrument: InstrumentId) -> None:
    pytest.importorskip("pyarrow")
    raw = records(kr_instrument)
    m = write_dataset(tmp_path, spec(), raw, tuple(normalize_record(v) for v in raw))
    manifest_file = tmp_path / m.spec.dataset_id / "manifest.json"
    manifest_file.write_text(manifest_file.read_text().replace("synthetic-test-only", "modified"))
    with pytest.raises(InvalidEvent, match="manifest integrity"):
        read_dataset(tmp_path, m.spec.dataset_id)
    with pytest.raises(InvalidEvent, match="unsafe"):
        read_dataset(tmp_path, "../../somewhere")


def test_writer_rejects_unmatched_ids_or_wrong_provider(
    tmp_path: Path, kr_instrument: InstrumentId,
) -> None:
    raw = records(kr_instrument)
    accepted = tuple(normalize_record(v) for v in raw)
    with pytest.raises(InvalidEvent, match="matching"):
        write_dataset(tmp_path, spec(), raw, (replace(accepted[0], event_id="unknown"),))
    with pytest.raises(InvalidEvent, match="source provider"):
        write_dataset(tmp_path, spec(), (replace(raw[0], source="incorrect"),), ())
    with pytest.raises(InvalidEvent, match="normalized event disagrees"):
        alternate = replace(kr_instrument, identifier="DIFFERENT")
        write_dataset(tmp_path, spec(), raw, (replace(accepted[0], instrument_id=alternate),))
    with pytest.raises(InvalidEvent, match="normalized event disagrees"):
        write_dataset(tmp_path, spec(), raw, (replace(accepted[0], available_at=AT),))
    with pytest.raises(InvalidEvent, match="coverage"):
        write_dataset(tmp_path, spec(), (replace(raw[0], event_time=AT-timedelta(days=1)),), ())


def test_coverage_unverified_must_remain_visible_to_research() -> None:
    s = spec()
    assert s.completeness is DataCompleteness.UNVERIFIED
    assert s.adjustment is AdjustmentPolicy.RAW
