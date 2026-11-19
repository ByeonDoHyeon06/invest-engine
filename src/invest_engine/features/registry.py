"""Versioned point-in-time feature definitions and immutable observations."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, getcontext, localcontext
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


@dataclass(frozen=True, slots=True)
class _RecursiveFeature:
    history: tuple[BarObservation, ...]
    value: Decimal
    context_signature: tuple[object, ...]


def _context_signature() -> tuple[object, ...]:
    ctx = getcontext()
    # Reference EMA/ATR always set precision=64 but inherit these settings.
    return (ctx.rounding, ctx.Emin, ctx.Emax, ctx.clamp, tuple(ctx.traps.items()))


class FeatureRegistry:
    def __init__(self, definitions: tuple[FeatureDefinition, ...]) -> None:
        self.definitions = definitions
        names = [d.name for d in definitions]
        if len(names) != len(set(names)):
            raise ValueError("duplicate feature names")
        self._graph = FeatureGraph(FeatureNode(d.name) for d in definitions)
        self._recursive: dict[str, _RecursiveFeature] = {}

    def _recursive_value(
        self, definition: FeatureDefinition, history: tuple[BarObservation, ...],
    ) -> Decimal:
        """Extend only an identical, already validated prefix.

        Fall back to the reference implementation on eviction, invalidation,
        changed history or Decimal context. The recurrence and seed are
        unchanged; this is neither a finite-window approximation nor a new
        indicator definition.
        """
        signature = _context_signature()
        previous = self._recursive.get(definition.name)
        if (previous is not None and previous.context_signature == signature
                and len(previous.history) <= len(history)
                and all(a is b for a, b in zip(previous.history, history, strict=False))):
            n = len(previous.history)
            suffix = history[n:]
            if (all(b.bar.finalized for b in suffix)
                    and all(a.bar.end <= b.bar.start for a, b in
                            zip(history[n-1:], suffix, strict=False))):
                with localcontext() as ctx:
                    ctx.prec = 64
                    value = previous.value
                    period = definition.period
                    if definition.kind is FeatureKind.EMA:
                        alpha = Decimal(2) / (period + 1)
                        for b in suffix:
                            value = alpha * b.bar.close + (Decimal(1) - alpha) * value
                    else:
                        for a, b in zip(history[n-1:], suffix, strict=False):
                            tr = max(b.bar.high - b.bar.low,
                                     abs(b.bar.high - a.bar.close),
                                     abs(b.bar.low - a.bar.close))
                            value = (value * (period - 1) + tr) / period
                    value = +value
                self._recursive[definition.name] = _RecursiveFeature(history, value, signature)
                return value
        bars = [b.bar for b in history]
        value = (ema(bars, definition.period) if definition.kind is FeatureKind.EMA
                 else atr(bars, definition.period))
        self._recursive[definition.name] = _RecursiveFeature(history, value, signature)
        return value

    def compute(
        self, instrument: InstrumentId, as_of: datetime, bars: tuple[BarObservation, ...],
    ) -> tuple[FeatureValue, ...]:
        now = utc_datetime(as_of)
        values: list[FeatureValue] = []
        for name in self._graph.schedule(d.name for d in self.definitions):
            definition = next(d for d in self.definitions if d.name == name)
            key = instrument.key
            history = [b for b in bars if b.instrument.key == key
                       and b.bar.interval == definition.interval and b.known_at <= now]
            needed = definition.period + int(definition.kind is FeatureKind.ATR)
            if len(history) < needed:
                continue
            latest = history[-needed:] if definition.kind is FeatureKind.MEDIAN_VOLUME else history
            if definition.kind in (FeatureKind.EMA, FeatureKind.ATR):
                value = self._recursive_value(definition, tuple(latest))
            else:
                value = median_volume([b.bar for b in latest], definition.period)
            values.append(FeatureValue(
                name, definition.version, instrument, now, value,
                tuple(b.event_id for b in latest),
            ))
        return tuple(values)
