"""Minimal deterministic event verifier. E2 will add the trading state reducer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Iterable

from invest_engine.core.clock import ReplayClock
from invest_engine.domain.errors import InvalidEvent, StaleData
from invest_engine.domain.events import EventEnvelope, MarketPayload
from invest_engine.domain.primitives import utc_datetime


def _canonical(value: object) -> Any:
    """Stable JSON form; no float coercion for Decimal and UTC time values."""
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        return utc_datetime(value).isoformat(timespec="microseconds")
    if isinstance(value, timedelta):
        return {"microseconds": (value.days * 86400 + value.seconds) * 1000000 + value.microseconds}
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {f.name: _canonical(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _canonical(v) for k, v in sorted(value.items())}
    if value is None or isinstance(value, (str, bool, int)):
        return value
    raise InvalidEvent(f"no canonical encoding for {type(value).__name__}")


def canonical_bytes(event: EventEnvelope[MarketPayload]) -> bytes:
    return json.dumps(
        _canonical(event), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def canonicalize_batch(
    events: Iterable[EventEnvelope[MarketPayload]],
) -> tuple[EventEnvelope[MarketPayload], ...]:
    """Batch ordering; do not use to reshuffle already persisted live journal events."""
    records = tuple(events)
    seen_ids: set[str] = set()
    ordinals: set[int] = set()
    for event in records:
        if event.event_id in seen_ids or event.ingest_ordinal in ordinals:
            raise InvalidEvent("duplicate event_id or ingest_ordinal")
        seen_ids.add(event.event_id)
        ordinals.add(event.ingest_ordinal)
    # Ordinals provide cross-source tie breaks; source_sequence is not globally comparable.
    return tuple(sorted(records, key=lambda e: (e.available_at, e.ingest_ordinal)))


@dataclass(frozen=True, slots=True)
class ReplaySummary:
    event_count: int
    state_hash: str
    last_available_at: datetime | None
    events_by_type: tuple[tuple[str, int], ...]


def replay_events(
    events: Iterable[EventEnvelope[MarketPayload]],
    *,
    run_version: str = "e0-replay-v1",
    as_of: datetime | None = None,
) -> ReplaySummary:
    """Hash/count a canonical event stream without simulating trades or orders.

    Replaying the same canonical events and run version yields the same state_hash.
    This is E0 infrastructure, NOT an E2 reducer or a backtesting engine.
    """
    if not run_version:
        raise ValueError("run_version cannot be empty")
    cutoff = utc_datetime(as_of, field="as_of") if as_of is not None else None
    records = canonicalize_batch(events)
    clock = ReplayClock(records[0].available_at if records else datetime(1970, 1, 1, tzinfo=timezone.utc))
    digest = hashlib.sha256(b"invest-engine:e0:" + run_version.encode("utf-8"))
    counts: dict[str, int] = {}
    for event in records:
        if cutoff is not None and event.available_at > cutoff:
            raise StaleData("event is not available at requested decision time")
        clock.advance_to(event.available_at)
        counts[event.event_type] = counts.get(event.event_type, 0) + 1
        payload = canonical_bytes(event)
        digest.update(len(payload).to_bytes(8, byteorder="big"))
        digest.update(payload)
    return ReplaySummary(
        event_count=len(records),
        state_hash=digest.hexdigest(),
        last_available_at=clock.now if records else None,
        events_by_type=tuple(sorted(counts.items())),
    )
