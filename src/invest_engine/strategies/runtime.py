"""Causal strategy dispatcher; deliberately does not submit orders."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from invest_engine.data.calendar import SessionCalendar
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import utc_datetime
from invest_engine.features.registry import FeatureRegistry
from invest_engine.strategies.contracts import (
    BarObservation, Strategy, StrategyContext, StrategySignal,
)


@dataclass(frozen=True, slots=True)
class StrategyOutcome:
    signals: tuple[StrategySignal, ...]
    reason_codes: tuple[str, ...] = ()


class StrategyRunner:
    """Consume a validated stream in deterministic journal order.

    The caller must persist the stream (E2) and replay it to reconstruct
    strategy state after a crash. This runtime is NOT an execution engine.
    """

    def __init__(self, strategy: Strategy, calendar: SessionCalendar, *,
                 max_bars: int = 30000) -> None:
        if max_bars < 1:
            raise ValueError("max_bars must be positive")
        self.strategy = strategy
        self.calendar = calendar
        self.max_bars = max_bars
        self._bars: list[BarObservation] = []
        self._seen_ids: set[str] = set()
        self._last_ordinal = -1
        self._last_known: datetime | None = None
        self._registry = FeatureRegistry(strategy.manifest.features)
        self._counts: dict[tuple[str, str, timedelta | None], int] = {}
        self._last_observed: dict[tuple[str, str, timedelta | None], datetime] = {}
        self._halt_reason: str | None = None

    @property
    def halt_reason(self) -> str | None:
        return self._halt_reason

    def accept(self, event: EventEnvelope[MarketPayload]) -> StrategyOutcome:
        if self._halt_reason is not None:
            raise InvalidEvent("strategy runner halted: restore by replay from trusted journal")
        try:
            return self._accept(event)
        except Exception as exc:
            self._halt_reason = f"{type(exc).__name__}: {exc}"
            raise

    def _accept(self, event: EventEnvelope[MarketPayload]) -> StrategyOutcome:
        if event.ingest_ordinal != self._last_ordinal + 1:
            raise InvalidEvent("strategy stream must have contiguous ordinals")
        if event.event_id in self._seen_ids:
            raise InvalidEvent("duplicate strategy event")
        if event.quality_flags:
            raise InvalidEvent("quality-flagged input cannot be used by a strategy")
        now = max(event.available_at, event.received_at)
        if self._last_known is not None and now < self._last_known:
            raise InvalidEvent("strategy clock moved backwards")
        if event.event_time > now:
            raise InvalidEvent("market event cannot be observed before occurrence")
        if isinstance(event.payload, Bar) and not event.payload.finalized:
            raise InvalidEvent("unfinalized bar not visible to strategy")
        self._seen_ids.add(event.event_id)
        self._last_ordinal = event.ingest_ordinal
        self._last_known = now
        if event.instrument_id is not None:
            count_key = (event.instrument_id.key, event.event_type,
                         event.payload.interval if isinstance(event.payload, Bar) else None)
            self._counts[count_key] = self._counts.get(count_key, 0) + 1
            self._last_observed[count_key] = now

        inst = event.instrument_id
        session = self.calendar.session_for(inst, event.event_time) if inst else None
        if isinstance(event.payload, Bar) and inst is not None:
            # Using a bar's start gives correct session lookup at an end boundary.
            session = self.calendar.session_for(inst, event.payload.start)
            if session is None:
                return StrategyOutcome((), ("SESSION_UNAVAILABLE",))
            try:
                observation = BarObservation(event.event_id, inst, event.payload, now, session)
            except ValueError as exc:
                raise InvalidEvent("bar violates session boundaries") from exc
            if any(b.instrument.key == inst.key and b.bar.interval == event.payload.interval
                   and b.bar.start == event.payload.start for b in self._bars):
                raise InvalidEvent("duplicate bar interval for instrument")
            self._bars.append(observation)
            if len(self._bars) > self.max_bars:
                del self._bars[:len(self._bars)-self.max_bars]

        manifest = self.strategy.manifest
        if inst is None or inst.market not in manifest.markets:
            return StrategyOutcome((), ("UNSUPPORTED_MARKET",))
        matching = [r for r in manifest.requirements if r.event_type == event.event_type and (
            r.interval is None or (isinstance(event.payload, Bar) and event.payload.interval == r.interval)
        )]
        if not matching:
            return StrategyOutcome((), ("UNSUBSCRIBED_EVENT",))
        if session is None:
            return StrategyOutcome((), ("SESSION_UNAVAILABLE",))
        for requirement in manifest.requirements:
            key = (inst.key, requirement.event_type, requirement.interval)
            if self._counts.get(key, 0) < requirement.warmup:
                return StrategyOutcome((), ("WARMUP_INCOMPLETE",))
            if requirement.max_age is not None:
                last_seen = self._last_observed.get(key)
                if last_seen is None or now - last_seen > requirement.max_age:
                    return StrategyOutcome((), ("REQUIRED_DATA_STALE",))
        features = self._registry.compute(inst, now, tuple(self._bars))
        if len(features) != len(manifest.features):
            return StrategyOutcome((), ("FEATURE_WARMUP_INCOMPLETE",))
        context = StrategyContext(now, event, tuple(self._bars), session, features)
        signals = self.strategy.on_event(event, context)
        if not isinstance(signals, tuple) or any(not isinstance(s, StrategySignal) for s in signals):
            raise InvalidEvent("strategy must return immutable StrategySignal tuple")
        for signal in signals:
            if (signal.strategy_id != manifest.strategy_id
                or signal.strategy_version != manifest.version
                or signal.instrument.key != inst.key
                or signal.trigger_event_id != event.event_id
                or signal.generated_at != now
                or signal.expires_at <= now):
                raise InvalidEvent("strategy returned signal with incorrect context or identity")
        if len({s.signal_id for s in signals}) != len(signals):
            raise InvalidEvent("duplicate signal IDs in a single decision")
        return StrategyOutcome(signals, () if signals else ("NO_ACTION",))
