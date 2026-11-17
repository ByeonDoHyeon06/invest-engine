"""Explicit, causal FX marks for *reporting*, never synthetic buying power.

A quote USD/KRW at 1300 means one USD is valued as 1300 KRW. We accept
only exact direct pairs: no reciprocal, triangulation, interpolation or
forward-fill beyond a declared maximum age. Neither source nor license is
validated merely because it is declared.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, localcontext

from invest_engine.domain.primitives import _currency, _decimal, utc_datetime
from invest_engine.research.report import EquityPoint, sha256


@dataclass(frozen=True, slots=True)
class FxObservation:
    observation_id: str
    base: str
    quote: str
    rate: Decimal
    event_time: datetime
    available_at: datetime
    received_at: datetime
    source: str

    def __post_init__(self) -> None:
        if not self.observation_id.strip() or not self.source.strip():
            raise ValueError("FX identity and provenance are required")
        _currency(self.base)
        _currency(self.quote)
        if self.base == self.quote:
            raise ValueError("FX observation must be a cross-currency pair")
        _decimal(self.rate, field="fx.rate", positive=True)
        for key in ("event_time", "available_at", "received_at"):
            object.__setattr__(self, key, utc_datetime(getattr(self, key)))
        if not (self.event_time <= self.available_at <= self.received_at):
            raise ValueError("FX quote cannot be observed before its effective/release time")


@dataclass(frozen=True, slots=True)
class FxReportingPolicy:
    base_currency: str
    max_age: timedelta

    def __post_init__(self) -> None:
        _currency(self.base_currency)
        if self.max_age < timedelta(0):
            raise ValueError("FX maximum observation age must be nonnegative")


@dataclass(frozen=True, slots=True)
class FxEquityPoint:
    at: datetime
    currency: str
    value: Decimal | None
    complete: bool
    source_observation_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()


class FxSeries:
    """As-of-only FX observations with an immutable, content-hashed identity."""

    def __init__(self, observations: tuple[FxObservation, ...]) -> None:
        if len({row.observation_id for row in observations}) != len(observations):
            raise ValueError("duplicate FX observation id")
        order = tuple(sorted(
            observations, key=lambda row: (row.received_at, row.observation_id),
        ))
        if observations != order:
            raise ValueError("FX input must be ordered by received time and ID")
        self.observations = observations
        self.digest = sha256(observations)

    def direct_as_of(
        self, currency: str, quote: str, now: datetime, max_age: timedelta,
    ) -> FxObservation | None:
        """Return the latest *known* quote, never a future or stale observation."""
        now = utc_datetime(now)
        match: FxObservation | None = None
        for item in self.observations:
            if item.base != currency or item.quote != quote:
                continue
            if item.received_at > now or item.available_at > now or item.event_time > now:
                continue
            # A newly received historical correction is not a fresh market quote.
            if now - item.event_time > max_age or now - item.received_at > max_age:
                continue
            if match is None or (item.received_at, item.observation_id) > (
                match.received_at, match.observation_id,
            ):
                match = item
        return match

    def value_at(
        self, point: EquityPoint, policy: FxReportingPolicy,
    ) -> FxEquityPoint:
        if not point.complete:
            return FxEquityPoint(point.at, policy.base_currency, None, False,
                                 reason_codes=("MARKET_VALUATION_INCOMPLETE",))
        sources: list[str] = []
        missing: list[str] = []
        with localcontext() as ctx:
            ctx.prec = 64
            total = Decimal(0)
            for currency, amount in point.by_currency:
                if amount == 0:
                    continue
                if currency == policy.base_currency:
                    total += amount
                    continue
                obs = self.direct_as_of(currency, policy.base_currency,
                                        point.at, policy.max_age)
                if obs is None:
                    missing.append(currency)
                else:
                    total += amount * obs.rate
                    sources.append(obs.observation_id)
        if missing:
            return FxEquityPoint(point.at, policy.base_currency, None, False,
                                 tuple(sorted(sources)),
                                 tuple("FX_MISSING_OR_STALE:" + curr for curr in sorted(missing)))
        return FxEquityPoint(point.at, policy.base_currency, total, True,
                             tuple(sorted(sources)))


def base_drawdown(points: tuple[FxEquityPoint, ...]) -> Decimal | None:
    """Never understate drawdown using a partial FX-adjusted equity curve."""
    if not points or any(not p.complete or p.value is None for p in points):
        return None
    peak: Decimal | None = None
    worst = Decimal(0)
    for item in points:
        assert item.value is not None
        peak = item.value if peak is None else max(peak, item.value)
        if peak > 0:
            worst = max(worst, (peak - item.value) / peak)
    return worst
