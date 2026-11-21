"""Immutable universe-level strategy contracts for multi-symbol research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Protocol

from invest_engine.domain.primitives import InstrumentId, Market, _decimal, utc_datetime
from invest_engine.strategies.contracts import BarObservation, StrategySignal


_ONE_MINUTE = timedelta(minutes=1)


class UniverseCheckpointKind(str, Enum):
    REBALANCE = "REBALANCE"
    FLATTEN = "FLATTEN"


class UniverseFrameStatus(str, Enum):
    COMPLETE = "COMPLETE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
    NO_ACTION = "NO_ACTION"


@dataclass(frozen=True, slots=True)
class UniverseDecisionFrame:
    """One deterministic, complete cross-sectional decision instant."""

    frame_id: str
    as_of: datetime
    session_start: datetime
    session_end: datetime
    slot_index: int
    kind: UniverseCheckpointKind
    instruments: tuple[InstrumentId, ...]
    trigger_bars: tuple[BarObservation, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.frame_id, str) or not self.frame_id.strip():
            raise ValueError("frame identity is required")

        instant = utc_datetime(self.as_of, field="frame.as_of")
        session_start = utc_datetime(self.session_start, field="frame.session_start")
        session_end = utc_datetime(self.session_end, field="frame.session_end")
        object.__setattr__(self, "as_of", instant)
        object.__setattr__(self, "session_start", session_start)
        object.__setattr__(self, "session_end", session_end)
        if not session_start < instant < session_end:
            raise ValueError("frame instant must be inside its session")
        if type(self.slot_index) is not int or self.slot_index < 1:
            raise ValueError("frame slot index must be a positive integer")
        if not isinstance(self.kind, UniverseCheckpointKind):
            raise ValueError("invalid universe checkpoint kind")

        if not isinstance(self.instruments, tuple) or not self.instruments:
            raise ValueError("frame instruments must be a nonempty tuple")
        if any(not isinstance(instrument, InstrumentId) for instrument in self.instruments):
            raise ValueError("frame instruments must contain InstrumentId values")
        instrument_keys = tuple(instrument.key for instrument in self.instruments)
        if instrument_keys != tuple(sorted(instrument_keys)):
            raise ValueError("frame instruments must be sorted by instrument key")
        if len(instrument_keys) != len(set(instrument_keys)):
            raise ValueError("frame instruments must be unique")

        if not isinstance(self.trigger_bars, tuple):
            raise ValueError("frame trigger bars must be a tuple")
        if len(self.trigger_bars) != len(self.instruments):
            raise ValueError("frame requires one trigger bar per instrument")
        if any(not isinstance(item, BarObservation) for item in self.trigger_bars):
            raise ValueError("frame trigger bars must contain BarObservation values")

        for instrument, observation in zip(self.instruments, self.trigger_bars, strict=True):
            if observation.instrument.key != instrument.key:
                raise ValueError("trigger bar instrument must match frame instrument")
            if (
                observation.bar.interval != _ONE_MINUTE
                or observation.bar.start != instant - _ONE_MINUTE
                or observation.bar.end != instant
            ):
                raise ValueError("trigger bar must be the exact one-minute bar ending at frame instant")
            if observation.known_at > instant:
                raise ValueError("future trigger observation is not allowed")
            if (
                observation.session.start != session_start
                or observation.session.end != session_end
            ):
                raise ValueError("trigger bar session must match frame session")


@dataclass(frozen=True, slots=True)
class UniverseFrameOutcome:
    """Explicitly separates a usable frame from unavailable and no-action states."""

    status: UniverseFrameStatus
    as_of: datetime
    frame: UniverseDecisionFrame | None = None
    missing_instrument_keys: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.status, UniverseFrameStatus):
            raise ValueError("invalid universe frame status")
        instant = utc_datetime(self.as_of, field="frame_outcome.as_of")
        object.__setattr__(self, "as_of", instant)
        if not isinstance(self.missing_instrument_keys, tuple):
            raise ValueError("missing instrument keys must be a tuple")
        if any(not isinstance(key, str) or not key.strip() for key in self.missing_instrument_keys):
            raise ValueError("missing instrument keys must be nonempty strings")
        if self.missing_instrument_keys != tuple(sorted(self.missing_instrument_keys)):
            raise ValueError("missing instrument keys must be sorted")
        if len(self.missing_instrument_keys) != len(set(self.missing_instrument_keys)):
            raise ValueError("missing instrument keys must be unique")
        if not isinstance(self.reason_codes, tuple) or any(
            not isinstance(code, str) or not code.strip() for code in self.reason_codes
        ):
            raise ValueError("reason codes must be a tuple of nonempty strings")

        if self.status is UniverseFrameStatus.COMPLETE:
            if self.frame is None or self.frame.as_of != instant:
                raise ValueError("complete outcome requires a matching frame")
            if self.missing_instrument_keys:
                raise ValueError("complete outcome cannot contain missing instruments")
        elif self.status is UniverseFrameStatus.DATA_UNAVAILABLE:
            if self.frame is not None:
                raise ValueError("data-unavailable outcome cannot contain a complete frame")
            if not self.missing_instrument_keys:
                raise ValueError("data-unavailable outcome requires missing instruments")
        else:
            if self.frame is not None:
                raise ValueError("no-action outcome cannot contain a complete frame")
            if self.missing_instrument_keys:
                raise ValueError("no-action outcome cannot contain missing instruments")
            if not self.reason_codes:
                raise ValueError("no-action outcome requires a reason code")


@dataclass(frozen=True, slots=True)
class PortfolioStrategyManifest:
    strategy_id: str
    version: str
    markets: frozenset[Market]
    bar_interval: timedelta
    checkpoint_interval: timedelta
    max_long_positions: int
    max_gross_target_fraction: Decimal

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.strategy_id, self.version)
        ):
            raise ValueError("portfolio strategy id and version are required")
        if (
            not isinstance(self.markets, frozenset)
            or not self.markets
            or any(not isinstance(market, Market) for market in self.markets)
        ):
            raise ValueError("portfolio strategy markets are required")
        if not isinstance(self.bar_interval, timedelta) or self.bar_interval <= timedelta(0):
            raise ValueError("portfolio bar interval must be positive")
        if (
            not isinstance(self.checkpoint_interval, timedelta)
            or self.checkpoint_interval <= timedelta(0)
            or self.checkpoint_interval % self.bar_interval != timedelta(0)
        ):
            raise ValueError("checkpoint interval must be a positive multiple of bar interval")
        if type(self.max_long_positions) is not int or self.max_long_positions < 1:
            raise ValueError("max long positions must be a positive integer")
        gross_fraction = _decimal(
            self.max_gross_target_fraction,
            field="portfolio_strategy.max_gross_target_fraction",
        )
        if gross_fraction <= 0 or gross_fraction > 1:
            raise ValueError("max gross target fraction must be within (0, 1]")


@dataclass(frozen=True, slots=True)
class PortfolioStrategyContext:
    """Pure read-only history for one complete universe decision frame."""

    as_of: datetime
    frame: UniverseDecisionFrame
    bars: tuple[BarObservation, ...]

    def __post_init__(self) -> None:
        instant = utc_datetime(self.as_of, field="portfolio_context.as_of")
        object.__setattr__(self, "as_of", instant)
        if not isinstance(self.frame, UniverseDecisionFrame) or self.frame.as_of != instant:
            raise ValueError("portfolio context must match its decision frame")
        if not isinstance(self.bars, tuple):
            raise ValueError("portfolio context bars must be a tuple")
        if any(not isinstance(observation, BarObservation) for observation in self.bars):
            raise ValueError("portfolio context bars must contain BarObservation values")
        if any(observation.known_at > instant for observation in self.bars):
            raise ValueError("future observations are not allowed in portfolio context")

    def bars_for(
        self,
        instrument: InstrumentId,
        interval: timedelta,
    ) -> tuple[BarObservation, ...]:
        return tuple(
            observation
            for observation in self.bars
            if observation.instrument.key == instrument.key
            and observation.bar.interval == interval
        )


@dataclass(frozen=True, slots=True)
class PortfolioSignalBatch:
    frame_id: str
    strategy_id: str
    strategy_version: str
    generated_at: datetime
    signals: tuple[StrategySignal, ...]
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        identities = (self.frame_id, self.strategy_id, self.strategy_version)
        if not all(isinstance(value, str) and value.strip() for value in identities):
            raise ValueError("portfolio signal batch identity fields are required")
        object.__setattr__(
            self,
            "generated_at",
            utc_datetime(self.generated_at, field="portfolio_signal_batch.generated_at"),
        )
        if not isinstance(self.signals, tuple):
            raise ValueError("portfolio signal batch signals must be a tuple")
        if any(not isinstance(signal, StrategySignal) for signal in self.signals):
            raise ValueError("portfolio signal batch must contain StrategySignal values")
        signal_ids = tuple(signal.signal_id for signal in self.signals)
        if len(signal_ids) != len(set(signal_ids)):
            raise ValueError("portfolio signal batch contains duplicate signal ids")
        if not isinstance(self.reason_codes, tuple) or any(
            not isinstance(code, str) or not code.strip() for code in self.reason_codes
        ):
            raise ValueError("reason codes must be a tuple of nonempty strings")


class PortfolioStrategy(Protocol):
    @property
    def manifest(self) -> PortfolioStrategyManifest: ...

    def on_frame(
        self,
        frame: UniverseDecisionFrame,
        context: PortfolioStrategyContext,
    ) -> PortfolioSignalBatch: ...

    def snapshot(self) -> bytes: ...

    def restore(self, data: bytes) -> None: ...
