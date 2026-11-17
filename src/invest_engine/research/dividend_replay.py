"""Explicit offline dividend entitlement/payment schedule with pinned raw data.

The schedule is a research hypothesis supplied by the operator. It neither
verifies actual issuer entitlement dates nor invents broker cash settlements.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import InstrumentId, utc_datetime
from invest_engine.trading.actions import DividendEntitled


@dataclass(frozen=True, slots=True)
class DividendPayment:
    action_id: str
    instrument: InstrumentId
    paid_at: datetime
    available_at: datetime
    source: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "paid_at", utc_datetime(self.paid_at))
        object.__setattr__(self, "available_at", utc_datetime(self.available_at))
        if not self.action_id.strip() or not self.source.strip():
            raise ValueError("dividend payment requires identity and provenance")
        if self.available_at > self.paid_at:
            raise ValueError("DIVIDEND_PAYMENT_NOT_KNOWN_AT_EFFECTIVE_TIME")


@dataclass(frozen=True, slots=True)
class DividendSchedule:
    entitlements: tuple[DividendEntitled, ...] = ()
    payments: tuple[DividendPayment, ...] = ()

    def __post_init__(self) -> None:
        ids = [d.action_id for d in self.entitlements]
        paid = [p.action_id for p in self.payments]
        if len(ids) != len(set(ids)) or len(paid) != len(set(paid)) or set(ids) != set(paid):
            raise ValueError("dividend schedule needs one distinct payment per entitlement")
        if self.entitlements != tuple(sorted(
            self.entitlements, key=lambda d: (d.effective_at, d.action_id),
        )) or self.payments != tuple(sorted(
            self.payments, key=lambda p: (p.paid_at, p.action_id),
        )):
            raise ValueError("dividend schedule must have deterministic date order")
        by_id = {p.action_id: p for p in self.payments}
        for entitled in self.entitlements:
            payment = by_id[entitled.action_id]
            if (payment.instrument != entitled.instrument or payment.source != entitled.source
                or payment.paid_at <= entitled.effective_at):
                raise ValueError("payment must follow its matching entitlement")
            if entitled.available_at > entitled.effective_at:
                raise ValueError("DIVIDEND_TERMS_NOT_AVAILABLE_BEFORE_ENTITLEMENT")

    def preflight(self, events: tuple[EventEnvelope[MarketPayload], ...]) -> None:
        """Require observable entitlement/payable boundaries; no synthetic bars."""
        if not events and self.entitlements:
            raise ValueError("historical market events required for dividends")
        for entitled in self.entitlements:
            boundaries = [e for e in events if e.instrument_id == entitled.instrument
                          and isinstance(e.payload, Bar)
                          and e.payload.start == entitled.effective_at]
            if len(boundaries) != 1:
                raise ValueError("DIVIDEND_ENTITLEMENT_REQUIRES_OBSERVED_BAR")
        for payment in self.payments:
            # A payment after the backtest horizon is a genuine receivable,
            # but within the horizon it must have a witnessed market boundary.
            latest = max((e.payload.end for e in events
                          if e.instrument_id == payment.instrument
                          and isinstance(e.payload, Bar)), default=None)
            if latest is not None and payment.paid_at < latest:
                observed = [e for e in events if e.instrument_id == payment.instrument
                            and isinstance(e.payload, Bar)
                            and e.payload.start == payment.paid_at]
                if len(observed) != 1:
                    raise ValueError("DIVIDEND_PAYMENT_REQUIRES_OBSERVED_BAR")
        ex_times = {(x.instrument.key, x.effective_at) for x in self.entitlements}
        if len(ex_times) != len(self.entitlements):
            raise ValueError("simultaneous dividends for one instrument unsupported")


def _utc(value: object) -> datetime:
    if not isinstance(value, str) or not (value.endswith("Z") or value.endswith("+00:00")):
        raise ValueError("dividend timestamps must be explicit UTC RFC3339")
    return utc_datetime(datetime.fromisoformat(value.replace("Z", "+00:00")))


def load_dividends(path: Path, checksum: str,
                   instruments: dict[str, InstrumentId]) -> DividendSchedule:
    if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
        raise ValueError("dividend checksum must be lowercase SHA256")
    data = path.read_bytes()
    if not data or len(data) > 4_000_000 or sha256(data).hexdigest() != checksum:
        raise ValueError("dividend schedule file hash mismatch or size limit")
    entitled: list[DividendEntitled] = []
    payments: list[DividendPayment] = []
    for line in data.splitlines():
        if not line or len(line) > 100_000:
            raise ValueError("invalid dividend schedule line")
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError("invalid dividend schedule record")
        value = cast(dict[str, Any], item)
        kind = value.get("kind")
        fields = ({"kind", "action_id", "instrument_key", "gross_per_share",
                   "withholding_fraction", "effective_at", "available_at", "source"}
                  if kind == "entitlement" else
                  {"kind", "action_id", "instrument_key", "paid_at", "available_at", "source"}
                  if kind == "payment" else set())
        if not fields or set(value) != fields:
            raise ValueError("invalid dividend schedule record fields")
        key = value["instrument_key"]
        if not isinstance(key, str) or key not in instruments:
            raise ValueError("dividend instrument missing from dataset")
        if kind == "entitlement":
            for name in ("gross_per_share", "withholding_fraction"):
                if not isinstance(value[name], str):
                    raise ValueError("dividend monetary inputs must be decimal strings")
            entitled.append(DividendEntitled(
                value["action_id"], instruments[key], Decimal(value["gross_per_share"]),
                Decimal(value["withholding_fraction"]), _utc(value["effective_at"]),
                _utc(value["available_at"]), value["source"],
            ))
        else:
            payments.append(DividendPayment(
                value["action_id"], instruments[key], _utc(value["paid_at"]),
                _utc(value["available_at"]), value["source"],
            ))
    return DividendSchedule(tuple(entitled), tuple(payments))
