"""Explicit, SHA-pinned session-open share split replay for offline research.

This *does not* certify a provider's issuer records, price adjustment policy,
or their historical availability. No dividends/delistings/mergers are inferred.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import InstrumentId, utc_datetime
from invest_engine.trading.actions import SplitApplied


@dataclass(frozen=True, slots=True)
class SplitSchedule:
    splits: tuple[SplitApplied, ...] = ()

    def __post_init__(self) -> None:
        ids = [split.action_id for split in self.splits]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicated split schedule IDs")
        if tuple(sorted(self.splits, key=lambda x: (x.effective_at, x.action_id))) != self.splits:
            raise ValueError("split schedule must be ordered by effective date and ID")

    def preflight(self, events: tuple[EventEnvelope[MarketPayload], ...]) -> None:
        """Splits must coincide with an explicit bar-open boundary, with known terms."""
        for split in self.splits:
            if split.available_at > split.effective_at:
                raise ValueError("SPLIT_TERMS_UNAVAILABLE_BEFORE_EFFECTIVE_TIME")
            on_boundary = [e for e in events if e.instrument_id == split.instrument
                           and isinstance(e.payload, Bar)
                           and e.payload.start == split.effective_at]
            if len(on_boundary) != 1:
                raise ValueError("SPLIT_MUST_START_AT_OBSERVED_BAR_BOUNDARY")
            if any(e.instrument_id == split.instrument and isinstance(e.payload, Bar)
                   and e.payload.start < split.effective_at < e.payload.end for e in events):
                raise ValueError("SPLIT_BAR_STRADDLES_EFFECTIVE_TIME")


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not (value.endswith("Z") or value.endswith("+00:00")):
        raise ValueError("split datetime must be explicit UTC RFC3339")
    return utc_datetime(datetime.fromisoformat(value.replace("Z", "+00:00")))


def load_splits(path: Path, checksum: str, instruments: dict[str, InstrumentId]) -> SplitSchedule:
    """Strict immutable split terms; caller must independently attest data provenance."""
    if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
        raise ValueError("split checksum must be lowercase SHA256")
    raw = path.read_bytes()
    if not raw or len(raw) > 4_000_000 or sha256(raw).hexdigest() != checksum:
        raise ValueError("split schedule file hash mismatch or size limit")
    rows: list[SplitApplied] = []
    for line in raw.splitlines():
        if not line or len(line) > 100_000:
            raise ValueError("invalid split schedule line")
        item = json.loads(line)
        keys = {"kind", "action_id", "instrument_key", "numerator", "denominator",
                "effective_at", "available_at", "source"}
        if not isinstance(item, dict) or set(item) != keys or item["kind"] != "split":
            raise ValueError("invalid split schedule schema")
        p = cast(dict[str, Any], item)
        key = p["instrument_key"]
        if not isinstance(key, str) or key not in instruments:
            raise ValueError("split instrument missing from dataset")
        rows.append(SplitApplied(
            p["action_id"], instruments[key], p["numerator"], p["denominator"],
            _utc(p["effective_at"]), _utc(p["available_at"]), p["source"],
        ))
    return SplitSchedule(tuple(rows))
