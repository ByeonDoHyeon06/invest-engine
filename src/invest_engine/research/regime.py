"""E6.4 causal, session-local market-regime research baseline.

Uses only finalized time bars actually received by the decision instant.
Thresholds are explicit hypotheses, not learned probabilities or live limits.
No allocation, broker, order, or risk-policy mutation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from enum import Enum

from invest_engine.data.calendar import StaticSessionCalendar
from invest_engine.domain.events import Bar, BarKind, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import InstrumentId, _decimal, utc_datetime
from invest_engine.research.report import sha256

D = Decimal


class Trend(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    RANGE = "RANGE"
    UNCERTAIN = "UNCERTAIN"


class Volatility(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class RegimePolicy:
    interval: timedelta = timedelta(minutes=1)
    lookback_returns: int = 20
    trend_return: Decimal = D("0.003")
    min_efficiency: Decimal = D("0.5")
    low_rms_return: Decimal = D("0.0005")
    high_rms_return: Decimal = D("0.003")
    version: str = "session-rms-efficiency-v1"

    def __post_init__(self) -> None:
        if (not isinstance(self.interval, timedelta) or self.interval <= timedelta(0)
                or type(self.lookback_returns) is not int or not 2 <= self.lookback_returns <= 10000
                or _decimal(self.trend_return, field="trend_return", positive=True) > 1
                or not 0 < _decimal(self.min_efficiency, field="min_efficiency") <= 1
                or not 0 <= _decimal(self.low_rms_return, field="low_rms_return")
                < _decimal(self.high_rms_return, field="high_rms_return", positive=True)
                or self.version != "session-rms-efficiency-v1"):
            raise ValueError("INVALID_REGIME_POLICY")

    @property
    def digest(self) -> str:
        return sha256(self)


@dataclass(frozen=True, slots=True)
class RegimeObservation:
    instrument: InstrumentId
    as_of: datetime
    policy_sha256: str
    trend: Trend
    volatility: Volatility
    net_return: Decimal | None
    efficiency: Decimal | None
    rms_return: Decimal | None
    source_event_ids: tuple[str, ...]
    source_sha256: str
    no_trade_hypothesis: bool
    reasons: tuple[str, ...]


def classify_regime(
    events: tuple[EventEnvelope[MarketPayload], ...],
    instrument: InstrumentId,
    calendar: StaticSessionCalendar,
    as_of: datetime,
    policy: RegimePolicy = RegimePolicy(),
) -> RegimeObservation:
    """Classify using an exact, contiguous, single-session trailing grid.

    A missing, late, flagged, duplicate, unfinalized or conflicting observation
    is not a zero return. Future receipts are ignored, even if their event
    timestamps are historical. Never compare overnight price gaps as intraday
    returns. Calendar and historical receipt provenance remain caller-supplied.
    """
    now = utc_datetime(as_of)
    if not isinstance(events, tuple):
        raise ValueError("REGIME_REQUIRES_IMMUTABLE_INPUT")
    def unknown(reason: str, ids: tuple[str, ...] = (),
                digest: str | None = None) -> RegimeObservation:
        return RegimeObservation(instrument, now, policy.digest, Trend.UNCERTAIN,
                                 Volatility.UNKNOWN, None, None, None, ids,
                                 digest if digest is not None else sha256(()), True, (reason,))

    session = calendar.session_for(instrument, now)
    if session is None:
        return unknown("OUTSIDE_SESSION")
    elapsed = (now-session.start) // policy.interval
    if elapsed < policy.lookback_returns+1:
        return unknown("INSUFFICIENT_SESSION_HISTORY")
    last_end = session.start+elapsed*policy.interval
    first_start = last_end-(policy.lookback_returns+1)*policy.interval
    expected = tuple(first_start+i*policy.interval for i in range(policy.lookback_returns+1))
    target = set(expected)
    known: dict[datetime, EventEnvelope[MarketPayload]] = {}
    seen: set[str] = set()
    for event in events:
        if (event.received_at > now or event.available_at > now
                or event.instrument_id is None or event.instrument_id.key != instrument.key
                or not isinstance(event.payload, Bar)):
            continue
        bar = event.payload
        # Other resolutions are separate series, not replacements for this grid.
        if bar.kind is not BarKind.TIME or bar.interval != policy.interval:
            continue
        if not (bar.start < last_end and bar.end > first_start):
            continue
        if (event.instrument_id != instrument or event.quality_flags
                or not bar.finalized or bar.start not in target
                or bar.end != bar.start+policy.interval or event.event_time != bar.end
                or event.available_at < bar.end or event.event_time > now):
            return unknown("INVALID_OR_FLAGGED_BAR")
        if bar.start in known or event.event_id in seen:
            return unknown("DUPLICATE_BAR_OR_EVENT")
        known[bar.start] = event
        seen.add(event.event_id)
    if set(known) != target:
        return unknown("MISSING_OR_LATE_BAR")
    ordered = tuple(known[t] for t in expected)
    ids = tuple(e.event_id for e in ordered)
    digest = sha256(ordered)
    if len({e.source for e in ordered}) != 1:
        return unknown("MIXED_SOURCE_HISTORY", ids, digest)
    closes = []
    for event in ordered:
        bar = event.payload
        assert isinstance(bar, Bar)
        if bar.volume <= 0:
            return unknown("ZERO_VOLUME_OBSERVATION", ids, digest)
        closes.append(bar.close)
    with localcontext() as ctx:
        ctx.prec = 64
        moves = tuple(b-a for a, b in zip(closes, closes[1:], strict=False))
        returns = tuple((b-a)/a for a, b in zip(closes, closes[1:], strict=False))
        net = (closes[-1]-closes[0])/closes[0]
        distance = sum((abs(x) for x in moves), D(0))
        efficiency = abs(closes[-1]-closes[0])/distance if distance else D(0)
        rms = (sum((x*x for x in returns), D(0))/len(returns)).sqrt()
        trend = (Trend.RANGE if abs(net) < policy.trend_return else
                 Trend.UNCERTAIN if efficiency < policy.min_efficiency else
                 Trend.UP if net > 0 else Trend.DOWN)
        volatility = (Volatility.LOW if rms <= policy.low_rms_return else
                      Volatility.HIGH if rms >= policy.high_rms_return else Volatility.NORMAL)
    # A conservative long-only research hypothesis, not an execution decision.
    reasons = tuple(reason for condition, reason in (
        (trend is Trend.UNCERTAIN, "DIRECTIONAL_EVIDENCE_CONFLICT"),
        (trend is Trend.DOWN, "LONG_ONLY_DOWNTREND_HYPOTHESIS"),
        (volatility is Volatility.HIGH, "HIGH_VOLATILITY_HYPOTHESIS"),
    ) if condition)
    return RegimeObservation(instrument, now, policy.digest, trend, volatility,
                             net, efficiency, rms, ids, digest, bool(reasons), reasons)
