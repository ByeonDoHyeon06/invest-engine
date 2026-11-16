"""Deterministic, side-effect-free event reducer and single-writer coordinator.

E2 is an observation runtime, not a trading/order execution engine. Live is
intentionally disabled until a separately authorized broker adapter exists.
"""

from __future__ import annotations

import hashlib
from contextlib import suppress
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum
from typing import Iterable

from invest_engine.core.replay import canonical_bytes
from invest_engine.domain.errors import InvalidEvent, UnsupportedData
from invest_engine.domain.events import Bar, EventEnvelope, MarketPayload
from invest_engine.domain.primitives import Market


class RuntimeMode(str, Enum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


class RuntimeStatus(str, Enum):
    RUNNING = "RUNNING"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    run_version: str
    mode: RuntimeMode = RuntimeMode.BACKTEST
    snapshot_interval: int = 100

    def __post_init__(self) -> None:
        if not self.run_version or not self.run_version.strip():
            raise ValueError("run_version must be nonempty")
        if not isinstance(self.mode, RuntimeMode):
            raise ValueError("invalid runtime mode")
        if self.snapshot_interval < 1:
            raise ValueError("snapshot_interval must be positive")
        if self.mode is RuntimeMode.LIVE:
            raise UnsupportedData("LIVE mode is unavailable before E8 approval")


@dataclass(frozen=True, slots=True)
class RuntimeState:
    run_version: str
    mode: RuntimeMode
    last_ordinal: int = -1
    observed_at: datetime | None = None
    event_count: int = 0
    digest: str = ""
    seen_ids: frozenset[str] = field(default_factory=frozenset)
    counts: tuple[tuple[str, int], ...] = ()
    status: RuntimeStatus = RuntimeStatus.RUNNING
    halt_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ObservationDispatch:
    """Pure command describing intended delivery; it performs no callbacks or I/O."""

    subscription_id: str
    event_id: str
    event_type: str


@dataclass(frozen=True, slots=True)
class Subscription:
    subscription_id: str
    event_types: frozenset[str]
    markets: frozenset[Market] = frozenset()
    bar_intervals: frozenset[timedelta] = frozenset()

    def __post_init__(self) -> None:
        if not self.subscription_id.strip() or not self.event_types:
            raise ValueError("subscription id and event types are required")
        if any(not name or not name.strip() for name in self.event_types):
            raise ValueError("event type name must be nonempty")
        if any(step <= timedelta(0) for step in self.bar_intervals):
            raise ValueError("bar interval must be positive")

    def matches(self, event: EventEnvelope[MarketPayload]) -> bool:
        if event.event_type not in self.event_types:
            return False
        if self.markets and (
            event.instrument_id is None or event.instrument_id.market not in self.markets
        ):
            return False
        return not (
            self.bar_intervals
            and (
                not isinstance(event.payload, Bar)
                or event.payload.interval not in self.bar_intervals
            )
        )


@dataclass(frozen=True, slots=True)
class Transition:
    state: RuntimeState
    commands: tuple[ObservationDispatch, ...]


def initial_state(config: RuntimeConfig) -> RuntimeState:
    seed = f"invest-engine:e2:v1:{config.run_version}:{config.mode.value}"
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return RuntimeState(config.run_version, config.mode, digest=digest)


def reduce_event(
    state: RuntimeState,
    event: EventEnvelope[MarketPayload],
    subscriptions: tuple[Subscription, ...] = (),
) -> Transition:
    """Pure, strict journal-order reducer; no implicit rescheduling or reordering."""
    if state.status is not RuntimeStatus.RUNNING:
        raise InvalidEvent("runtime halted: explicit operator recovery required")
    if event.ingest_ordinal != state.last_ordinal + 1:
        raise InvalidEvent("non-contiguous global ingestion ordinal")
    if event.event_id in state.seen_ids:
        raise InvalidEvent("duplicate event id")
    if event.quality_flags:
        raise InvalidEvent("quality flagged observation must not reach core")
    if isinstance(event.payload, Bar) and not event.payload.finalized:
        raise InvalidEvent("unfinalized bar must not reach core")
    observed_at = max(event.available_at, event.received_at)
    if state.observed_at is not None and observed_at < state.observed_at:
        raise InvalidEvent("observation time moved backwards")

    payload = canonical_bytes(event)
    digest = hashlib.sha256(
        bytes.fromhex(state.digest) + len(payload).to_bytes(8, "big") + payload
    ).hexdigest()
    counts = dict(state.counts)
    counts[event.event_type] = counts.get(event.event_type, 0) + 1
    updated = replace(
        state,
        last_ordinal=event.ingest_ordinal,
        observed_at=observed_at,
        event_count=state.event_count + 1,
        digest=digest,
        seen_ids=state.seen_ids | {event.event_id},
        counts=tuple(sorted(counts.items())),
    )
    commands = tuple(
        ObservationDispatch(sub.subscription_id, event.event_id, event.event_type)
        for sub in subscriptions if sub.matches(event)
    )
    return Transition(updated, commands)


class EventJournalProtocol:
    """Documented duck-typed runtime boundary; durable implementation in journal.py."""

    def attach(self, config: RuntimeConfig) -> None:
        raise NotImplementedError

    def commit_event(
        self, event: EventEnvelope[MarketPayload], state: RuntimeState, *, snapshot: bool
    ) -> None:
        raise NotImplementedError

    def events(self) -> Iterable[EventEnvelope[MarketPayload]]:
        raise NotImplementedError

    def verify_snapshot(self, state: RuntimeState) -> None:
        raise NotImplementedError

    def halt_reason(self) -> str | None:
        raise NotImplementedError

    def record_halt(self, reason: str) -> None:
        raise NotImplementedError

    def clear_halt(self) -> None:
        raise NotImplementedError


class EventRuntime:
    """A single-writer runtime. Journal commit precedes publication of new state."""

    def __init__(
        self,
        config: RuntimeConfig,
        *,
        journal: EventJournalProtocol | None = None,
        subscriptions: tuple[Subscription, ...] = (),
    ) -> None:
        ids = [sub.subscription_id for sub in subscriptions]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate subscription ids")
        self.config = config
        self.journal = journal
        self.subscriptions = tuple(sorted(subscriptions, key=lambda sub: sub.subscription_id))
        state = initial_state(config)
        if journal is not None:
            journal.attach(config)
            for event in journal.events():
                state = reduce_event(state, event, self.subscriptions).state
            journal.verify_snapshot(state)
            reason = journal.halt_reason()
            if reason is not None:
                state = replace(state, status=RuntimeStatus.HALTED, halt_reason=reason)
        self.state = state

    def accept(self, event: EventEnvelope[MarketPayload]) -> Transition:
        if self.state.status is RuntimeStatus.HALTED:
            raise InvalidEvent("runtime is halted")
        try:
            proposed = reduce_event(self.state, event, self.subscriptions)
            if self.journal is not None:
                self.journal.commit_event(
                    event, proposed.state,
                    snapshot=proposed.state.event_count % self.config.snapshot_interval == 0,
                )
            self.state = proposed.state
            return proposed
        except Exception as exc:
            # No further entries until a human explicitly investigates the failure.
            reason = f"{type(exc).__name__}: {exc}"
            self.state = replace(self.state, status=RuntimeStatus.HALTED, halt_reason=reason)
            if self.journal is not None:
                with suppress(Exception):
                    # If durable halt cannot be recorded, the in-memory runtime
                    # remains halted. The host must treat storage faults as fatal.
                    self.journal.record_halt(reason)
            raise

    def resume_after_review(self, *, reviewed: bool = False) -> None:
        if not reviewed:
            raise PermissionError("manual review must be acknowledged")
        if self.journal is not None:
            self.journal.clear_halt()
        self.state = replace(self.state, status=RuntimeStatus.RUNNING, halt_reason=None)
