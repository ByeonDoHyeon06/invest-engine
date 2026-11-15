"""In-memory Point-in-Time observation boundary for early research tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from invest_engine.data.quality import QualityDecision
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import EventEnvelope, MarketPayload
from invest_engine.domain.primitives import utc_datetime


@dataclass(slots=True)
class ObservationBuffer:
    """Accepts quality-approved observations; disallows future availability/receipt.

    Not a durable journal or broker-ready feed. The E2 engine owns persistence.
    """

    _events: list[EventEnvelope[MarketPayload]] = field(default_factory=list)
    _ids: set[str] = field(default_factory=set)

    def append(self, decision: QualityDecision) -> None:
        if not decision.accepted:
            raise InvalidEvent("quarantined observation cannot enter strategy-visible buffer")
        event = decision.event
        if event.event_id in self._ids:
            raise InvalidEvent("duplicate event in observation buffer")
        self._ids.add(event.event_id)
        self._events.append(event)

    def visible_at(self, instant: datetime) -> tuple[EventEnvelope[MarketPayload], ...]:
        at = utc_datetime(instant, field="observation.as_of")
        return tuple(
            sorted(
                (
                    event for event in self._events
                    if event.available_at <= at and event.received_at <= at
                ),
                key=lambda event: (max(event.available_at, event.received_at), event.ingest_ordinal),
            )
        )
