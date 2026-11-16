"""Versioned point-in-time feature definitions and immutable observations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum

from invest_engine.core.features import FeatureGraph, FeatureNode
from invest_engine.domain.primitives import InstrumentId, utc_datetime
from invest_engine.features.technical import atr, ema, median_volume
from invest_engine.strategies.contracts import BarObservation


class FeatureKind(str, Enum):
    EMA = "EMA"
    ATR = "ATR"
    MEDIAN_VOLUME = "MEDIAN_VOLUME"


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    name: str
    kind: FeatureKind
    interval: timedelta
    period: int
    version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not self.name.strip() or not self.version.strip():
            raise ValueError("feature name and version required")
        if not isinstance(self.kind, FeatureKind):
            raise ValueError("unsupported feature kind")
        if self.interval <= timedelta(0) or self.period < 1:
            raise ValueError("feature interval and period must be positive")


@dataclass(frozen=True, slots=True)
class FeatureValue:
    name: str
    version: str
    instrument: InstrumentId
    as_of: datetime
    value: Decimal
    source_event_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", utc_datetime(self.as_of))
        if not self.source_event_ids:
            raise ValueError("source events required")


class FeatureRegistry:
    def __init__(self, definitions: tuple[FeatureDefinition, ...]) -> None:
        self.definitions = definitions
        names = [d.name for d in definitions]
        if len(names) != len(set(names)):
            raise ValueError("duplicate feature names")
        self._graph = FeatureGraph(FeatureNode(d.name) for d in definitions)

    def compute(
        self, instrument: InstrumentId, as_of: datetime, bars: tuple[BarObservation, ...],
    ) -> tuple[FeatureValue, ...]:
        now = utc_datetime(as_of)
        values: list[FeatureValue] = []
        for name in self._graph.schedule(d.name for d in self.definitions):
            definition = next(d for d in self.definitions if d.name == name)
            history = [b for b in bars if b.instrument.key == instrument.key
                       and b.bar.interval == definition.interval and b.known_at <= now]
            needed = definition.period + int(definition.kind is FeatureKind.ATR)
            if len(history) < needed:
                continue
            latest = history[-needed:] if definition.kind is FeatureKind.MEDIAN_VOLUME else history
            if definition.kind is FeatureKind.EMA:
                value = ema([b.bar for b in latest], definition.period)
            elif definition.kind is FeatureKind.ATR:
                value = atr([b.bar for b in latest], definition.period)
            else:
                value = median_volume([b.bar for b in latest], definition.period)
            values.append(FeatureValue(
                name, definition.version, instrument, now, value,
                tuple(b.event_id for b in latest),
            ))
        return tuple(values)
