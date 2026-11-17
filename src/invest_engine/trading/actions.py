"""Versioned, synthetic corporate-action instructions for E5.7 portfolio research.

These are not a proof of issuer actions, entitlement or settlement dates.  A
caller must provide point-in-time evidence independently of these contracts.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json

from invest_engine.core.replay import _canonical
from datetime import datetime
from decimal import Decimal

from invest_engine.domain.primitives import InstrumentId, _decimal, utc_datetime


def _identity(action_id: str, instrument: InstrumentId, effective_at: datetime,
              available_at: datetime, source: str) -> tuple[datetime, datetime]:
    if not all(isinstance(v, str) and v.strip() for v in (action_id, source)):
        raise ValueError("corporate-action identity/source required")
    if not isinstance(instrument, InstrumentId):
        raise ValueError("corporate-action instrument required")
    effective = utc_datetime(effective_at)
    available = utc_datetime(available_at)
    return effective, available


@dataclass(frozen=True, slots=True)
class SplitApplied:
    action_id: str
    instrument: InstrumentId
    numerator: int
    denominator: int
    effective_at: datetime
    available_at: datetime
    source: str

    def __post_init__(self) -> None:
        effective, available = _identity(self.action_id, self.instrument, self.effective_at,
                                         self.available_at, self.source)
        if (type(self.numerator) is not int or type(self.denominator) is not int
                or self.numerator <= 0 or self.denominator <= 0
                or self.numerator == self.denominator):
            raise ValueError("nontrivial positive split ratio required")
        object.__setattr__(self, "effective_at", effective)
        object.__setattr__(self, "available_at", available)


@dataclass(frozen=True, slots=True)
class DividendEntitled:
    action_id: str
    instrument: InstrumentId
    gross_per_share: Decimal
    withholding_fraction: Decimal
    effective_at: datetime
    available_at: datetime
    source: str

    def __post_init__(self) -> None:
        effective, available = _identity(self.action_id, self.instrument, self.effective_at,
                                         self.available_at, self.source)
        _decimal(self.gross_per_share, field="dividend.gross_per_share")
        _decimal(self.withholding_fraction, field="dividend.withholding_fraction")
        if self.gross_per_share < 0 or not (0 <= self.withholding_fraction < 1):
            raise ValueError("invalid synthetic dividend/withholding")
        object.__setattr__(self, "effective_at", effective)
        object.__setattr__(self, "available_at", available)


@dataclass(frozen=True, slots=True)
class DividendPaymentConfirmed:
    action_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.action_id, str) or not self.action_id.strip():
            raise ValueError("dividend action ID required")


@dataclass(frozen=True, slots=True)
class DelistingObserved:
    action_id: str
    instrument: InstrumentId
    effective_at: datetime
    available_at: datetime
    source: str

    def __post_init__(self) -> None:
        effective, available = _identity(self.action_id, self.instrument, self.effective_at,
                                         self.available_at, self.source)
        object.__setattr__(self, "effective_at", effective)
        object.__setattr__(self, "available_at", available)


@dataclass(frozen=True, slots=True)
class DelistingCashResolved:
    """Explicitly evidenced NET cash receipt, never a synthetic market fill.

    E5.11's historical runner only permits receipts proven available and paid
    by the terminal historical bar. Later settlements require a separate
    chronological cash-event replay (not yet supported).
    """
    action_id: str
    instrument: InstrumentId
    quantity: Decimal
    net_cash: Decimal
    paid_at: datetime
    available_at: datetime
    source: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, InstrumentId):
            raise ValueError("settlement instrument required")
        if not isinstance(self.action_id, str) or not self.action_id.strip():
            raise ValueError("settlement action identity required")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("settlement provenance required")
        _decimal(self.quantity, field="resolution.quantity", positive=True)
        _decimal(self.net_cash, field="resolution.net_cash")
        if self.net_cash < 0:
            raise ValueError("delisting payout cannot be negative")
        if (not isinstance(self.evidence_sha256, str) or len(self.evidence_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.evidence_sha256)):
            raise ValueError("resolution requires SHA-256 receipt fingerprint")
        object.__setattr__(self, "paid_at", utc_datetime(self.paid_at))
        object.__setattr__(self, "available_at", utc_datetime(self.available_at))


@dataclass(frozen=True, slots=True)
class DelistingResolutionRecord:
    action_id: str
    instrument_key: str
    currency: str
    quantity: Decimal
    net_cash: Decimal
    realized_pnl: Decimal
    evidence_sha256: str
    terms_sha256: str


@dataclass(frozen=True, slots=True)
class PositionAdjustment:
    action_id: str
    instrument_key: str
    quantity_delta: Decimal


@dataclass(frozen=True, slots=True)
class DividendReceivable:
    action_id: str
    currency: str
    entitled_quantity: Decimal
    gross: Decimal
    withheld: Decimal
    net: Decimal
    recorded_at: datetime


def action_fingerprint(
    action: SplitApplied | DividendEntitled | DelistingObserved | DelistingCashResolved,
) -> str:
    """Bind an action ID to immutable terms; prevents silently changing history."""
    encoded = json.dumps(_canonical(action), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
