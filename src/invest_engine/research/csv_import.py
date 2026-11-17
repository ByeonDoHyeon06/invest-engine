"""Offline CSV OHLCV -> canonical market events, with explicit volume provenance.

No network calls, corporate-action adjustment, or license assertions. The
converter does *not* certify that bars were actually available at their close.
"""
from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from invest_engine.core.replay import canonical_bytes
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, utc_datetime


@dataclass(frozen=True, slots=True)
class CSVImportResult:
    event_count: int
    source_sha256: str
    output_sha256: str
    volume_unit: str
    execution_eligible: bool


def import_ohlcv_csv(
    csv_path: Path, output_jsonl: Path, *, instrument: InstrumentId,
    source: str, interval: timedelta,
    volume_unit: str, observation_delay: timedelta = timedelta(seconds=1),
) -> CSVImportResult:
    """CSV header exactly datetime,open,high,low,close,volume; UTC open time.

    Only a verified SHARES unit is eligible for execution-model inputs. Unknown
    volume units cannot be silently relabeled as traded shares.
    """
    if volume_unit not in {"SHARES", "TICK_COUNT"}:
        raise ValueError("volume_unit must be SHARES or TICK_COUNT")
    if (not source.strip() or interval <= timedelta(0)
            or observation_delay < timedelta(0)):
        raise ValueError("invalid source/interval/delay")
    if csv_path.resolve() == output_jsonl.resolve():
        raise ValueError("cannot overwrite raw market data")
    original = csv_path.read_bytes()
    if len(original) > 50_000_000:
        raise ValueError("CSV input exceeds per-run cap")
    try:
        content = original.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8") from exc
    reader = csv.DictReader(content.splitlines())
    expected = ["datetime", "open", "high", "low", "close", "volume"]
    if reader.fieldnames != expected:
        raise ValueError("CSV requires exact header datetime,open,high,low,close,volume")
    events: list[EventEnvelope[Bar]] = []
    prev_end: datetime | None = None
    for n, row in enumerate(reader):
        if n >= 400_000:
            raise ValueError("CSV row count exceeds bounded research converter")
        if not isinstance(row, dict) or set(row) != set(expected) or any(v is None for v in row.values()):
            raise ValueError("missing or unexpected CSV field")
        try:
            stamp = str(row["datetime"])
            if not (stamp.endswith("Z") or stamp.endswith("+00:00")):
                raise ValueError("UTC bar timestamp is required")
            start = utc_datetime(datetime.fromisoformat(stamp.replace("Z", "+00:00")))
            end = start + interval
            prices = [Decimal(str(row[name])) for name in ("open", "high", "low", "close", "volume")]
            if prev_end is not None and start < prev_end:
                raise ValueError("CSV rows overlap or are not time ordered")
            bar = Bar(start, end, prices[0], prices[1], prices[2],
                      prices[3], prices[4], interval=interval)
            seen = end + observation_delay
            event = EventEnvelope(
                f"csv:{hashlib.sha256(original).hexdigest()[:16]}:{n}",
                "market.bar", source, instrument, end, seen, seen, n, bar,
            )
        except (InvalidOperation, OverflowError, TypeError) as exc:
            raise ValueError(f"invalid numerical CSV record {n}") from exc
        events.append(event)
        prev_end = end
    if not events:
        raise ValueError("CSV contains no observations")
    output = b"".join(canonical_bytes(event) + b"\n" for event in events)
    output_jsonl.parent.mkdir(parents=True, exist_ok=True)
    output_jsonl.write_bytes(output)
    return CSVImportResult(len(events), hashlib.sha256(original).hexdigest(),
                           hashlib.sha256(output).hexdigest(), volume_unit,
                           volume_unit == "SHARES")


def write_csv_import_manifest(path: Path, result: CSVImportResult, source: str) -> None:
    record = {
        "schema_version": "e5-csv-import-v1",
        "source": source,
        "source_sha256": result.source_sha256,
        "canonical_sha256": result.output_sha256,
        "volume_unit": result.volume_unit,
        "execution_eligible_by_volume_unit": result.execution_eligible,
        "data_provider_authenticity_verified": False,
        "corporate_actions_verified": False,
        "availability_timestamps_are_assumptions": True,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(record, sort_keys=True, separators=(",", ":")).encode())
