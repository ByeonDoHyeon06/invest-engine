from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from invest_engine.core.features import FeatureGraph, FeatureNode
from invest_engine.core.fixtures import synthetic_ticks
from invest_engine.core.journal import SQLiteEventJournal
from invest_engine.core.runtime import (
    EventRuntime,
    RuntimeConfig,
    RuntimeMode,
    RuntimeStatus,
    Subscription,
    initial_state,
    reduce_event,
)
from invest_engine.domain.errors import InvalidEvent, UnsupportedData
from invest_engine.domain.events import EventEnvelope, MarketPayload
from invest_engine.domain.primitives import InstrumentId, Market


def test_500_event_state_replay_determinism(kr_instrument: InstrumentId) -> None:
    events = synthetic_ticks(kr_instrument, count=500)
    a = EventRuntime(RuntimeConfig("abc"))
    b = EventRuntime(RuntimeConfig("abc"))
    for event in events:
        a.accept(event)
        b.accept(event)
    assert a.state == b.state
    assert a.state.event_count == 500
    assert a.state.last_ordinal == 499
    assert a.state.counts == (("market.trade", 500),)
    assert a.state.status is RuntimeStatus.RUNNING


def test_pure_reducer_does_not_mutate_prior_state(kr_instrument: InstrumentId) -> None:
    config = RuntimeConfig("immutable")
    previous = initial_state(config)
    changed = reduce_event(previous, synthetic_ticks(kr_instrument, count=1)[0])
    assert previous.event_count == 0
    assert changed.state.event_count == 1
    assert changed.state.digest != previous.digest
    assert changed.commands == ()


def test_event_clock_uses_receipt_not_just_market_time(kr_instrument: InstrumentId) -> None:
    event = synthetic_ticks(kr_instrument, count=1)[0]
    result = reduce_event(initial_state(RuntimeConfig("clock")), event)
    assert result.state.observed_at == event.received_at


def test_quality_flag_rejected_and_halts(kr_instrument: InstrumentId) -> None:
    bad = replace(synthetic_ticks(kr_instrument, count=1)[0], quality_flags=("STALE",))
    runtime = EventRuntime(RuntimeConfig("bad"))
    with pytest.raises(InvalidEvent, match="quality"):
        runtime.accept(bad)
    assert runtime.state.status is RuntimeStatus.HALTED
    with pytest.raises(InvalidEvent, match="halted"):
        runtime.accept(bad)


def test_duplicate_ordinal_rejected_and_halts(kr_instrument: InstrumentId) -> None:
    runtime = EventRuntime(RuntimeConfig("ordinal"))
    event = synthetic_ticks(kr_instrument, count=1)[0]
    runtime.accept(event)
    with pytest.raises(InvalidEvent, match="non-contiguous"):
        runtime.accept(event)
    assert runtime.state.event_count == 1
    assert runtime.state.status is RuntimeStatus.HALTED


def test_duplicate_event_id_with_new_ordinal_halts(kr_instrument: InstrumentId) -> None:
    runtime = EventRuntime(RuntimeConfig("dupe"))
    event = synthetic_ticks(kr_instrument, count=1)[0]
    runtime.accept(event)
    with pytest.raises(InvalidEvent, match="duplicate"):
        runtime.accept(replace(event, ingest_ordinal=1))


def test_backwards_observed_time_halts(kr_instrument: InstrumentId) -> None:
    events = synthetic_ticks(kr_instrument, count=2)
    runtime = EventRuntime(RuntimeConfig("backward"))
    runtime.accept(events[0])
    with pytest.raises(InvalidEvent, match="backwards"):
        runtime.accept(replace(
            events[1], available_at=events[0].available_at,
            received_at=events[0].received_at - timedelta(microseconds=1),
        ))


def test_router_is_sorted_filtered_and_returns_pure_commands(kr_instrument: InstrumentId) -> None:
    subscriptions = (
        Subscription("z-trades", frozenset({"market.trade"}), markets=frozenset({Market.KR})),
        Subscription("b-quote", frozenset({"market.quote"})),
        Subscription("a-trades", frozenset({"market.trade"})),
    )
    runtime = EventRuntime(RuntimeConfig("router"), subscriptions=subscriptions)
    commands = runtime.accept(synthetic_ticks(kr_instrument, count=1)[0]).commands
    assert [cmd.subscription_id for cmd in commands] == ["a-trades", "z-trades"]


def test_router_timeframe_specific(kr_instrument: InstrumentId) -> None:
    subscriber = Subscription(
        "one-minute", frozenset({"market.bar"}),
        bar_intervals=frozenset({timedelta(minutes=1)}),
    )
    runtime = EventRuntime(RuntimeConfig("res"), subscriptions=(subscriber,))
    result = runtime.accept(synthetic_ticks(kr_instrument, count=1)[0])
    assert result.commands == ()


def test_duplicate_subscription_rejected() -> None:
    sub = Subscription("id", frozenset({"market.trade"}))
    with pytest.raises(ValueError, match="duplicate"):
        EventRuntime(RuntimeConfig("ids"), subscriptions=(sub, sub))


def test_live_disabled() -> None:
    with pytest.raises(UnsupportedData, match="E8"):
        RuntimeConfig("live", mode=RuntimeMode.LIVE)


def test_explicit_review_to_resume(kr_instrument: InstrumentId) -> None:
    runtime = EventRuntime(RuntimeConfig("resume"))
    event = synthetic_ticks(kr_instrument, count=1)[0]
    with pytest.raises(InvalidEvent):
        runtime.accept(replace(event, ingest_ordinal=3))
    with pytest.raises(PermissionError):
        runtime.resume_after_review()
    runtime.resume_after_review(reviewed=True)
    runtime.accept(event)
    assert runtime.state.status is RuntimeStatus.RUNNING


def test_snapshot_recovery_and_tail_events(tmp_path: Path, kr_instrument: InstrumentId) -> None:
    db = tmp_path / "events.sqlite"
    config = RuntimeConfig("snapshot", snapshot_interval=10)
    events = synthetic_ticks(kr_instrument, count=23)
    with SQLiteEventJournal(db) as journal:
        first = EventRuntime(config, journal=journal)
        for event in events:
            first.accept(event)
        state = first.state
    with SQLiteEventJournal(db) as journal:
        recovered = EventRuntime(config, journal=journal)
        assert recovered.state == state
        assert len(journal.events()) == 23
        assert journal.connection.execute("SELECT count(*) FROM checkpoints").fetchone()[0] == 2


def test_bad_checksum_detected_at_startup(tmp_path: Path, kr_instrument: InstrumentId) -> None:
    db = tmp_path / "tamper.sqlite"
    config = RuntimeConfig("tamper", snapshot_interval=1)
    with SQLiteEventJournal(db) as journal:
        EventRuntime(config, journal=journal).accept(synthetic_ticks(kr_instrument, count=1)[0])
        journal.connection.execute("UPDATE events SET json='{}' WHERE ordinal=0")
        journal.connection.commit()
    with SQLiteEventJournal(db) as journal, pytest.raises(InvalidEvent, match="checksum"):
        EventRuntime(config, journal=journal)


def test_snapshot_mismatch_detected_at_startup(tmp_path: Path, kr_instrument: InstrumentId) -> None:
    db = tmp_path / "snapshot.sqlite"
    config = RuntimeConfig("snap-mismatch", snapshot_interval=1)
    with SQLiteEventJournal(db) as journal:
        EventRuntime(config, journal=journal).accept(synthetic_ticks(kr_instrument, count=1)[0])
        journal.connection.execute("UPDATE checkpoints SET json='{}' WHERE ordinal=0")
        journal.connection.commit()
    with SQLiteEventJournal(db) as journal, pytest.raises(InvalidEvent, match="snapshot checksum"):
        EventRuntime(config, journal=journal)


def test_incorrect_run_version_rejected(tmp_path: Path, kr_instrument: InstrumentId) -> None:
    db = tmp_path / "different.sqlite"
    with SQLiteEventJournal(db) as journal:
        runtime = EventRuntime(RuntimeConfig("v1"), journal=journal)
        runtime.accept(synthetic_ticks(kr_instrument, count=1)[0])
    with SQLiteEventJournal(db) as journal, pytest.raises(InvalidEvent, match="different runtime"):
        EventRuntime(RuntimeConfig("v2"), journal=journal)


def test_persisted_halt_requires_review(tmp_path: Path, kr_instrument: InstrumentId) -> None:
    db = tmp_path / "halt.sqlite"
    config = RuntimeConfig("halt", snapshot_interval=1)
    with SQLiteEventJournal(db) as journal:
        runtime = EventRuntime(config, journal=journal)
        with pytest.raises(InvalidEvent):
            runtime.accept(replace(synthetic_ticks(kr_instrument, count=1)[0], ingest_ordinal=6))
    with SQLiteEventJournal(db) as journal:
        recovered = EventRuntime(config, journal=journal)
        assert recovered.state.status is RuntimeStatus.HALTED
        recovered.resume_after_review(reviewed=True)
        recovered.accept(synthetic_ticks(kr_instrument, count=1)[0])
    with SQLiteEventJournal(db) as journal:
        assert EventRuntime(config, journal=journal).state.status is RuntimeStatus.RUNNING


def test_feature_graph_dependency_schedule() -> None:
    graph = FeatureGraph([
        FeatureNode("signal", ("ema", "volume")),
        FeatureNode("ema", ("close",)),
        FeatureNode("volume"),
        FeatureNode("close"),
    ])
    assert graph.schedule(["signal"]) == ("close", "ema", "volume", "signal")


def test_feature_cycle_and_missing_dependency_rejected() -> None:
    with pytest.raises(ValueError, match="cycle"):
        FeatureGraph([FeatureNode("a", ("b",)), FeatureNode("b", ("a",))])
    with pytest.raises(ValueError, match="unknown"):
        FeatureGraph([FeatureNode("a", ("missing",))])
    with pytest.raises(ValueError, match="unique"):
        FeatureGraph([FeatureNode("a"), FeatureNode("a")])


def test_codec_roundtrip_all_market_payloads(kr_instrument: InstrumentId) -> None:
    from datetime import datetime, timezone
    from decimal import Decimal

    from invest_engine.core.codec import decode_event
    from invest_engine.core.replay import canonical_bytes
    from invest_engine.domain.events import (
        Bar, BookLevel, MarketStatus, OrderBookSnapshot, QuoteTick, SessionState,
    )

    start = datetime(2026, 1, 2, 9, tzinfo=timezone.utc)
    base = synthetic_ticks(kr_instrument, count=1)[0]
    payloads = [
        ("market.trade", base.payload),
        ("market.quote", QuoteTick(Decimal("10"), Decimal("20"), Decimal("11"), Decimal("20"))),
        ("market.order_book_snapshot", OrderBookSnapshot(
            (BookLevel(Decimal("10"), Decimal("3")),),
            (BookLevel(Decimal("11"), Decimal("2")),),
        )),
        ("market.bar", Bar(
            start, start + timedelta(minutes=1), Decimal(10), Decimal(12), Decimal(9),
            Decimal(11), Decimal(50), interval=timedelta(minutes=1),
        )),
        ("market.status", MarketStatus(SessionState.CLOSED, "synthetic-test")),
    ]
    for name, payload in payloads:
        event: EventEnvelope[MarketPayload] = replace(
            base, event_type=name, payload=payload,
            instrument_id=None if name == "market.status" else kr_instrument,
        )
        assert decode_event(canonical_bytes(event)) == event


def test_same_event_stream_different_version_produces_different_digest(
    kr_instrument: InstrumentId,
) -> None:
    event = synthetic_ticks(kr_instrument, count=1)[0]
    first = EventRuntime(RuntimeConfig("v1"))
    second = EventRuntime(RuntimeConfig("v2"))
    first.accept(event)
    second.accept(event)
    assert first.state.digest != second.state.digest


def test_journal_snapshot_detects_self_consistent_forgery(
    tmp_path: Path, kr_instrument: InstrumentId,
) -> None:
    import hashlib
    import json

    db = tmp_path / "forged.sqlite"
    config = RuntimeConfig("forge", snapshot_interval=1)
    with SQLiteEventJournal(db) as journal:
        runtime = EventRuntime(config, journal=journal)
        runtime.accept(synthetic_ticks(kr_instrument, count=1)[0])
        row = journal.connection.execute("SELECT json FROM checkpoints WHERE ordinal=0").fetchone()
        forged = json.loads(row[0])
        forged["event_count"] = 900
        encoded = json.dumps(forged, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        journal.connection.execute(
            "UPDATE checkpoints SET json=?,checksum=? WHERE ordinal=0",
            (encoded, hashlib.sha256(encoded.encode()).hexdigest()),
        )
        journal.connection.commit()
    with SQLiteEventJournal(db) as journal, pytest.raises(InvalidEvent, match="snapshot differs"):
        EventRuntime(config, journal=journal)


def test_state_not_published_if_journal_commit_fails(
    tmp_path: Path, kr_instrument: InstrumentId,
) -> None:
    import sqlite3

    db = tmp_path / "full.sqlite"
    config = RuntimeConfig("fail")
    with SQLiteEventJournal(db) as journal:
        runtime = EventRuntime(config, journal=journal)
        journal.connection.execute("CREATE TRIGGER reject_event BEFORE INSERT ON events BEGIN SELECT RAISE(ABORT, 'test failure'); END")
        with pytest.raises(sqlite3.IntegrityError):
            runtime.accept(synthetic_ticks(kr_instrument, count=1)[0])
        assert runtime.state.event_count == 0
        assert runtime.state.status is RuntimeStatus.HALTED
        assert journal.connection.execute("SELECT count(*) FROM events").fetchone()[0] == 0
