"""Immutable, checksum-verified raw and normalized market-data dataset packages."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping

from invest_engine.data.contracts import RawMarketRecord, SUPPORTED_KINDS
from invest_engine.domain.errors import InvalidEvent, UnsupportedData
from invest_engine.domain.events import (
    Bar, BarKind, BookLevel, EventEnvelope, MarketPayload,
    MarketStatus, OrderBookSnapshot, QuoteTick, SessionState, TradeTick,
)
from invest_engine.domain.primitives import AssetClass, InstrumentId, Market, utc_datetime


class DataCompleteness(str, Enum):
    PROVIDER_ATTESTED = "PROVIDER_ATTESTED"
    GAPS_PRESENT = "GAPS_PRESENT"
    UNVERIFIED = "UNVERIFIED"


class AdjustmentPolicy(str, Enum):
    RAW = "RAW"
    SPLIT_ADJUSTED = "SPLIT_ADJUSTED"
    TOTAL_RETURN = "TOTAL_RETURN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class DatasetSpec:
    dataset_id: str
    provider: str
    license_id: str
    market: Market
    event_kind: str
    coverage_start: datetime
    coverage_end: datetime
    calendar_version: str
    revision: int = 1
    previous_dataset_id: str | None = None
    adjustment: AdjustmentPolicy = AdjustmentPolicy.UNKNOWN
    completeness: DataCompleteness = DataCompleteness.UNVERIFIED

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}", self.dataset_id):
            raise InvalidEvent("unsafe dataset_id")
        if not isinstance(self.market, Market) or self.event_kind not in SUPPORTED_KINDS:
            raise UnsupportedData("invalid dataset market or event kind")
        if not isinstance(self.adjustment, AdjustmentPolicy) or not isinstance(self.completeness, DataCompleteness):
            raise InvalidEvent("invalid dataset adjustment/completeness")
        for name in ("provider", "license_id", "calendar_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise InvalidEvent(f"dataset {name} is required")
        object.__setattr__(self, "coverage_start", utc_datetime(self.coverage_start, field="coverage_start"))
        object.__setattr__(self, "coverage_end", utc_datetime(self.coverage_end, field="coverage_end"))
        if self.coverage_end <= self.coverage_start:
            raise InvalidEvent("coverage_end must follow coverage_start")
        if self.revision < 1:
            raise InvalidEvent("revision must be >= 1")
        if self.revision > 1 and not self.previous_dataset_id:
            raise InvalidEvent("dataset revision requires previous_dataset_id")
        if self.previous_dataset_id == self.dataset_id:
            raise InvalidEvent("dataset cannot revise itself")


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    spec: DatasetSpec
    raw_count: int
    normalized_count: int
    raw_sha256: str
    normalized_sha256: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.raw_count < 0 or self.normalized_count < 0:
            raise InvalidEvent("dataset counts must be non-negative")
        if self.normalized_count > self.raw_count:
            raise InvalidEvent("normalized observations exceed raw data")
        for hash_value in (self.raw_sha256, self.normalized_sha256):
            if not re.fullmatch(r"[0-9a-f]{64}", hash_value):
                raise InvalidEvent("invalid parquet checksum")
        if self.schema_version != 1:
            raise UnsupportedData("dataset manifest schema not supported")


def _instant(value: object) -> datetime:
    if not isinstance(value, str):
        raise InvalidEvent("stored timestamp must be an ISO string")
    return utc_datetime(datetime.fromisoformat(value), field="stored.timestamp")


def _instrument(data: object) -> InstrumentId | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise InvalidEvent("invalid instrument encoding")
    return InstrumentId(
        Market(data["market"]), data["venue"], data["identifier"], data["symbol"],
        data["currency"], AssetClass(data["asset_class"]),
    )


def _serializable(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, timedelta):
        return {"microseconds": (value.days * 86400 + value.seconds) * 1_000_000 + value.microseconds}
    if isinstance(value, InstrumentId):
        return {field: _serializable(getattr(value, field)) for field in (
            "market", "venue", "identifier", "symbol", "currency", "asset_class")}
    if isinstance(value, Mapping):
        return {str(key): _serializable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_serializable(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise InvalidEvent("unsupported dataset value type")


def _raw_json(raw: RawMarketRecord) -> str:
    data = {name: _serializable(getattr(raw, name)) for name in (
        "event_id", "source", "kind", "instrument_id", "event_time", "available_at",
        "received_at", "ingest_ordinal", "payload", "source_sequence")}
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _read_raw_json(text: str) -> RawMarketRecord:
    data = json.loads(text)
    return RawMarketRecord(
        event_id=data["event_id"], source=data["source"], kind=data["kind"],
        instrument_id=_instrument(data["instrument_id"]),
        event_time=_instant(data["event_time"]),
        available_at=_instant(data["available_at"]),
        received_at=_instant(data["received_at"]),
        ingest_ordinal=data["ingest_ordinal"], payload=data["payload"],
        source_sequence=data["source_sequence"],
    )


def _event_json(event: EventEnvelope[MarketPayload]) -> str:
    # Reuse E0 stable event serialization; no rounding through floats.
    from invest_engine.core.replay import canonical_bytes

    return canonical_bytes(event).decode("utf-8")


def _read_event_json(text: str) -> EventEnvelope[MarketPayload]:
    data = json.loads(text)
    item = data["payload"]
    kind = data["event_type"]
    payload: MarketPayload
    if kind == "market.trade":
        payload = TradeTick(Decimal(item["price"]), Decimal(item["quantity"]), item["trade_id"])
    elif kind == "market.quote":
        payload = QuoteTick(
            bid_price=Decimal(item["bid_price"]), bid_size=Decimal(item["bid_size"]),
            ask_price=Decimal(item["ask_price"]), ask_size=Decimal(item["ask_size"]),
        )
    elif kind == "market.order_book_snapshot":
        payload = OrderBookSnapshot(
            tuple(BookLevel(Decimal(v["price"]), Decimal(v["size"])) for v in item["bids"]),
            tuple(BookLevel(Decimal(v["price"]), Decimal(v["size"])) for v in item["asks"]),
            item["book_sequence"],
        )
    elif kind == "market.bar":
        interval_data = item["interval"]
        duration = None if interval_data is None else timedelta(microseconds=interval_data["microseconds"])
        payload = Bar(
            start=_instant(item["start"]), end=_instant(item["end"]),
            open=Decimal(item["open"]), high=Decimal(item["high"]),
            low=Decimal(item["low"]), close=Decimal(item["close"]),
            volume=Decimal(item["volume"]), kind=BarKind(item["kind"]),
            interval=duration, finalized=item["finalized"],
        )
    elif kind == "market.status":
        payload = MarketStatus(SessionState(item["state"]), item["reason"])
    else:
        raise UnsupportedData("unknown stored event type")
    return EventEnvelope(
        event_id=data["event_id"], event_type=kind, source=data["source"],
        instrument_id=_instrument(data["instrument_id"]),
        event_time=_instant(data["event_time"]),
        available_at=_instant(data["available_at"]),
        received_at=_instant(data["received_at"]),
        ingest_ordinal=data["ingest_ordinal"], payload=payload,
        schema_version=data["schema_version"], source_sequence=data["source_sequence"],
        correlation_id=data["correlation_id"], causation_id=data["causation_id"],
        quality_flags=tuple(data["quality_flags"]),
    )


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as reader:
        for chunk in iter(lambda: reader.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_parquet(path: Path, payloads: list[tuple[str, str]]) -> None:
    pa = importlib.import_module("pyarrow")
    pq = importlib.import_module("pyarrow.parquet")
    table = pa.table({"event_id": [row[0] for row in payloads], "event_json": [row[1] for row in payloads]})
    pq.write_table(table, path, compression="zstd")


def _read_parquet(path: Path) -> list[tuple[str, str]]:
    pq = importlib.import_module("pyarrow.parquet")
    table = pq.read_table(path, columns=["event_id", "event_json"])
    return [(row["event_id"], row["event_json"]) for row in table.to_pylist()]


def _spec_dict(spec: DatasetSpec) -> dict[str, object]:
    return {name: _serializable(getattr(spec, name)) for name in (
        "dataset_id", "provider", "license_id", "market", "event_kind", "coverage_start",
        "coverage_end", "calendar_version", "revision", "previous_dataset_id",
        "adjustment", "completeness")}


def _manifest_text(manifest: DatasetManifest) -> str:
    data = {"spec": _spec_dict(manifest.spec), "raw_count": manifest.raw_count,
            "normalized_count": manifest.normalized_count, "raw_sha256": manifest.raw_sha256,
            "normalized_sha256": manifest.normalized_sha256, "schema_version": manifest.schema_version}
    return json.dumps(data, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def _parse_manifest(text: str) -> DatasetManifest:
    obj = json.loads(text)
    item = obj["spec"]
    spec = DatasetSpec(
        dataset_id=item["dataset_id"], provider=item["provider"], license_id=item["license_id"],
        market=Market(item["market"]), event_kind=item["event_kind"],
        coverage_start=_instant(item["coverage_start"]), coverage_end=_instant(item["coverage_end"]),
        calendar_version=item["calendar_version"], revision=item["revision"],
        previous_dataset_id=item["previous_dataset_id"], adjustment=AdjustmentPolicy(item["adjustment"]),
        completeness=DataCompleteness(item["completeness"]),
    )
    return DatasetManifest(spec, obj["raw_count"], obj["normalized_count"],
                           obj["raw_sha256"], obj["normalized_sha256"], obj["schema_version"])


def write_dataset(
    root: Path,
    spec: DatasetSpec,
    raw_records: Iterable[RawMarketRecord],
    normalized_events: Iterable[EventEnvelope[MarketPayload]],
) -> DatasetManifest:
    """Write a new immutable dataset directory (never overwrite a previous revision)."""
    raw = tuple(raw_records)
    normal = tuple(normalized_events)
    if len({x.event_id for x in raw}) != len(raw) or len({x.event_id for x in normal}) != len(normal):
        raise InvalidEvent("duplicate dataset event identity")
    by_id = {item.event_id: item for item in raw}
    if not {x.event_id for x in normal}.issubset(by_id):
        raise InvalidEvent("normalized event without matching raw source")
    expected_kind = {
        "trade": "market.trade", "quote": "market.quote",
        "book": "market.order_book_snapshot", "bar": "market.bar",
        "status": "market.status",
    }
    for event in normal:
        origin = by_id[event.event_id]
        if (
            event.event_type != expected_kind[origin.kind]
            or event.instrument_id != origin.instrument_id
            or event.event_time != origin.event_time
            or event.available_at != origin.available_at
            or event.received_at != origin.received_at
            or event.ingest_ordinal != origin.ingest_ordinal
            or event.quality_flags
        ):
            raise InvalidEvent("normalized event disagrees with raw identity or timestamps")
    for source_record in raw:
        if source_record.source != spec.provider:
            raise InvalidEvent("source provider differs from dataset provenance")
        if (source_record.instrument_id is not None
                and source_record.instrument_id.market != spec.market):
            raise InvalidEvent("mixed market dataset is prohibited")
        if not spec.coverage_start <= source_record.event_time < spec.coverage_end:
            raise InvalidEvent("observation outside declared dataset coverage")
    for normalized_record in normal:
        if normalized_record.source != spec.provider:
            raise InvalidEvent("source provider differs from dataset provenance")
        if (normalized_record.instrument_id is not None
                and normalized_record.instrument_id.market != spec.market):
            raise InvalidEvent("mixed market dataset is prohibited")
        if not spec.coverage_start <= normalized_record.event_time < spec.coverage_end:
            raise InvalidEvent("observation outside declared dataset coverage")
    for item in raw:
        if item.kind != spec.event_kind:
            raise InvalidEvent("raw event kind differs from dataset kind")
    root.mkdir(parents=True, exist_ok=True)
    dest = root / spec.dataset_id
    if dest.exists():
        raise FileExistsError("dataset is immutable; create a new revision ID")
    stage = Path(tempfile.mkdtemp(prefix=".stage-", dir=root))
    try:
        raw_path, normalized_path = stage / "raw.parquet", stage / "normalized.parquet"
        _write_parquet(raw_path, [(v.event_id, _raw_json(v)) for v in raw])
        _write_parquet(normalized_path, [(v.event_id, _event_json(v)) for v in normal])
        manifest = DatasetManifest(spec, len(raw), len(normal), _sha(raw_path), _sha(normalized_path))
        manifest_text = _manifest_text(manifest)
        (stage / "manifest.json").write_text(manifest_text, encoding="utf-8")
        (stage / "manifest.sha256").write_text(
            hashlib.sha256(manifest_text.encode("utf-8")).hexdigest() + "\n", encoding="ascii")
        if dest.exists():
            raise FileExistsError("dataset was created concurrently")
        os.rename(stage, dest)
        return manifest
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def read_dataset(root: Path, dataset_id: str) -> tuple[DatasetManifest, tuple[RawMarketRecord, ...], tuple[EventEnvelope[MarketPayload], ...]]:
    """Verify package hashes before returning any data for research."""
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}", dataset_id):
        raise InvalidEvent("unsafe dataset_id")
    base = root / dataset_id
    text = (base / "manifest.json").read_text(encoding="utf-8")
    expected = (base / "manifest.sha256").read_text(encoding="ascii").strip()
    if hashlib.sha256(text.encode("utf-8")).hexdigest() != expected:
        raise InvalidEvent("dataset manifest integrity mismatch")
    manifest = _parse_manifest(text)
    if manifest.spec.dataset_id != dataset_id:
        raise InvalidEvent("manifest dataset identity mismatch")
    raw_path, normal_path = base / "raw.parquet", base / "normalized.parquet"
    if _sha(raw_path) != manifest.raw_sha256 or _sha(normal_path) != manifest.normalized_sha256:
        raise InvalidEvent("parquet checksum mismatch")
    raw_rows, norm_rows = _read_parquet(raw_path), _read_parquet(normal_path)
    if len(raw_rows) != manifest.raw_count or len(norm_rows) != manifest.normalized_count:
        raise InvalidEvent("dataset row count mismatch")
    raw = tuple(_read_raw_json(text) for _, text in raw_rows)
    normalized = tuple(_read_event_json(text) for _, text in norm_rows)
    if any(row_id != record.event_id for (row_id, _), record in zip(raw_rows, raw, strict=True)):
        raise InvalidEvent("raw parquet row identity mismatch")
    if any(row_id != event.event_id for (row_id, _), event in zip(norm_rows, normalized, strict=True)):
        raise InvalidEvent("normalized parquet row identity mismatch")
    return manifest, raw, normalized
