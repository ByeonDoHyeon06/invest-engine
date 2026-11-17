"""Fail-closed, *declared* point-in-time research metadata validation.

Metadata is supplied by the caller. Passing this gate proves structural/as-of
consistency, NOT provider authenticity, historical completeness or market rights.
Unmodeled issuer actions abort the entire experiment rather than quietly
excluding a survivor-biased subset of instruments.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256 as hash256
from pathlib import Path
from typing import Any, cast

from invest_engine.core.replay import canonical_bytes
from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import utc_datetime
from invest_engine.research.report import sha256
from invest_engine.trading.actions import DividendEntitled, SplitApplied


@dataclass(frozen=True, slots=True)
class UniverseMembership:
    instrument_key: str
    effective_from: datetime
    effective_until: datetime
    published_at: datetime
    received_at: datetime
    source: str
    included: bool

    def __post_init__(self) -> None:
        _times(self, ("effective_from", "effective_until", "published_at", "received_at"))
        if self.effective_from >= self.effective_until:
            raise ValueError("universe membership interval must be positive")
        if self.published_at > self.received_at:
            raise ValueError("universe membership published after receipt")
        if not self.instrument_key.strip() or not self.source.strip() or not isinstance(self.included, bool):
            raise ValueError("invalid universe provenance or inclusion")


@dataclass(frozen=True, slots=True)
class MarketVintage:
    event_id: str
    payload_sha256: str
    revision: str
    published_at: datetime
    received_at: datetime
    source: str

    def __post_init__(self) -> None:
        _times(self, ("published_at", "received_at"))
        if self.published_at > self.received_at:
            raise ValueError("market vintage published after receipt")
        if not all((self.event_id.strip(), self.revision.strip(), self.source.strip())):
            raise ValueError("market vintage identity and provenance required")
        _hash(self.payload_sha256)


@dataclass(frozen=True, slots=True)
class CorporateAction:
    action_id: str
    instrument_key: str
    action_type: str
    effective_at: datetime
    published_at: datetime
    received_at: datetime
    source: str

    def __post_init__(self) -> None:
        _times(self, ("effective_at", "published_at", "received_at"))
        if self.published_at > self.received_at:
            raise ValueError("corporate action published after receipt")
        if self.action_type not in {"SPLIT", "CASH_DIVIDEND", "DELIST", "MERGER", "SYMBOL_CHANGE"}:
            raise ValueError("unknown corporate action type")
        if not all((self.action_id.strip(), self.instrument_key.strip(), self.source.strip())):
            raise ValueError("corporate action identity and source required")


@dataclass(frozen=True, slots=True)
class CorporateActionCoverage:
    instrument_key: str
    start: datetime
    end: datetime
    published_at: datetime
    received_at: datetime
    source: str

    def __post_init__(self) -> None:
        _times(self, ("start", "end", "published_at", "received_at"))
        if self.start >= self.end or self.published_at > self.received_at:
            raise ValueError("invalid action coverage interval or availability")
        if not self.instrument_key.strip() or not self.source.strip():
            raise ValueError("corporate action coverage provenance required")


def _times(instance: object, names: tuple[str, ...]) -> None:
    for name in names:
        object.__setattr__(instance, name, utc_datetime(getattr(instance, name)))


def _hash(value: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("expected lowercase SHA-256 hash")


@dataclass(frozen=True, slots=True)
class PITEvidence:
    memberships: tuple[UniverseMembership, ...]
    vintages: tuple[MarketVintage, ...]
    actions: tuple[CorporateAction, ...]
    action_coverages: tuple[CorporateActionCoverage, ...]

    def __post_init__(self) -> None:
        for title, keys in (
            ("market vintage", [r.event_id for r in self.vintages]),
            ("corporate action", [r.action_id for r in self.actions]),
        ):
            if len(keys) != len(set(keys)):
                raise ValueError(f"duplicate {title} identifiers")
        # Multiple overlapping *known* membership records can select a winner
        # only with additional provider semantics; refuse ambiguity instead.
        for i, a in enumerate(self.memberships):
            for b in self.memberships[i + 1:]:
                if (a.instrument_key == b.instrument_key and
                    a.effective_from < b.effective_until and b.effective_from < a.effective_until):
                    raise ValueError("overlapping universe membership windows")
        for i, coverage in enumerate(self.action_coverages):
            for other_coverage in self.action_coverages[i + 1:]:
                if (coverage.instrument_key == other_coverage.instrument_key and
                    coverage.start < other_coverage.end and
                    other_coverage.start < coverage.end):
                    raise ValueError("overlapping action coverage declarations")

    @property
    def digest(self) -> str:
        return sha256(self)


@dataclass(frozen=True, slots=True)
class PITGateResult:
    event_count: int
    instrument_count: int
    evidence_sha256: str
    data_release_verified: bool = False
    reason_codes: tuple[str, ...] = (
        "EXTERNAL_SOURCE_AND_CORPORATE_ACTION_COMPLETENESS_UNVERIFIED",
        "PRICE_ADJUSTMENT_NOT_IMPLEMENTED",
    )


def validate_pit_events(
    events: tuple[EventEnvelope[MarketPayload], ...], evidence: PITEvidence,
    *, modeled_splits: tuple[SplitApplied, ...] = (),
    modeled_dividends: tuple[DividendEntitled, ...] = (),
) -> PITGateResult:
    """Reject retroactive universes/revisions and ANY in-window issuer action.

    This is a research gate. It never removes a delisted instrument to improve
    a backtest and never applies guessed split/dividend adjustments.
    """
    if not events:
        raise ValueError("PIT gate requires historical events")
    modeled_ids = {a.action_id: a for a in modeled_splits}
    if len(modeled_ids) != len(modeled_splits):
        raise ValueError("duplicate modeled split IDs")
    dividend_ids = {a.action_id: a for a in modeled_dividends}
    if len(dividend_ids) != len(modeled_dividends) or set(modeled_ids) & set(dividend_ids):
        raise ValueError("duplicate modeled corporate action IDs")
    matched: set[str] = set()
    seen: set[str] = set()
    bounds: dict[str, tuple[datetime, datetime]] = {}
    vintages = {row.event_id: row for row in evidence.vintages}
    for event in events:
        inst = event.instrument_id
        if inst is None:
            raise ValueError("PIT gate requires instrument for every market event")
        if event.event_id in seen:
            raise ValueError("duplicate market event in PIT gate")
        seen.add(event.event_id)
        now = max(event.available_at, event.received_at)
        membership = [r for r in evidence.memberships if r.instrument_key == inst.key
                      and r.effective_from <= event.event_time < r.effective_until
                      and r.published_at <= now and r.received_at <= now]
        if len(membership) != 1 or not membership[0].included:
            raise ValueError(f"PIT_UNIVERSE_NOT_ELIGIBLE:{event.event_id}")
        vintage = vintages.get(event.event_id)
        if (vintage is None or vintage.payload_sha256 != hash256(canonical_bytes(event)).hexdigest()
            or vintage.published_at > event.available_at
            or vintage.received_at > event.received_at):
            raise ValueError(f"PIT_VINTAGE_MISSING_FUTURE_OR_MISMATCH:{event.event_id}")
        beginning = event.payload.start if isinstance(event.payload, Bar) else event.event_time
        ending = event.payload.end if isinstance(event.payload, Bar) else event.event_time
        prev = bounds.get(inst.key)
        bounds[inst.key] = (
            min(prev[0], beginning) if prev else beginning,
            max(prev[1], ending) if prev else ending,
        )
    if set(vintages) != seen:
        raise ValueError("PIT_VINTAGE_HAS_UNKNOWN_EVENTS")
    for key, (beginning, end) in bounds.items():
        covers = [r for r in evidence.action_coverages if r.instrument_key == key
                  and r.start <= beginning and r.end >= end
                  and r.published_at <= beginning and r.received_at <= beginning]
        if len(covers) != 1:
            raise ValueError(f"PIT_ACTION_COVERAGE_UNVERIFIED:{key}")
        for action in evidence.actions:
            if action.instrument_key != key or not beginning <= action.effective_at <= end:
                continue
            split = modeled_ids.get(action.action_id)
            dividend = dividend_ids.get(action.action_id)
            split_match = (
                action.action_type == "SPLIT" and split is not None
                and split.instrument.key == key and split.effective_at == action.effective_at
                and split.available_at == action.received_at and split.source == action.source
            )
            dividend_match = (
                action.action_type == "CASH_DIVIDEND" and dividend is not None
                and dividend.instrument.key == key and dividend.effective_at == action.effective_at
                and dividend.available_at == action.received_at and dividend.source == action.source
            )
            if (not (split_match or dividend_match)
                or action.published_at > action.received_at
                or action.received_at > action.effective_at):
                raise ValueError(f"UNMODELED_CORPORATE_ACTION:{key}")
            matched.add(action.action_id)
    if matched != (set(modeled_ids) | set(dividend_ids)):
        raise ValueError("ACTION_SCHEDULE_HAS_UNDECLARED_OR_OUT_OF_RANGE_ACTIONS")
    return PITGateResult(
        len(events), len(bounds), evidence.digest, reason_codes=(
            "EXTERNAL_SOURCE_AND_CORPORATE_ACTION_COMPLETENESS_UNVERIFIED",
            "RAW_UNADJUSTED_SPLIT_PRICE_CONVENTION_ASSUMED",
        ) if modeled_splits and not modeled_dividends else (
            "EXTERNAL_SOURCE_AND_CORPORATE_ACTION_COMPLETENESS_UNVERIFIED",
            "DIVIDEND_ENTITLEMENT_AND_PAYMENT_SYNTHETIC" if modeled_dividends else
            "PRICE_ADJUSTMENT_NOT_IMPLEMENTED",
            "RAW_UNADJUSTED_SPLIT_PRICE_CONVENTION_ASSUMED" if modeled_splits else
            "NO_SPLIT_REPLAY",
        ),
    )


def _object(value: object, keys: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("invalid PIT evidence record fields")
    return cast(dict[str, Any], value)


def _utc(raw: object) -> datetime:
    if not isinstance(raw, str) or not (raw.endswith("Z") or raw.endswith("+00:00")):
        raise ValueError("PIT evidence times require UTC RFC3339 strings")
    return utc_datetime(datetime.fromisoformat(raw.replace("Z", "+00:00")))


def load_pit_evidence(file: Path, expected_sha256: str) -> tuple[PITEvidence, str]:
    """Strict, SHA-pinned JSONL with four typed, explicit record kinds."""
    _hash(expected_sha256)
    if not file.is_file():
        raise ValueError("PIT evidence file missing")
    raw = file.read_bytes()
    digest = hash256(raw).hexdigest()
    if digest != expected_sha256:
        raise ValueError("PIT evidence file hash mismatch")
    if len(raw) > 40_000_000 or not raw:
        raise ValueError("PIT evidence too large or empty")
    memberships: list[UniverseMembership] = []
    vintages: list[MarketVintage] = []
    actions: list[CorporateAction] = []
    covers: list[CorporateActionCoverage] = []
    for line in raw.splitlines():
        if not line or len(line) > 1_000_000:
            raise ValueError("PIT evidence contains empty or oversized record")
        item = json.loads(line)
        if not isinstance(item, dict):
            raise ValueError("PIT record must be object")
        kind = item.get("kind")
        if kind == "membership":
            p = _object(item, {"kind", "instrument_key", "effective_from", "effective_until",
                               "published_at", "received_at", "source", "included"})
            memberships.append(UniverseMembership(
                p["instrument_key"], _utc(p["effective_from"]), _utc(p["effective_until"]),
                _utc(p["published_at"]), _utc(p["received_at"]), p["source"], p["included"],
            ))
        elif kind == "vintage":
            p = _object(item, {"kind", "event_id", "payload_sha256", "revision",
                               "published_at", "received_at", "source"})
            vintages.append(MarketVintage(p["event_id"], p["payload_sha256"],
                                          p["revision"], _utc(p["published_at"]),
                                          _utc(p["received_at"]), p["source"]))
        elif kind == "corporate_action":
            p = _object(item, {"kind", "action_id", "instrument_key", "action_type",
                               "effective_at", "published_at", "received_at", "source"})
            actions.append(CorporateAction(p["action_id"], p["instrument_key"],
                                           p["action_type"], _utc(p["effective_at"]),
                                           _utc(p["published_at"]), _utc(p["received_at"]),
                                           p["source"]))
        elif kind == "action_coverage":
            p = _object(item, {"kind", "instrument_key", "start", "end",
                               "published_at", "received_at", "source"})
            covers.append(CorporateActionCoverage(
                p["instrument_key"], _utc(p["start"]), _utc(p["end"]),
                _utc(p["published_at"]), _utc(p["received_at"]), p["source"],
            ))
        else:
            raise ValueError("unknown PIT evidence record kind")
    return PITEvidence(tuple(memberships), tuple(vintages), tuple(actions), tuple(covers)), digest
