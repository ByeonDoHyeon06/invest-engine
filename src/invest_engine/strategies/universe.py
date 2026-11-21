"""Deterministic cross-sectional frame coordination for offline research."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from invest_engine.data.calendar import SessionCalendar
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import Bar, BarKind, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import InstrumentId, utc_datetime
from invest_engine.strategies.contracts import BarObservation
from invest_engine.strategies.portfolio_contracts import (
    UniverseCheckpointKind,
    UniverseDecisionFrame,
    UniverseFrameOutcome,
    UniverseFrameStatus,
)


_ONE_MINUTE = timedelta(minutes=1)


class UniverseFrameCoordinator:
    """Synchronize one immutable universe against explicit replay watermarks."""

    def __init__(
        self,
        calendar: SessionCalendar,
        instruments: tuple[InstrumentId, ...],
        *,
        bar_interval: timedelta = _ONE_MINUTE,
        checkpoint_interval: timedelta = timedelta(minutes=30),
        full_session_duration: timedelta = timedelta(minutes=390),
        max_bars: int = 500_000,
    ) -> None:
        if not isinstance(instruments, tuple) or len(instruments) < 2:
            raise ValueError("universe requires at least two instruments in a tuple")
        if any(not isinstance(instrument, InstrumentId) for instrument in instruments):
            raise ValueError("universe must contain InstrumentId values")
        ordered = tuple(sorted(instruments, key=lambda instrument: instrument.key))
        keys = tuple(instrument.key for instrument in ordered)
        if len(keys) != len(set(keys)):
            raise ValueError("universe instruments must be unique")
        if len({instrument.market for instrument in ordered}) != 1:
            raise ValueError("universe instruments must share one market")
        if len({instrument.currency for instrument in ordered}) != 1:
            raise ValueError("universe instruments must share one currency")
        if bar_interval != _ONE_MINUTE:
            raise ValueError("universe frames currently require one-minute bars")
        if (
            not isinstance(checkpoint_interval, timedelta)
            or checkpoint_interval <= timedelta(0)
            or checkpoint_interval % bar_interval != timedelta(0)
        ):
            raise ValueError("checkpoint interval must be a positive bar multiple")
        if (
            not isinstance(full_session_duration, timedelta)
            or full_session_duration <= timedelta(0)
        ):
            raise ValueError("full session duration must be positive")
        if type(max_bars) is not int or max_bars < 1:
            raise ValueError("max_bars must be a positive integer")

        self.calendar = calendar
        self.instruments = ordered
        self.bar_interval = bar_interval
        self.checkpoint_interval = checkpoint_interval
        self.full_session_duration = full_session_duration
        self.max_bars = max_bars
        self._instrument_by_key = {instrument.key: instrument for instrument in ordered}
        self._observations: list[BarObservation] = []
        self._bar_keys: set[tuple[str, timedelta | None, datetime]] = set()
        self._seen_ids: set[str] = set()
        self._last_ordinal = -1
        self._last_known: datetime | None = None
        self._finalized_watermark: datetime | None = None
        self._halt_reason: str | None = None

    @property
    def observations(self) -> tuple[BarObservation, ...]:
        return tuple(self._observations)

    @property
    def last_ordinal(self) -> int:
        return self._last_ordinal

    @property
    def last_known(self) -> datetime | None:
        return self._last_known

    @property
    def finalized_watermark(self) -> datetime | None:
        return self._finalized_watermark

    @property
    def halt_reason(self) -> str | None:
        return self._halt_reason

    def invalidate_instrument_history(self, instrument: InstrumentId) -> None:
        """Drop stale price history without rewinding replay audit identity."""
        if not isinstance(instrument, InstrumentId):
            raise ValueError("history invalidation requires an InstrumentId")
        self._observations = [
            observation
            for observation in self._observations
            if observation.instrument.key != instrument.key
        ]
        self._bar_keys = {
            key for key in self._bar_keys if key[0] != instrument.key
        }

    def accept(self, event: EventEnvelope[MarketPayload]) -> None:
        if self._halt_reason is not None:
            raise InvalidEvent(
                "universe frame coordinator halted: restore by replay from trusted journal"
            )
        try:
            self._accept(event)
        except Exception as exc:
            self._halt_reason = f"{type(exc).__name__}: {exc}"
            raise

    def _accept(self, event: EventEnvelope[MarketPayload]) -> None:
        if event.ingest_ordinal != self._last_ordinal + 1:
            raise InvalidEvent("universe stream must have contiguous ordinals")
        if event.event_id in self._seen_ids:
            raise InvalidEvent("duplicate universe event")
        if event.quality_flags:
            raise InvalidEvent("quality-flagged input cannot enter a universe frame")
        if not isinstance(event.payload, Bar):
            raise InvalidEvent("universe coordinator accepts only bars")
        if event.payload.kind is not BarKind.TIME:
            raise InvalidEvent("universe coordinator accepts only TIME bars")
        if event.payload.interval != self.bar_interval:
            raise InvalidEvent("bar interval does not match universe interval")
        if not event.payload.finalized:
            raise InvalidEvent("unfinalized bar cannot enter a universe frame")
        if (
            self._finalized_watermark is not None
            and event.payload.end <= self._finalized_watermark
        ):
            raise InvalidEvent("bar ended at or before finalized universe watermark")
        instrument = event.instrument_id
        if instrument is None or instrument.key not in self._instrument_by_key:
            raise InvalidEvent("bar instrument is outside the configured universe")

        known_at = max(event.available_at, event.received_at)
        if self._last_known is not None and known_at < self._last_known:
            raise InvalidEvent("universe clock moved backwards")
        if event.event_time > known_at:
            raise InvalidEvent("market event cannot be observed before occurrence")
        session = self.calendar.session_for(instrument, event.payload.start)
        if session is None:
            raise InvalidEvent("UNIVERSE_SESSION_UNAVAILABLE")
        try:
            observation = BarObservation(
                event.event_id,
                instrument,
                event.payload,
                known_at,
                session,
            )
        except ValueError as exc:
            raise InvalidEvent("bar violates universe session boundaries") from exc
        bar_key = (instrument.key, event.payload.interval, event.payload.start)
        if bar_key in self._bar_keys:
            raise InvalidEvent("duplicate universe bar interval for instrument")

        self._seen_ids.add(event.event_id)
        self._last_ordinal = event.ingest_ordinal
        self._last_known = known_at
        self._observations.append(observation)
        self._bar_keys.add(bar_key)
        if len(self._observations) > self.max_bars:
            excess = len(self._observations) - self.max_bars
            for old in self._observations[:excess]:
                self._bar_keys.remove(
                    (old.instrument.key, old.bar.interval, old.bar.start)
                )
            del self._observations[:excess]

    def finalize(self, as_of: datetime) -> UniverseFrameOutcome:
        if self._halt_reason is not None:
            raise InvalidEvent(
                "universe frame coordinator halted: restore by replay from trusted journal"
            )
        try:
            outcome = self._finalize(as_of)
        except Exception as exc:
            self._halt_reason = f"{type(exc).__name__}: {exc}"
            raise
        self._finalized_watermark = outcome.as_of
        return outcome

    def _finalize(self, as_of: datetime) -> UniverseFrameOutcome:
        instant = utc_datetime(as_of, field="universe_frame.as_of")
        if self._last_known is not None and instant < self._last_known:
            raise InvalidEvent("finalization cannot move behind observed stream")
        if (
            self._finalized_watermark is not None
            and instant < self._finalized_watermark
        ):
            raise InvalidEvent("finalization cannot move behind prior watermark")
        trigger_by_key = {
            observation.instrument.key: observation
            for observation in self._observations
            if observation.bar.end == instant
        }
        missing = tuple(
            instrument.key
            for instrument in self.instruments
            if instrument.key not in trigger_by_key
        )
        if missing:
            return UniverseFrameOutcome(
                UniverseFrameStatus.DATA_UNAVAILABLE,
                instant,
                missing_instrument_keys=missing,
                reason_codes=("UNIVERSE_FRAME_INCOMPLETE",),
            )

        trigger_bars = tuple(
            trigger_by_key[instrument.key] for instrument in self.instruments
        )
        session_bounds = {
            (observation.session.start, observation.session.end)
            for observation in trigger_bars
        }
        if len(session_bounds) != 1:
            raise InvalidEvent("UNIVERSE_SESSION_MISMATCH")
        session_start, session_end = next(iter(session_bounds))
        if session_end - session_start != self.full_session_duration:
            return UniverseFrameOutcome(
                UniverseFrameStatus.NO_ACTION,
                instant,
                reason_codes=("NO_ACTION_EARLY_CLOSE",),
            )

        elapsed = instant - session_start
        flatten_at = session_end - self.checkpoint_interval
        if instant == flatten_at:
            kind = UniverseCheckpointKind.FLATTEN
        elif (
            elapsed >= self.checkpoint_interval
            and instant <= session_end - timedelta(hours=1)
            and elapsed % self.checkpoint_interval == timedelta(0)
        ):
            kind = UniverseCheckpointKind.REBALANCE
        else:
            return UniverseFrameOutcome(
                UniverseFrameStatus.NO_ACTION,
                instant,
                reason_codes=("NO_ACTION_OUTSIDE_CHECKPOINT_SCHEDULE",),
            )
        slot_index = elapsed // self.checkpoint_interval

        identity = {
            "as_of": instant.isoformat(),
            "instrument_keys": [instrument.key for instrument in self.instruments],
            "kind": kind.value,
            "session_end": session_end.isoformat(),
            "session_start": session_start.isoformat(),
            "trigger_event_ids": [item.event_id for item in trigger_bars],
        }
        encoded = json.dumps(
            identity,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        frame = UniverseDecisionFrame(
            frame_id="universe-frame:" + hashlib.sha256(encoded).hexdigest(),
            as_of=instant,
            session_start=session_start,
            session_end=session_end,
            slot_index=slot_index,
            kind=kind,
            instruments=self.instruments,
            trigger_bars=trigger_bars,
        )
        return UniverseFrameOutcome(UniverseFrameStatus.COMPLETE, instant, frame)
