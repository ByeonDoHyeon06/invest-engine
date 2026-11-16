"""Strict, broker-free strategy plugin contracts (E4)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from invest_engine.features.registry import FeatureDefinition, FeatureValue

from invest_engine.data.calendar import TradingSession
from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import InstrumentId, Market, _decimal, utc_datetime


class SignalDirection(str, Enum):
    LONG = "LONG"
    EXIT = "EXIT"


@dataclass(frozen=True, slots=True)
class DataRequirement:
    event_type: str
    interval: timedelta | None = None
    warmup: int = 1
    max_age: timedelta | None = None

    def __post_init__(self) -> None:
        if not self.event_type.startswith("market."):
            raise ValueError("strategy requirements must be market event types")
        if self.event_type == "market.bar":
            if self.interval is None or self.interval <= timedelta(0):
                raise ValueError("bar requirement needs a positive interval")
        elif self.interval is not None:
            raise ValueError("only market.bar can specify interval")
        if self.warmup < 1:
            raise ValueError("warmup must be >= 1")
        if self.max_age is not None and self.max_age < timedelta(0):
            raise ValueError("max_age must not be negative")


@dataclass(frozen=True, slots=True)
class StrategyManifest:
    strategy_id: str
    version: str
    markets: frozenset[Market]
    requirements: tuple[DataRequirement, ...]
    features: tuple[FeatureDefinition, ...] = ()

    def __post_init__(self) -> None:
        if not self.strategy_id.strip() or not self.version.strip():
            raise ValueError("strategy id and version are required")
        if not self.markets or any(not isinstance(m, Market) for m in self.markets):
            raise ValueError("supported markets are required")
        if not self.requirements:
            raise ValueError("strategy must declare data requirements")
        keys = [(req.event_type, req.interval) for req in self.requirements]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate data requirement")
        names = [f.name for f in self.features]
        if len(names) != len(set(names)):
            raise ValueError("duplicate feature name")


@dataclass(frozen=True, slots=True)
class BarObservation:
    event_id: str
    instrument: InstrumentId
    bar: Bar
    known_at: datetime
    session: TradingSession

    def __post_init__(self) -> None:
        object.__setattr__(self, "known_at", utc_datetime(self.known_at))
        if self.bar.end > self.known_at:
            raise ValueError("bar cannot be known before completion")
        if self.instrument.market != self.session.market or self.instrument.venue != self.session.venue:
            raise ValueError("bar session does not match instrument")
        if not (self.session.start <= self.bar.start < self.bar.end <= self.session.end):
            raise ValueError("bar must fit fully inside market session")


@dataclass(frozen=True, slots=True)
class StrategyContext:
    """Pure immutable view. No TradingRuntime, broker, or write-capable account object."""

    as_of: datetime
    event: EventEnvelope[MarketPayload]
    bars: tuple[BarObservation, ...]
    session: TradingSession | None
    features: tuple[FeatureValue, ...] = ()

    def __post_init__(self) -> None:
        instant = utc_datetime(self.as_of)
        object.__setattr__(self, "as_of", instant)
        if any(b.known_at > instant for b in self.bars):
            raise ValueError("future feature observations in context")

    def feature(self, name: str) -> Decimal | None:
        return next((f.value for f in self.features if f.name == name), None)

    def bars_for(self, instrument: InstrumentId, interval: timedelta) -> tuple[BarObservation, ...]:
        return tuple(
            b for b in self.bars
            if b.instrument.key == instrument.key and b.bar.interval == interval
        )


@dataclass(frozen=True, slots=True)
class StrategySignal:
    signal_id: str
    strategy_id: str
    strategy_version: str
    instrument: InstrumentId
    direction: SignalDirection
    target_fraction: Decimal
    generated_at: datetime
    expires_at: datetime
    trigger_event_id: str
    stop_price: Decimal | None = None
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not all((self.signal_id.strip(), self.strategy_id.strip(), self.strategy_version.strip(), self.trigger_event_id.strip())):
            raise ValueError("signal identity fields required")
        if not isinstance(self.direction, SignalDirection):
            raise ValueError("invalid signal direction")
        fraction = _decimal(self.target_fraction, field="signal.target_fraction")
        if fraction < 0 or fraction > 1:
            raise ValueError("target fraction must be within [0, 1]")
        if self.direction is SignalDirection.LONG and fraction == 0:
            raise ValueError("long target fraction must be positive")
        if self.direction is SignalDirection.EXIT and fraction != 0:
            raise ValueError("exit target must be zero")
        if self.stop_price is not None:
            _decimal(self.stop_price, field="signal.stop_price", positive=True)
        object.__setattr__(self, "generated_at", utc_datetime(self.generated_at))
        object.__setattr__(self, "expires_at", utc_datetime(self.expires_at))
        if self.expires_at <= self.generated_at:
            raise ValueError("signal must expire after generation")


class Strategy(Protocol):
    @property
    def manifest(self) -> StrategyManifest: ...

    def on_event(self, event: EventEnvelope[MarketPayload], context: StrategyContext) -> tuple[StrategySignal, ...]: ...

    def snapshot(self) -> bytes: ...

    def restore(self, data: bytes) -> None: ...
