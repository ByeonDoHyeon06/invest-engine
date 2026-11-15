"""Stateful, fail-closed market-feed quality checks and replay-safe watermarks."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum

from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload


class Disposition(str, Enum):
    ACCEPT = "ACCEPT"
    QUARANTINE = "QUARANTINE"


class QualityFlag(str, Enum):
    DUPLICATE = "DUPLICATE"
    LATE = "LATE"
    STALE = "STALE"
    SEQUENCE_GAP = "SEQUENCE_GAP"
    SEQUENCE_REWIND = "SEQUENCE_REWIND"
    STREAM_UNSYNCED = "STREAM_UNSYNCED"
    UNFINALIZED_BAR = "UNFINALIZED_BAR"


@dataclass(frozen=True, slots=True)
class QualityPolicy:
    allowed_lateness: timedelta = timedelta(0)
    max_receipt_delay: timedelta | None = None

    def __post_init__(self) -> None:
        if self.allowed_lateness < timedelta(0):
            raise ValueError("allowed_lateness cannot be negative")
        if self.max_receipt_delay is not None and self.max_receipt_delay < timedelta(0):
            raise ValueError("max_receipt_delay cannot be negative")


@dataclass(frozen=True, slots=True)
class QualityDecision:
    disposition: Disposition
    event: EventEnvelope[MarketPayload]
    flags: tuple[QualityFlag, ...]

    @property
    def accepted(self) -> bool:
        return self.disposition is Disposition.ACCEPT


@dataclass(slots=True)
class QualityGate:
    """Call in arrival order. Quarantined events never become trading observations.

    Sequence gaps put the stream into UNSYNCED until reset_stream is explicitly
    called after an external snapshot/recovery. This class never guesses gaps.
    """

    policy: QualityPolicy = field(default_factory=QualityPolicy)
    _seen_ids: set[str] = field(default_factory=set, init=False, repr=False)
    _watermarks: dict[tuple[str, str, str], datetime] = field(
        default_factory=dict, init=False, repr=False
    )
    _sequences: dict[tuple[str, str, str], int] = field(
        default_factory=dict, init=False, repr=False
    )
    _unsynced: set[tuple[str, str, str]] = field(default_factory=set, init=False, repr=False)

    @staticmethod
    def stream_key(event: EventEnvelope[MarketPayload]) -> tuple[str, str, str]:
        instrument = event.instrument_id.key if event.instrument_id else "GLOBAL"
        return (event.source, instrument, event.event_type)

    def reset_stream(self, key: tuple[str, str, str], *, last_sequence: int | None = None) -> None:
        """Only invoke after the caller has independently reconciled this feed."""
        if last_sequence is not None and last_sequence < 0:
            raise ValueError("last_sequence cannot be negative")
        self._unsynced.discard(key)
        self._watermarks.pop(key, None)
        self._sequences.pop(key, None)
        if last_sequence is not None:
            self._sequences[key] = last_sequence

    def inspect(self, event: EventEnvelope[MarketPayload]) -> QualityDecision:
        flags: set[QualityFlag] = set()
        key = self.stream_key(event)
        if event.event_id in self._seen_ids:
            return QualityDecision(
                Disposition.QUARANTINE,
                replace(event, quality_flags=tuple(sorted(set(event.quality_flags) | {QualityFlag.DUPLICATE.value}))),
                (QualityFlag.DUPLICATE,),
            )
        self._seen_ids.add(event.event_id)

        previous_time = self._watermarks.get(key)
        if previous_time is not None and event.event_time < previous_time - self.policy.allowed_lateness:
            flags.add(QualityFlag.LATE)
        if previous_time is None or event.event_time > previous_time:
            self._watermarks[key] = event.event_time

        if event.source_sequence is not None:
            previous_seq = self._sequences.get(key)
            if previous_seq is not None:
                if event.source_sequence <= previous_seq:
                    flags.add(QualityFlag.SEQUENCE_REWIND)
                elif event.source_sequence > previous_seq + 1:
                    flags.add(QualityFlag.SEQUENCE_GAP)
                    self._unsynced.add(key)
            if previous_seq is None or event.source_sequence > previous_seq:
                self._sequences[key] = event.source_sequence

        if key in self._unsynced:
            flags.add(QualityFlag.STREAM_UNSYNCED)
        if (
            self.policy.max_receipt_delay is not None
            and event.received_at - event.available_at > self.policy.max_receipt_delay
        ):
            flags.add(QualityFlag.STALE)
        if isinstance(event.payload, Bar) and not event.payload.finalized:
            flags.add(QualityFlag.UNFINALIZED_BAR)

        ordered = tuple(sorted(flags, key=lambda flag: flag.value))
        enriched = replace(
            event,
            quality_flags=tuple(sorted(set(event.quality_flags) | {flag.value for flag in ordered})),
        )
        return QualityDecision(
            Disposition.QUARANTINE if flags else Disposition.ACCEPT,
            enriched,
            ordered,
        )
