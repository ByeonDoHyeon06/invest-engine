"""Conservative, source-pinned delisting boundary for offline research.

A delisted security with outstanding shares needs a real terminal settlement,
which OHLCV bars cannot provide. Only zero-position/zero-order delistings may
pass this contract; no mark, liquidation or write-off is fabricated.
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
from invest_engine.trading.actions import DelistingObserved, DelistingCashResolved


@dataclass(frozen=True, slots=True)
class DelistingSchedule:
    delistings: tuple[DelistingObserved, ...] = ()
    resolutions: tuple[DelistingCashResolved, ...] = ()

    def __post_init__(self) -> None:
        keys = [a.action_id for a in self.delistings]
        symbols = [a.instrument.key for a in self.delistings]
        if len(keys) != len(set(keys)) or len(symbols) != len(set(symbols)):
            raise ValueError("DUPLICATE_OR_MULTIPLE_DELISTING")
        if tuple(sorted(self.delistings, key=lambda a: (a.effective_at, a.action_id))) != self.delistings:
            raise ValueError("DELISTING_SCHEDULE_NOT_SORTED")
        if any(a.available_at > a.effective_at for a in self.delistings):
            raise ValueError("DELISTING_TERMS_NOT_AVAILABLE_AT_EFFECTIVE_TIME")
        records = {a.action_id: a for a in self.delistings}
        ids = [r.action_id for r in self.resolutions]
        if len(ids) != len(set(ids)):
            raise ValueError("DUPLICATE_DELISTING_RESOLUTION")
        for resolution in self.resolutions:
            event = records.get(resolution.action_id)
            if event is None or event.instrument != resolution.instrument:
                raise ValueError("DELISTING_RESOLUTION_ACTION_MISMATCH")
            if (resolution.paid_at > event.effective_at or
                resolution.available_at > event.effective_at):
                raise ValueError("TERMINAL_SETTLEMENT_AFTER_LAST_BAR_REQUIRES_CASH_EVENT_REPLAY")

    def preflight(self, events: tuple[EventEnvelope[MarketPayload], ...]) -> None:
        for action in self.delistings:
            boundary = [e for e in events if e.instrument_id == action.instrument
                        and isinstance(e.payload, Bar) and e.payload.end == action.effective_at]
            if len(boundary) != 1:
                raise ValueError("DELISTING_REQUIRES_LAST_CONFIRMED_BAR_BOUNDARY")
            if any(e.instrument_id == action.instrument and
                   (e.payload.start >= action.effective_at
                    if isinstance(e.payload, Bar) else e.event_time >= action.effective_at)
                   for e in events):
                raise ValueError("MARKET_EVENTS_AFTER_DELISTING")
            if any(e.instrument_id == action.instrument and isinstance(e.payload, Bar)
                   and e.payload.start < action.effective_at < e.payload.end for e in events):
                raise ValueError("DELISTING_SPLITS_MARKET_BAR")


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not (value.endswith("Z") or value.endswith("+00:00")):
        raise ValueError("delisting timestamps must be explicit UTC")
    return utc_datetime(datetime.fromisoformat(value.replace("Z", "+00:00")))


def load_delistings(file: Path, expected_hash: str,
                     instruments: dict[str, InstrumentId]) -> DelistingSchedule:
    if (len(expected_hash) != 64 or
        any(character not in "0123456789abcdef" for character in expected_hash)):
        raise ValueError("invalid delisting SHA-256")
    raw = file.read_bytes()
    if not raw or len(raw) > 4_000_000 or sha256(raw).hexdigest() != expected_hash:
        raise ValueError("DELISTING_FILE_HASH_MISMATCH")
    result: list[DelistingObserved] = []
    resolutions: list[DelistingCashResolved] = []
    for line in raw.splitlines():
        if not line or len(line) > 100_000:
            raise ValueError("invalid delisting schedule line")
        row = json.loads(line)
        if not isinstance(row, dict):
            raise ValueError("invalid delisting schedule schema")
        data = cast(dict[str, Any], row)
        symbol = data.get("instrument_key")
        if data.get("kind") not in {"delisting", "cash_resolution"}:
            raise ValueError("invalid delisting schedule schema")
        required_fields = ({"kind", "action_id", "instrument_key", "effective_at",
                            "available_at", "source"} if data["kind"] == "delisting" else
                           {"kind", "action_id", "instrument_key", "quantity", "net_cash",
                            "paid_at", "available_at", "source", "evidence_sha256"})
        if set(data) != required_fields:
            raise ValueError("invalid delisting schedule schema")
        if not isinstance(symbol, str) or symbol not in instruments:
            raise ValueError("delisting instrument not present in historical dataset")
        if data.get("kind") == "delisting":
            required = {"kind", "action_id", "instrument_key", "effective_at",
                        "available_at", "source"}
            if set(data) != required:
                raise ValueError("invalid delisting schedule schema")
            result.append(DelistingObserved(data["action_id"], instruments[symbol],
                                          _utc(data["effective_at"]),
                                          _utc(data["available_at"]), data["source"]))
        elif data.get("kind") == "cash_resolution":
            required = {"kind", "action_id", "instrument_key", "quantity", "net_cash",
                        "paid_at", "available_at", "source", "evidence_sha256"}
            if set(data) != required or not isinstance(data["quantity"], str) or not isinstance(data["net_cash"], str):
                raise ValueError("invalid terminal settlement schema")
            from decimal import Decimal
            resolutions.append(DelistingCashResolved(
                data["action_id"], instruments[symbol], Decimal(data["quantity"]),
                Decimal(data["net_cash"]), _utc(data["paid_at"]),
                _utc(data["available_at"]), data["source"], data["evidence_sha256"],
            ))
        else:
            raise ValueError("invalid delisting schedule schema")
    return DelistingSchedule(tuple(result), tuple(resolutions))
