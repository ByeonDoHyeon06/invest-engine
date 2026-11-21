from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest

from invest_engine.data.calendar import StaticSessionCalendar, TradingSession
from invest_engine.domain.errors import InvalidEvent
from invest_engine.domain.events import Bar, EventEnvelope
from invest_engine.domain.primitives import InstrumentId, Market
from invest_engine.strategies.portfolio_contracts import (
    UniverseCheckpointKind,
    UniverseFrameOutcome,
    UniverseFrameStatus,
)
from invest_engine.strategies.universe import UniverseFrameCoordinator


MINUTE = timedelta(minutes=1)
SESSION_START = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)
SESSION_END = SESSION_START + timedelta(minutes=390)
A = InstrumentId(Market.US, "XNAS", "US-A", "AAA", "USD")
B = InstrumentId(Market.US, "XNYS", "US-B", "BBB", "USD")


def calendar(
    *,
    first_end: datetime = SESSION_END,
    second_end: datetime = SESSION_END,
) -> StaticSessionCalendar:
    return StaticSessionCalendar(
        (
            TradingSession(Market.US, A.venue, SESSION_START, first_end),
            TradingSession(Market.US, B.venue, SESSION_START, second_end),
        )
    )


def bar_event(
    instrument: InstrumentId,
    event_id: str,
    end: datetime,
    ordinal: int,
    *,
    known_at: datetime | None = None,
) -> EventEnvelope[Bar]:
    bar = Bar(
        end - MINUTE,
        end,
        D("100"),
        D("101"),
        D("99"),
        D("100"),
        D("1000"),
        interval=MINUTE,
    )
    observed_at = known_at or end
    return EventEnvelope(
        event_id,
        "market.bar",
        "fixture",
        instrument,
        end,
        observed_at,
        observed_at,
        ordinal,
        bar,
    )


def finalize(
    events: tuple[EventEnvelope[Bar], ...],
    as_of: datetime,
    *,
    source_calendar: StaticSessionCalendar | None = None,
) -> tuple[UniverseFrameCoordinator, UniverseFrameOutcome]:
    coordinator = UniverseFrameCoordinator(source_calendar or calendar(), (B, A))
    for event in events:
        coordinator.accept(event)
    return coordinator, coordinator.finalize(as_of)


def test_complete_frame_is_cross_venue_sorted_and_deterministic() -> None:
    checkpoint = SESSION_START + timedelta(minutes=30)
    events = (
        bar_event(B, "bar:b:1000", checkpoint, 0),
        bar_event(A, "bar:a:1000", checkpoint, 1),
    )
    _, first = finalize(events, checkpoint)
    _, second = finalize(events, checkpoint)

    assert first.status is UniverseFrameStatus.COMPLETE
    assert first.frame is not None
    assert first.frame == second.frame
    assert tuple(item.key for item in first.frame.instruments) == tuple(
        sorted((A.key, B.key))
    )
    assert first.frame.kind is UniverseCheckpointKind.REBALANCE

    flatten_at = SESSION_END - timedelta(minutes=30)
    _, flatten = finalize(
        (
            bar_event(A, "bar:a:1530", flatten_at, 0),
            bar_event(B, "bar:b:1530", flatten_at, 1),
        ),
        flatten_at,
    )
    assert flatten.frame is not None
    assert flatten.frame.kind is UniverseCheckpointKind.FLATTEN

    changed_events = (events[0], replace(events[1], event_id="bar:a:1000:corrected"))
    _, changed = finalize(changed_events, checkpoint)
    assert changed.frame is not None
    assert changed.frame.frame_id != first.frame.frame_id


def test_missing_member_is_data_unavailable_not_partial_frame() -> None:
    checkpoint = SESSION_START + timedelta(minutes=30)
    _, outcome = finalize(
        (bar_event(A, "bar:a:1000", checkpoint, 0),),
        checkpoint,
    )

    assert outcome.status is UniverseFrameStatus.DATA_UNAVAILABLE
    assert outcome.frame is None
    assert outcome.missing_instrument_keys == (B.key,)
    assert outcome.reason_codes == ("UNIVERSE_FRAME_INCOMPLETE",)


def test_misaligned_sessions_fail_and_early_close_is_no_action() -> None:
    checkpoint = SESSION_START + timedelta(minutes=30)
    events = (
        bar_event(A, "bar:a:1000", checkpoint, 0),
        bar_event(B, "bar:b:1000", checkpoint, 1),
    )
    coordinator = UniverseFrameCoordinator(
        calendar(second_end=SESSION_END - MINUTE),
        (A, B),
    )
    for event in events:
        coordinator.accept(event)

    with pytest.raises(InvalidEvent, match="UNIVERSE_SESSION_MISMATCH"):
        coordinator.finalize(checkpoint)
    assert coordinator.halt_reason is not None
    with pytest.raises(InvalidEvent, match="halted"):
        coordinator.finalize(checkpoint)

    early_end = SESSION_START + timedelta(minutes=210)
    _, early = finalize(
        events,
        checkpoint,
        source_calendar=calendar(first_end=early_end, second_end=early_end),
    )
    assert early.status is UniverseFrameStatus.NO_ACTION
    assert early.frame is None
    assert early.reason_codes == ("NO_ACTION_EARLY_CLOSE",)


def test_checkpoint_outside_schedule_is_no_action() -> None:
    outside = SESSION_START + timedelta(minutes=15)
    _, outcome = finalize(
        (
            bar_event(A, "bar:a:0945", outside, 0),
            bar_event(B, "bar:b:0945", outside, 1),
        ),
        outside,
    )

    assert outcome.status is UniverseFrameStatus.NO_ACTION
    assert outcome.frame is None
    assert outcome.reason_codes == ("NO_ACTION_OUTSIDE_CHECKPOINT_SCHEDULE",)


def test_rebalance_window_always_reserves_the_final_session_hour() -> None:
    checkpoint_interval = timedelta(minutes=15)
    inside_final_hour = SESSION_END - timedelta(minutes=45)
    coordinator = UniverseFrameCoordinator(
        calendar(),
        (A, B),
        checkpoint_interval=checkpoint_interval,
    )
    for event in (
        bar_event(A, "bar:a:inside-final-hour", inside_final_hour, 0),
        bar_event(B, "bar:b:inside-final-hour", inside_final_hour, 1),
    ):
        coordinator.accept(event)

    outcome = coordinator.finalize(inside_final_hour)
    assert outcome.status is UniverseFrameStatus.NO_ACTION
    assert outcome.reason_codes == ("NO_ACTION_OUTSIDE_CHECKPOINT_SCHEDULE",)


def test_late_bar_after_finalized_watermark_halts_coordinator() -> None:
    checkpoint = SESSION_START + timedelta(minutes=30)
    events = (
        bar_event(A, "bar:a:1000", checkpoint, 0),
        bar_event(B, "bar:b:1000", checkpoint, 1),
    )
    coordinator, outcome = finalize(events, checkpoint)
    assert outcome.status is UniverseFrameStatus.COMPLETE

    late = bar_event(
        A,
        "bar:a:0959:late",
        checkpoint - MINUTE,
        2,
        known_at=checkpoint + MINUTE,
    )
    with pytest.raises(InvalidEvent, match="watermark"):
        coordinator.accept(late)
    assert coordinator.halt_reason is not None
    with pytest.raises(InvalidEvent, match="halted"):
        coordinator.accept(late)


def test_duplicate_noncontiguous_flagged_unfinalized_and_wrong_interval_fail() -> None:
    checkpoint = SESSION_START + timedelta(minutes=30)
    first = bar_event(A, "bar:a:1000", checkpoint, 0)

    duplicate = UniverseFrameCoordinator(calendar(), (A, B))
    duplicate.accept(first)
    with pytest.raises(InvalidEvent, match="duplicate"):
        duplicate.accept(replace(first, ingest_ordinal=1))
    assert duplicate.halt_reason is not None
    with pytest.raises(InvalidEvent, match="halted"):
        duplicate.accept(replace(first, ingest_ordinal=1))

    malformed = (
        replace(first, ingest_ordinal=4, event_id="noncontiguous"),
        replace(first, event_id="flagged", quality_flags=("STALE",)),
        replace(
            first,
            event_id="unfinalized",
            payload=replace(first.payload, finalized=False),
        ),
        replace(
            first,
            event_id="wrong-interval",
            payload=replace(first.payload, interval=2 * MINUTE),
        ),
    )
    expected = ("contiguous", "quality", "unfinalized", "interval")
    for event, message in zip(malformed, expected, strict=True):
        coordinator = UniverseFrameCoordinator(calendar(), (A, B))
        with pytest.raises(InvalidEvent, match=message):
            coordinator.accept(event)
        assert coordinator.halt_reason is not None
        with pytest.raises(InvalidEvent, match="halted"):
            coordinator.accept(event)


def test_finalization_cannot_move_behind_observed_stream_or_previous_watermark() -> None:
    checkpoint = SESSION_START + timedelta(minutes=30)
    events = (
        bar_event(A, "bar:a:1000", checkpoint, 0),
        bar_event(B, "bar:b:1000", checkpoint, 1),
    )

    behind_stream = UniverseFrameCoordinator(calendar(), (A, B))
    for event in events:
        behind_stream.accept(event)
    with pytest.raises(InvalidEvent, match="observed stream"):
        behind_stream.finalize(checkpoint - MINUTE)
    assert behind_stream.halt_reason is not None
    with pytest.raises(InvalidEvent, match="halted"):
        behind_stream.finalize(checkpoint)

    behind_watermark = UniverseFrameCoordinator(calendar(), (A, B))
    for event in events:
        behind_watermark.accept(event)
    later = checkpoint + timedelta(minutes=30)
    assert (
        behind_watermark.finalize(later).status
        is UniverseFrameStatus.DATA_UNAVAILABLE
    )
    with pytest.raises(InvalidEvent, match="watermark"):
        behind_watermark.finalize(checkpoint)
    assert behind_watermark.halt_reason is not None
    with pytest.raises(InvalidEvent, match="halted"):
        behind_watermark.finalize(checkpoint)


def test_invalidate_history_removes_only_one_instrument_without_rewinding_stream() -> None:
    checkpoint = SESSION_START + timedelta(minutes=30)
    coordinator, outcome = finalize(
        (
            bar_event(A, "bar:a:1000", checkpoint, 0),
            bar_event(B, "bar:b:1000", checkpoint, 1),
        ),
        checkpoint,
    )
    assert outcome.status is UniverseFrameStatus.COMPLETE
    audit_before = (
        coordinator.last_ordinal,
        coordinator.last_known,
        coordinator.finalized_watermark,
    )

    coordinator.invalidate_instrument_history(A)

    assert all(item.instrument.key != A.key for item in coordinator.observations)
    assert any(item.instrument.key == B.key for item in coordinator.observations)
    assert (
        coordinator.last_ordinal,
        coordinator.last_known,
        coordinator.finalized_watermark,
    ) == audit_before
